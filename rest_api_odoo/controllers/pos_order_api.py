from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError
import pytz
import json
import psycopg2
import uuid
import logging
from datetime import datetime, time, timedelta

_logger = logging.getLogger(__name__)

class PosOrderApi(http.Controller):
        
    @http.route(
        "/api/pos/order",
        type="http",
        auth="none",
        methods=["GET", "POST", "OPTIONS"],
        csrf=False
    )
    def pos_order(self, **kw):
        # CORS preflight
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api-key, company-id"),
            ])

        req_id = str(uuid.uuid4())

        try:
            env = self._api_env(request.env)

            method = request.httprequest.method.upper()

            if method == "GET":
                result = self._list_orders(env, kw)
                # selalu sisipkan req_id biar gampang trace
                if isinstance(result, dict):
                    result.setdefault("req_id", req_id)
                return self._resp(result, result.get("status", 200) if isinstance(result, dict) else 200)

            if method == "POST":
                raw = request.httprequest.data or b"{}"
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    return self._resp(self._err(f"Invalid JSON body (req_id={req_id})", 400), 400)

                # Validasi minimal & aman
                if not isinstance(body, dict):
                    return self._resp(self._err(f"Body must be a JSON object (req_id={req_id})", 400), 400)

                # lines wajib list & tidak kosong
                lines = body.get("lines")
                if not isinstance(lines, list) or not lines:
                    return self._resp(self._err(f"Field 'lines' must be a non-empty list (req_id={req_id})", 400), 400)

                # validasi tiap line
                for i, line in enumerate(lines):
                    if not isinstance(line, dict):
                        return self._resp(self._err(f"lines[{i}] must be an object (req_id={req_id})", 400), 400)
                    for k in ("product_id", "qty", "price_unit"):
                        if line.get(k) is None:
                            return self._resp(self._err(f"lines[{i}].{k} is required (req_id={req_id})", 400), 400)

                result = self._create_order(env, body)
                if isinstance(result, dict):
                    result.setdefault("req_id", req_id)
                return self._resp(result, result.get("status", 200) if isinstance(result, dict) else 200)

            return self._resp(self._err(f"Method not allowed (req_id={req_id})", 405), 405)

        except Exception:
            # Jangan bocorin error internal mentah ke client
            _logger.exception("POS ORDER API ERROR req_id=%s", req_id)
            return self._resp(self._err(f"Internal server error (req_id={req_id})", 500), 500)

    
    @http.route("/api/pos/order/pay", type="http", auth="none", methods=["POST", "OPTIONS"], csrf=False)
    def pos_order_pay(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
            ])

        order_id = int(kw.get("id", 0))
        if not order_id:
            return self._resp(self._err("Missing id", 400), 400)

        try:
            env = self._api_env(request.env)

            raw = request.httprequest.data or b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._resp(self._err("Invalid JSON body", 400), 400)

            # =========================
            # 1) PAY ORDER (EXISTING)
            # =========================
            result = self._pay_order(env, order_id, body)

            # =========================
            # 2) STOCK PROCESS (ADD-ON, FRONTEND TIDAK PERLU UBAH)
            #    - tidak mengubah route / params / request contract
            #    - hanya menambahkan proses stock setelah berhasil pay
            # =========================
            try:
                # hanya lanjut kalau response pay sukses
                is_dict = isinstance(result, dict)
                success = bool(result.get("success")) if is_dict else False
                status = int(result.get("status", 200)) if is_dict else 200

                if success and status < 400:
                    order = env["pos.order"].sudo().browse(order_id)
                    if order and order.exists():
                        self._fix_order_line_uom(env, order)
                        # kalau state paid/done, coba trigger stock
                        st = (order.state or "").lower()
                        if st in ("paid", "done", "invoiced"):
                            stock_info = self._pos_try_process_stock(env, order)

                            # tambahin info ke response (frontend aman karena biasanya ignore extra field)
                            if is_dict:
                                # simpan di level root biar mudah trace, tapi tidak mengubah field lama
                                result["stock_processed"] = bool(stock_info.get("stock_processed", False))
                                result["picking_ids"] = stock_info.get("picking_ids", [])
                                result["picking_states"] = stock_info.get("picking_states", [])
                                if stock_info.get("stock_error"):
                                    result["stock_error"] = stock_info.get("stock_error")

            except Exception:
                # jangan bikin pay gagal cuma karena stock post-process error
                _logger.exception("POS ORDER PAY STOCK POST-PROCESS ERROR order_id=%s", order_id)

            return self._resp(result, result.get("status", 200) if isinstance(result, dict) else 200)

        except Exception as e:
            _logger.exception("POS ORDER PAY API ERROR")
            return self._resp(self._err(str(e), 400), 400)


    def _pos_try_process_stock(self, env, order):
        out = {
        "stock_processed": False,
        "picking_ids": [],
        "picking_states": [],
        "stock_error": None,
    }

        try:
            order = order.sudo().with_company(order.company_id)

            # --- debug info minimal (opsional tapi sangat membantu)
            try:
                _logger.info(
                    "STOCK TRY order=%s state=%s session=%s config=%s real_time=%s lines=%s",
                    order.id,
                    order.state,
                    order.session_id.id if order.session_id else None,
                    order.session_id.config_id.id if order.session_id and order.session_id.config_id else None,
                    getattr(order.session_id.config_id, "real_time_inventory", None)
                    if order.session_id and order.session_id.config_id else None,
                    len(order.lines),
                )
            except Exception:
                pass

            pickings = order.picking_ids.sudo() if hasattr(order, "picking_ids") else env["stock.picking"].sudo()
            out["picking_ids"] = pickings.ids

            # 1) create picking kalau belum ada
            if not pickings:
                created = False
                for fn_name in ("_create_order_picking", "_create_picking"):
                    fn = getattr(order, fn_name, None)
                    if callable(fn):
                        _logger.info("STOCK CREATE picking via %s order=%s", fn_name, order.id)
                        fn()
                        created = True
                        break

                pickings = order.picking_ids.sudo()
                out["picking_ids"] = pickings.ids

                if not created:
                    out["stock_error"] = "No picking creation method found (_create_order_picking/_create_picking)."
                    return out

                if not pickings:
                    out["stock_error"] = "Picking masih belum terbentuk setelah create (cek config/session/location)."
                    return out

            # 2) process picking: confirm -> assign -> qty_done -> validate (+ handle wizard)
            for p in pickings.filtered(lambda x: x.state not in ("done", "cancel")).sudo():
                try:
                    if p.state == "draft" and hasattr(p, "action_confirm"):
                        p.action_confirm()

                    if hasattr(p, "action_assign"):
                        p.action_assign()

                    # set qty_done supaya validate jalan
                    mls = getattr(p, "move_line_ids", None)
                    if mls is not None:
                        for ml in mls:
                            if (ml.qty_done or 0) <= 0:
                                reserved = getattr(ml, "reserved_uom_qty", 0) or 0
                                demand = getattr(ml, "product_uom_qty", 0) or 0
                                ml.qty_done = reserved if reserved > 0 else demand

                    # validate
                    res = p.button_validate() if hasattr(p, "button_validate") else None

                    # handle wizard immediate/backorder kalau muncul
                    if isinstance(res, dict) and res.get("res_model") in (
                        "stock.immediate.transfer",
                        "stock.backorder.confirmation",
                    ):
                        wiz = env[res["res_model"]].sudo().browse(res.get("res_id"))
                        if wiz and wiz.exists():
                            if res["res_model"] == "stock.immediate.transfer" and hasattr(wiz, "process"):
                                wiz.process()
                            elif res["res_model"] == "stock.backorder.confirmation":
                                if hasattr(wiz, "process"):
                                    wiz.process()
                                elif hasattr(wiz, "process_cancel_backorder"):
                                    wiz.process_cancel_backorder()

                except Exception as e:
                    # catat error terakhir untuk diagnosa
                    out["stock_error"] = f"picking_id={p.id} err={str(e)}"

            # refresh
            pickings = order.picking_ids.sudo()
            out["picking_states"] = pickings.mapped("state")
            out["picking_ids"] = pickings.ids

            # sukses kalau minimal ada picking done
            out["stock_processed"] = bool(pickings) and any(st == "done" for st in out["picking_states"])
            return out

        except Exception as e:
            out["stock_error"] = str(e)
            return out

        
    @http.route(
    "/api/pos/order/cancel",
    type="http",
    auth="none",
    methods=["PUT", "OPTIONS"],
    csrf=False
    )
    def pos_order_cancel(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "PUT,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
            ])

        method = request.httprequest.method.upper()

        # parse JSON body (optional)
        data = {}
        if method == "PUT":
            raw = request.httprequest.data or b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._resp(self._err("Invalid JSON body", 400), 400)

        # values optional
        values = data.get("values") if isinstance(data, dict) else None
        if values is None and isinstance(data, dict):
            values = data

        try:
            env = self._api_env(request.env)

            order_id = kw.get("id") or kw.get("Id") or (values or {}).get("id")
            order_id = self._parse_int(order_id)
            if not order_id:
                return self._resp(self._err("Missing order id", 400), 400)

            result = self._cancel_order(env, order_id)
            return self._resp(result, result.get("status", 200))

        except Exception as e:
            _logger.exception("POS ORDER CANCEL ERROR")
            return self._resp(self._err(str(e), 400), 400)
        
        
    @http.route(
    "/api/pos/order/draft",
    type="http",
    auth="none",
    methods=["GET", "OPTIONS"],
    csrf=False
    )
    def pos_order_draft(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
            ])

        try:
            env = self._api_env(request.env)
            result = self._list_draft_orders(env, kw)
            return self._resp(result, result.get("status", 200))
        except Exception as e:
            _logger.exception("POS ORDER DRAFT API ERROR")
            return self._resp(self._err(str(e), 400), 400)
        
        
        
    @http.route(
    "/api/pos/order/count",
    type="http",
    auth="none",
    methods=["GET", "OPTIONS"],
    csrf=False
    )
    def pos_order_count(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type"),
            ])

        try:
            env = self._api_env(request.env)
            result = self._count_orders(env, kw)
            return self._resp(result, result.get("status", 200))
        except Exception as e:
            _logger.exception("POS ORDER COUNT ERROR")
            return self._resp(self._err(str(e), 400), 400)
        

    # ---------------- helpers ----------------

    def _api_env(self, env):
        # kompatibel dengan env yang tidak punya with_user()
        service_uid = env.ref("base.user_admin").id
        return env(user=service_uid, su=True)

    def _resp(self, payload, status=200):
        # default=str biar datetime aman, tapi kita juga format manual di data
        body = json.dumps(payload, default=str)
        return request.make_response(body, headers=[
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
        ], status=status)

    def _err(self, msg, status=400, code=None, data=None):
        out = {"success": False, "message": msg, "status": status}
        if code:
            out["code"] = code
        if data is not None:
            out["data"] = data
        return out

    def _parse_int(self, v, default=None):
        try:
            return int(v)
        except Exception:
            return default

    def _parse_bool(self, v, default=False):
        if v is None:
            return default
        return str(v).lower() in ("1", "true", "yes", "y", "on")

    def _parse_states(self, v):
        # "paid,done" -> ["paid","done"]
        if not v:
            return ["paid", "done", "invoiced"]
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return ["paid", "done", "invoiced"]

    def _parse_dt(self, s):
        # terima "YYYY-MM-DD" atau "YYYY-MM-DD HH:MM:SS"
        if not s:
            return None
        s = str(s).strip()
        try:
            if len(s) == 10:
                d = fields.Date.from_string(s)
                return fields.Datetime.to_datetime(d)
            return fields.Datetime.from_string(s)
        except Exception:
            raise UserError("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")

    # ---------------- core ----------------

    def _list_orders(self, env, params):
        session_id = self._parse_int(params.get("session_id"))
        config_id = self._parse_int(params.get("config_id"))
        mode = (params.get("mode") or "").lower()
        phone = (params.get("phone") or params.get("mobile") or "").strip()

        limit = self._parse_int(params.get("limit"), 50)
        offset = self._parse_int(params.get("offset"), 0)

        include_lines = self._parse_bool(params.get("include_lines"), False)
        include_payments = self._parse_bool(params.get("include_payments"), False)

        PosOrder = env["pos.order"]
        domain = []

        # ✅ cek dulu field-nya ada di model apa tidak
        has_change_amount = "change_amount" in PosOrder._fields

        # =========================
        # MODE: TODAY (posted only)
        # =========================
        if mode == "today":
            config = env["pos.config"].sudo().browse(int(config_id or 0))
            if not config.exists():
                return {
                    "success": False,
                    "message": "POS config not found",
                    "data": {"items": []},
                }

            user_tz = (
                config.company_id.partner_id.tz
                or env.user.tz
                or "Asia/Jakarta"
            )

            try:
                tz = pytz.timezone(user_tz)
            except Exception:
                tz = pytz.timezone("Asia/Jakarta")
                user_tz = "Asia/Jakarta"

            now_local = datetime.now(tz)
            start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=1)

            start = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
            end = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

            domain += [
                ("session_id.config_id", "=", config.id),
                ("date_order", ">=", start),
                ("date_order", "<", end),
                ("state", "in", ["paid", "done", "invoiced"]),
            ]

            _logger.warning(
                "POS TODAY DEBUG mode=%s config_id=%s config_name=%s tz=%s now_local=%s start_utc=%s end_utc=%s domain=%s",
                mode,
                config.id,
                config.name,
                user_tz,
                now_local,
                start,
                end,
                domain,
            )

            _logger.warning(
                "POS TODAY COUNT=%s",
                env["pos.order"].sudo().search_count(domain),
            )

        # =========================
        # MODE: DRAFT (lintas hari)
        # =========================
        elif mode == "draft":
            domain += [("state", "=", "draft")]

        # =========================
        # MODE: DEFAULT (legacy)
        # =========================
        else:
            states = self._parse_states(params.get("state"))
            date_from = self._parse_dt(params.get("date_from"))
            date_to = self._parse_dt(params.get("date_to"))

            domain.append(("state", "in", states))
            if date_from:
                domain.append(("date_order", ">=", date_from))
            if date_to:
                domain.append(("date_order", "<=", date_to))

        # =========================
        # FILTER TAMBAHAN
        # =========================
        if session_id:
            domain.append(("session_id", "=", session_id))
        if config_id:
            domain.append(("session_id.config_id", "=", config_id))
        if phone:
            domain += ["|", ("partner_id.phone", "ilike", phone), ("partner_id.mobile", "ilike", phone)]

        # total untuk pagination
        total_count = PosOrder.search_count(domain)

        # field dasar (buat list)
        fields_basic = [
            "id", "name", "pos_reference",
            "date_order", "state",
            "session_id", "amount_total", "amount_tax", "amount_paid", "amount_return",
            "partner_id", "user_id", "company_id",
        ]
        # ✅ tambahin ke fields_basic kalau ada
        if has_change_amount:
            fields_basic.append("change_amount")

        orders_rs = PosOrder.search(domain, limit=limit, offset=offset, order="date_order desc, id desc")
        items = [self._order_to_dict(o, include_lines=include_lines, include_payments=include_payments) for o in orders_rs]

        # ==========================================================
        # AMBIL name_waiters / name_customer dari poskas.bill
        # (field ini TIDAK ada di pos.order, jadi jangan akses
        # rec.name_waiters langsung -> bisa 500 AttributeError)
        # ==========================================================
        bills_by_order = {}
        try:
            if orders_rs:
                bills = env["poskas.bill"].sudo().search([
                    ("pos_order_id", "in", orders_rs.ids)
                ])
                for b in bills:
                    if b.pos_order_id:
                        # kalau ada lebih dari 1 bill per order, ambil yang terakhir dibuat
                        bills_by_order[b.pos_order_id.id] = b
        except Exception:
            _logger.exception("FAILED GET BILL LIST FOR ORDERS order_ids=%s", orders_rs.ids)

        for it, rec in zip(items, orders_rs):
            # datetime -> string
            it["date_order"] = fields.Datetime.to_string(rec.date_order) if rec.date_order else None

            # m2o -> rapihin jadi id + name
            it["session_id"] = rec.session_id.id if rec.session_id else None
            it["session_name"] = rec.session_id.name if rec.session_id else None

            it["partner_id"] = rec.partner_id.id if rec.partner_id else None
            it["partner_name"] = rec.partner_id.name if rec.partner_id else None

            it["user_id"] = rec.user_id.id if rec.user_id else None
            it["user_name"] = rec.user_id.name if rec.user_id else None

            # fallback: kalau field ini kebetulan ada juga di pos.order, pakai itu dulu
            it["name_waiters"] = getattr(rec, "name_waiters", None) or None
            it["name_customer"] = getattr(rec, "name_customer", None) or None

            # ✅ change_amount (defensive, biar gak 500 kalau field belum ke-upgrade)
            if has_change_amount:
                it["change_amount"] = float(rec.change_amount or 0.0)
            else:
                it["change_amount"] = 0.0

            # override pakai data dari poskas.bill (sumber utama)
            bill = bills_by_order.get(rec.id)
            if bill:
                it["bill_id"] = bill.id
                it["dp_amount"] = float(bill.dp_amount or 0.0)
                it["is_dp"] = bool(bill.is_dp)
                it["name_waiters"] = bill.name_waiters or it["name_waiters"]
                it["name_customer"] = bill.name_customer or it["name_customer"]
            else:
                it["bill_id"] = None
                it["dp_amount"] = 0.0
                it["is_dp"] = False

            it["company_id"] = rec.company_id.id if rec.company_id else None
            it["company_name"] = rec.company_id.name if rec.company_id else None

            # optional lines
            if include_lines:
                it["lines"] = [{
                    "id": l.id,
                    "product_id": l.product_id.id if l.product_id else None,
                    "product_name": l.product_id.display_name if l.product_id else None,
                    "qty": l.qty,
                    "price_unit": l.price_unit,
                    "discount": l.discount,
                    "price_subtotal": l.price_subtotal,
                    "price_subtotal_incl": l.price_subtotal_incl,
                } for l in rec.lines]

            # optional payments
            if include_payments:
                payments = getattr(rec, "payment_ids", False)
                it["payments"] = [{
                    "id": p.id,
                    "payment_method_id": p.payment_method_id.id if p.payment_method_id else None,
                    "payment_method_name": p.payment_method_id.name if p.payment_method_id else None,
                    "amount": p.amount,
                    "payment_date": fields.Datetime.to_string(getattr(p, "payment_date", None)) if getattr(p, "payment_date", None) else None,
                } for p in payments] if payments else []

        return {
            "success": True,
            "data": {
                "items": items,
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        }
        
    def _count_orders(self, env, params):
        config_id = self._parse_int(params.get("config_id"))
        state = params.get("state") or "draft"

        if not config_id:
            return self._err("Missing config_id", 400)

        domain = [
            ("state", "=", state),
            ("session_id.config_id", "=", config_id),
        ]

        count = env["pos.order"].search_count(domain)

        return {
            "success": True,
            "data": {
                "draft_count": count
            }
    }

    
    def _cancel_order(self, env, order_id):
        order = env["pos.order"].browse(int(order_id))
        if not order.exists():
            return self._err("Order not found", 404)

        # hanya boleh cancel draft
        if order.state != "draft":
            return self._err(
                f"Order cannot be canceled because state is '{order.state}'",
                409,
                code="ORDER_NOT_DRAFT",
                data={"id": order.id, "state": order.state}
            )

        try:
            # Odoo pos.order biasanya punya action_pos_order_cancel()
            if hasattr(order, "action_pos_order_cancel"):
                order.action_pos_order_cancel()
            else:
                # fallback (kalau versi kamu beda)
                order.write({"state": "cancel"})

        except Exception as e:
            _logger.exception("CANCEL ORDER ERROR")
            return self._err(str(e), 400)

        return {
            "success": True,
            "data": {
                "id": order.id,
                "name": order.name,
                "pos_reference": order.pos_reference,
                "state": order.state,
            }
        }

    def _list_draft_orders(self, env, params):
        session_id = self._parse_int(params.get("session_id"))
        config_id = self._parse_int(params.get("config_id"))
        limit = self._parse_int(params.get("limit"), 50)
        offset = self._parse_int(params.get("offset"), 0)

        if not config_id and not session_id:
            return self._err("Missing config_id or session_id", 400)

        domain = [("state", "=", "draft")]

        if session_id:
            domain.append(("session_id", "=", session_id))
        if config_id:
            domain.append(("session_id.config_id", "=", config_id))

        PosOrder = env["pos.order"]
        total = PosOrder.search_count(domain)

        orders = PosOrder.search(domain, order="date_order desc, id desc", limit=limit, offset=offset)

        items = []
        for o in orders:
            items.append({
                "id": o.id,
                "name": o.name,
                "pos_reference": o.pos_reference,
                "date_order": fields.Datetime.to_string(o.date_order) if o.date_order else None,
                "state": o.state,
                "session_id": o.session_id.id if o.session_id else None,
                "session_name": o.session_id.name if o.session_id else None,
                "amount_total": o.amount_total,
                "amount_paid": o.amount_paid,
                "user_id": o.user_id.id if o.user_id else None,
                "user_name": o.user_id.name if o.user_id else None,
            })

        return {
            "success": True,
            "data": {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        }

    
    
    @http.route(
    "/api/pos/session/can_close",
    type="http",
    auth="none",
    methods=["GET", "OPTIONS"],
    csrf=False
    )
    def pos_session_can_close(self, **kw):
        # CORS preflight
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
            ])

        try:
            api_env = self._api_env(request.env)

            session_id = kw.get("id") or kw.get("Id") or kw.get("session_id")
            if not session_id:
                return self._resp(self._err("Missing session_id", 400), 400)

            include_drafts = str(kw.get("include_drafts") or "0").lower() in ("1", "true", "yes")

            result = self._can_close_session(api_env, int(session_id), include_drafts=include_drafts)
            return self._resp(result, result.get("status", 200))

        except Exception as e:
            _logger.exception("CAN CLOSE SESSION ERROR")
            return self._resp(self._err(str(e), 400), 400)

    
    def _fix_order_line_uom(self, env, order):
        if not order or not order.exists():
            return

        order = order.sudo()
        Line = env["pos.order.line"].sudo()

        # cari nama field uom yang benar di model kamu
        uom_field = None
        for f in ("uom_id", "product_uom_id"):
            if f in Line._fields:
                uom_field = f
                break
        if not uom_field:
            _logger.warning("No UoM field found on pos.order.line")
            return

        for line in order.lines:
            prod = line.product_id
            if not prod or not prod.uom_id:
                continue

            line_uom = getattr(line, uom_field, False)
            prod_uom = prod.uom_id

            # mismatch kategori => paksa pakai uom product
            if (not line_uom) or (line_uom.category_id.id != prod_uom.category_id.id):
                _logger.warning(
                    "FIX UOM order=%s line=%s product=%s line_uom=%s(%s) -> prod_uom=%s(%s)",
                    order.id, line.id,
                    prod.display_name,
                    line_uom.name if line_uom else None,
                    line_uom.category_id.name if line_uom and line_uom.category_id else None,
                    prod_uom.name,
                    prod_uom.category_id.name if prod_uom.category_id else None,
                )
                line.write({uom_field: prod_uom.id})

    
    def _can_close_session(self, env, session_id, include_drafts=False):
        session = env["pos.session"].browse(int(session_id))
        if not session.exists():
            return self._err("Session not found", 404)

        # cari draft orders pada session ini (lintas hari)
        draft_orders = env["pos.order"].search([
            ("session_id", "=", session.id),
            ("state", "=", "draft"),
        ], order="date_order desc, id desc")

        draft_total = len(draft_orders)
        can_close = (draft_total == 0)

        data = {
            "session_id": session.id,
            "session_name": session.name,
            "state": session.state,
            "can_close": can_close,
            "draft_total": draft_total,
        }

        if include_drafts and draft_total:
            data["draft_items"] = [{
                "id": o.id,
                "name": o.name,
                "pos_reference": o.pos_reference,
                "date_order": fields.Datetime.to_string(o.date_order) if o.date_order else None,
                "amount_total": o.amount_total,
            } for o in draft_orders[:50]]  # limit ringkas

        return {"success": True, "data": data}

    
    def _create_order(self, env, body):
        session_id = self._parse_int(body.get("session_id"))
        partner_id = self._parse_int(body.get("partner_id"))
        waiter_name = (body.get("name_waiters") or "").strip()
        lines = body.get("lines") or []

        # ========= table wajib =========
        table_id = self._parse_int(body.get("table_id"))
        if not table_id:
            return self._err("Missing table_id (meja belum dipilih)", 400)

        table = env["restaurant.table"].browse(table_id)
        if not table.exists():
            return self._err("Table not found", 404)

        # ========= basic validate =========
        if not session_id:
            return self._err("Missing session_id", 400)
        if not isinstance(lines, list) or not lines:
            return self._err("Missing lines", 400)

        session = env["pos.session"].browse(session_id)
        if not session.exists():
            return self._err("Session not found", 404)

        if session.state not in ("opened", "opening_control"):
            return self._err(
                f"Session not active (state={session.state})",
                409,
                code="SESSION_NOT_OPENED",
                data={"session_id": session.id, "state": session.state}
            )

        partner = False
        if partner_id:
            partner = env["res.partner"].browse(partner_id)
            if not partner.exists():
                return self._err("Partner not found", 404)

        PosOrder = env["pos.order"]
        if "table_id" not in PosOrder._fields:
            return self._err("pos.order has no field table_id (restaurant module?)", 500)

        PosLine = env["pos.order.line"]

        # ====== ORDER header fields ======
        has_general_note = "general_note" in PosOrder._fields
        # ✅ field baru
        has_change_amount = "change_amount" in PosOrder._fields

        # ====== line fields ======
        has_uom = "uom_id" in PosLine._fields
        has_price_subtotal = "price_subtotal" in PosLine._fields
        has_price_subtotal_incl = "price_subtotal_incl" in PosLine._fields

        # ✅ target utama kamu
        has_customer_note = "customer_note" in PosLine._fields
        # fallback legacy
        has_line_note = "note" in PosLine._fields

        # Kalau kamu MAU juga copy ke general note, set True (default False)
        copy_line_notes_to_general_note = bool(body.get("copy_line_notes_to_general_note", False))

        # ✅ ambil change_amount dari payload
        try:
            change_amount = float(body.get("change_amount") or 0.0)
        except Exception:
            return self._err("Invalid change_amount", 400)

        _logger.warning(
            "DEBUG change_amount: has_field=%s raw_body=%r parsed=%s",
            has_change_amount, body.get("change_amount"), change_amount
        )

        order_line_cmds = []
        general_notes = []
        total = 0.0
        tax = 0.0
        line_no = 0

        # Simpan mapping note dari payload sesuai urutan line
        # supaya setelah create kita bisa "force write" ke customer_note
        payload_notes_by_index = []  # list[str] sejajar dengan order_line_cmds

        for ln in lines:
            if not isinstance(ln, dict):
                return self._err("Invalid line format", 400)

            product_id = self._parse_int(ln.get("product_id"))
            if not product_id:
                return self._err("Line missing product_id", 400)

            product = env["product.product"].browse(product_id)
            if not product.exists():
                return self._err("Product not found", 404)

            try:
                qty = float(ln.get("qty", 0))
                price_unit = float(ln.get("price_unit", 0))
                discount = float(ln.get("discount") or 0)
            except Exception:
                return self._err("Invalid qty / price / discount", 400)

            if qty <= 0:
                return self._err("Line qty must be > 0", 400)

            effective_unit = price_unit * (1.0 - (discount / 100.0))
            subtotal = effective_unit * qty
            subtotal_incl = subtotal  # tax = 0

            note_txt = (ln.get("note") or "").strip()
            base_name = (product.display_name or product.name or "").strip() or "Item"

            line_no += 1
            if copy_line_notes_to_general_note and note_txt:
                general_notes.append(f"{line_no}. {base_name}: {note_txt}")

            line_vals = {
                "product_id": product_id,
                "qty": qty,
                "price_unit": price_unit,
                "discount": discount,
                "name": base_name,
            }

            if has_uom and product.uom_id:
                line_vals["uom_id"] = product.uom_id.id

            if has_price_subtotal:
                line_vals["price_subtotal"] = subtotal
            if has_price_subtotal_incl:
                line_vals["price_subtotal_incl"] = subtotal_incl

            # ✅ coba isi saat create (best effort)
            if note_txt:
                if has_customer_note:
                    line_vals["customer_note"] = note_txt
                elif has_line_note:
                    line_vals["note"] = note_txt
                else:
                    line_vals["name"] = f"{base_name}\n{note_txt}"

            order_line_cmds.append((0, 0, line_vals))
            payload_notes_by_index.append(note_txt)  # simpan selalu (empty string juga)
            total += subtotal_incl

        order_vals = {
            "session_id": session.id,
            "partner_id": partner.id if partner else False,
            "table_id": table_id,
            "name_waiters": waiter_name,
            "lines": order_line_cmds,
            "amount_tax": tax,
            "amount_total": total,
            "amount_paid": 0.0,
            "amount_return": 0.0,
        }

        if has_general_note and copy_line_notes_to_general_note and general_notes:
            order_vals["general_note"] = "\n".join(general_notes)

        # ✅ masukkan change_amount kalau field-nya ada
        if has_change_amount:
            order_vals["change_amount"] = change_amount

        try:
            company = session.company_id
            PosOrderX = PosOrder.sudo().with_company(company).with_context(allowed_company_ids=[company.id])
            order_vals["company_id"] = company.id
            has_pos_reference = "pos_reference" in PosOrder._fields

            client_ref = (body.get("client_ref") or "").strip()  # dari app
            if client_ref:
                if has_pos_reference:
                    order_vals["pos_reference"] = client_ref
                # kalau kamu MAU paksa jadi name:
                order_vals["name"] = client_ref
            # ===== create order =====
            order = PosOrderX.create(order_vals)
            env.cr.flush()
            order = PosOrderX.browse(order.id)

            # ===== fallback SQL kalau ORM create kosong =====
            if not order or not getattr(order, "id", False) or not order.exists():
                _logger.error(
                    "ORM CREATE returned empty, using SQL fallback. session_id=%s table_id=%s lines_len=%s",
                    session.id, table_id, len(order_line_cmds)
                )

                general_note_text = None
                if has_general_note and copy_line_notes_to_general_note and general_notes:
                    general_note_text = "\n".join(general_notes)

                order = self._sql_create_order_fallback(
                    env=env,
                    session=session,
                    partner=partner,
                    table_id=table_id,
                    order_line_cmds=order_line_cmds,
                    total=total,
                    tax=tax,
                    general_note_text=general_note_text,
                )

            if not order or not order.exists():
                _logger.error("CREATE ORDER FAILED: fallback also failed. session_id=%s table_id=%s", session.id, table_id)
                return self._err("Failed to create order", 500)

            env["pos.order"].flush_model()
            env["pos.order.line"].flush_model()

            if not order.lines:
                _logger.error("CREATE ORDER FAILED: order created but lines empty. order_id=%s", order.id)
                return self._err("Failed to create order (lines empty)", 500)

            # ======================================================
            # ✅ FORCE WRITE NOTE KE LINE (BIAR 100% MASUK)
            # ======================================================
            try:
                # order.lines biasanya urut create order_line_cmds,
                # tapi untuk aman, kita sort by id asc (paling dekat ke urutan insert)
                order_lines = order.lines.sorted(lambda l: l.id)

                # jumlah harusnya sama. kalau beda, tetap best-effort sampai min
                n = min(len(order_lines), len(payload_notes_by_index))

                if has_customer_note or has_line_note:
                    for i in range(n):
                        note_txt = (payload_notes_by_index[i] or "").strip()
                        if not note_txt:
                            continue

                        l = order_lines[i].sudo()
                        vals = {}

                        if has_customer_note:
                            # hanya write kalau belum keisi / beda
                            if (l.customer_note or "").strip() != note_txt:
                                vals["customer_note"] = note_txt
                        elif has_line_note:
                            if (l.note or "").strip() != note_txt:
                                vals["note"] = note_txt

                        if vals:
                            l.write(vals)

            except Exception:
                _logger.exception("FORCE WRITE line notes failed (non-fatal)")

            # ======================================================
            # ✅ FORCE WRITE CHANGE_AMOUNT KE ORDER (BIAR 100% MASUK)
            # Ini backstop terakhir: gak peduli order dibuat lewat ORM
            # create() biasa atau lewat SQL fallback, di sini kita
            # pastikan change_amount ke-set langsung via write().
            # ======================================================
            if has_change_amount:
                try:
                    order_sudo = order.sudo()
                    current_val = float(order_sudo.change_amount or 0.0)
                    if current_val != change_amount:
                        order_sudo.write({"change_amount": change_amount})
                        env["pos.order"].flush_model()
                        _logger.warning(
                            "FORCE WRITE change_amount OK. order_id=%s before=%s after=%s",
                            order.id, current_val, change_amount
                        )
                except Exception:
                    _logger.exception("FORCE WRITE change_amount failed (non-fatal). order_id=%s", order.id)

            # reload final
            order = PosOrder.sudo().browse(order.id)

            return {
                "success": True,
                "status": 200,
                "data": self._order_to_dict(order, include_lines=True, include_payments=False),
            }

        except Exception:
            _logger.exception("CREATE ORDER FAILED")
            return self._err("Failed to create order", 400)
        
             
    def _order_to_dict(self, order, include_lines=True, include_payments=False):
        if not order or not order.exists():
            return {
                "id": False,
                "name": False,
                "name_waiters": "",
                "pos_reference": False,
                "date_order": None,
                "state": False,
                "session_id": None,
                "session_name": None,
                "partner_id": None,
                "partner_name": None,
                "user_id": None,
                "user_name": None,
                "company_id": None,
                "company_name": None,
                "amount_total": 0.0,
                "amount_tax": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
                "bill_id": None,
                "dp_amount": 0.0,
                "is_dp": False,
                "lines": [],
            }

        order = order.sudo()
        data = {
            "id": order.id,
            "name": order.name,
            "name_waiters": order.name_waiters,
            "pos_reference": getattr(order, "pos_reference", False),
            "date_order": order.date_order.isoformat() if order.date_order else None,
            "state": order.state,
            "session_id": order.session_id.id if order.session_id else None,
            "session_name": order.session_id.name if order.session_id else None,
            "partner_id": order.partner_id.id if order.partner_id else None,
            "partner_name": order.partner_id.name if order.partner_id else None,
            "user_id": order.user_id.id if order.user_id else None,
            "user_name": order.user_id.name if order.user_id else None,
            "company_id": order.company_id.id if order.company_id else None,
            "company_name": order.company_id.name if order.company_id else None,
            "amount_total": float(order.amount_total or 0.0),
            "amount_tax": float(order.amount_tax or 0.0),
            "amount_paid": float(order.amount_paid or 0.0),
            "amount_return": float(order.amount_return or 0.0),
            "bill_id": None,
            "dp_amount": 0.0,
            "is_dp": False,
            "lines": [],
        }
        try:
            bill = request.env["poskas.bill"].sudo().search([
                ("pos_order_id", "=", order.id)
            ], limit=1)

            if bill:
                data["bill_id"] = bill.id
                data["dp_amount"] = float(bill.dp_amount or 0.0)
                data["is_dp"] = bool(bill.is_dp)
        except Exception:
            _logger.exception("FAILED GET BILL DP order_id=%s", order.id)
        if include_lines:
            for l in order.lines:
                data["lines"].append({
                    "id": l.id,
                    "product_id": l.product_id.id if l.product_id else None,
                    "product_name": l.product_id.display_name if l.product_id else None,
                    "qty": float(l.qty or 0.0),
                    "price_unit": float(l.price_unit or 0.0),
                    "discount": float(l.discount or 0.0),
                    "note": getattr(l, "note", False) or False,
                    "name": l.name,
                    "price_subtotal": float(getattr(l, "price_subtotal", 0.0) or 0.0),
                    "price_subtotal_incl": float(getattr(l, "price_subtotal_incl", 0.0) or 0.0),
                })

        return data

    def _get_fallback_partner(self, api_env, session):
        cfg = session.config_id
        fallback = None

        # 1) dari field config (kalau ada)
        for fn in ("default_partner_id", "anonymous_partner_id", "walkin_partner_id", "default_customer_id"):
            try:
                if cfg and hasattr(cfg, "_fields") and fn in cfg._fields and getattr(cfg, fn):
                    fallback = getattr(cfg, fn)
                    break
            except Exception:
                pass

        # 2) cari partner "Customer" / "Walk-in" by name (case kamu ketemu "customer")
        if not fallback:
            fallback = api_env["res.partner"].sudo().search(
                [("name", "ilike", "customer"), ("company_id", "in", [False, session.company_id.id])],
                limit=1,
            )

        # 3) last fallback: partner mana saja di company (biar tidak kosong)
        if not fallback:
            fallback = api_env["res.partner"].sudo().search(
                [("company_id", "in", [False, session.company_id.id])],
                limit=1
            )

        return fallback

    
    def _pay_order(self, env, order_id, body):
            order_id = self._parse_int(order_id)
            session_id = self._parse_int(body.get("session_id"))
            pm_id = self._parse_int(body.get("payment_method_id"))
            ref = (body.get("ref") or "").strip()

            if not order_id:
                return self._err("Missing order_id", 400)
            if not session_id:
                return self._err("Missing session_id", 400)
            if not pm_id:
                return self._err("Missing payment_method_id", 400)

            try:
                amount = float(body.get("amount", 0) or 0)
            except Exception:
                return self._err("Invalid amount", 400)

            Order = env["pos.order"]
            order = Order.browse(order_id)
            if not order.exists():
                return self._err("Order not found", 404)

            # =========================
            # HANDLE TOTAL = 0 (diskon 100%)
            # =========================
            currency = getattr(order, "currency_id", None)
            total0 = float(order.amount_total or 0.0)

            is_zero_total = False
            if currency:
                is_zero_total = (currency.compare_amounts(total0, 0.0) == 0)
            else:
                is_zero_total = abs(total0) < 1e-9

            if is_zero_total:
                # finalize tanpa payment walaupun amount=0
                vals = {}
                if "amount_paid" in order._fields:
                    vals["amount_paid"] = 0.0
                if "amount_return" in order._fields:
                    vals["amount_return"] = 0.0
                if vals:
                    order.write(vals)
                    env.cr.flush()
                    if hasattr(order, "invalidate_recordset"):
                        order.invalidate_recordset()

                try:
                    order.with_context(
                        active_model="pos.order",
                        active_id=order.id,
                        default_pos_order_id=order.id,
                        pos_order_id=order.id,
                    ).action_pos_order_paid()
                except Exception:
                    if "state" in order._fields:
                        order.write({"state": "paid"})

                env.cr.flush()
                if hasattr(order, "invalidate_recordset"):
                    order.invalidate_recordset()

                try:
                    bill_id = self._parse_int(body.get("bill_id"))
                    if bill_id:
                        bill = env["poskas.bill"].sudo().browse(bill_id)
                        if bill.exists():
                            bill.write({
                                "pos_order_id": order.id,
                                "state": "paid",
                            })
                except Exception:
                    _logger.exception("FAILED LINK BILL TO ORDER ZERO TOTAL order_id=%s", order.id)
                    
                return {
                    "success": True,
                    "data": {
                        "order_id": order.id,
                        "amount_total": 0.0,
                        "amount_paid": 0.0,
                        "amount_return": 0.0,
                        "state": getattr(order, "state", "paid"),
                        "payments": [],
                        "note": "Zero total (100% discount) - finalized without payment",
                    }
                }

            # =========================
            # VALIDASI AMOUNT NORMAL
            # =========================
            if amount <= 0:
                return self._err("Amount must be > 0", 400)


        

            Order = env["pos.order"]
            order = Order.browse(order_id)
            if not order.exists():
                return self._err("Order not found", 404)

            session = env["pos.session"].browse(session_id)
            if not session.exists():
                return self._err("Session not found", 404)

            if getattr(order, "session_id", False) and order.session_id.id != session.id:
                return self._err("Order session mismatch", 409)

            pm = env["pos.payment.method"].browse(pm_id)
            if not pm.exists():
                return self._err("Payment method not found", 404)

            if "pos.payment" not in env.registry.models:
                return self._err("Model pos.payment not available", 500)

            Payment = env["pos.payment"]

            # ----------------------------
            # compatibility helpers
            # ----------------------------
            def _invalidate(rec):
                """Compat: invalidate cache/recordset."""
                try:
                    # Odoo lama/beda bisa punya salah satu dari ini
                    if hasattr(rec, "invalidate_recordset"):
                        rec.invalidate_recordset()
                    elif hasattr(rec, "invalidate_cache"):
                        rec.invalidate_cache()
                    elif hasattr(env, "cache") and hasattr(env.cache, "invalidate"):
                        # best-effort
                        env.cache.invalidate()
                except Exception:
                    pass

            def _flush():
                try:
                    env.cr.flush()
                except Exception:
                    pass

            def _read_money_snapshot():
                _invalidate(order)
                fields_to_read = ["amount_total"]
                if "amount_paid" in order._fields:
                    fields_to_read.append("amount_paid")
                if "amount_return" in order._fields:
                    fields_to_read.append("amount_return")
                if "state" in order._fields:
                    fields_to_read.append("state")

                od = order.read(fields_to_read)[0]
                total_ = float(od.get("amount_total") or 0.0)
                paid_ = float(od.get("amount_paid") or 0.0) if "amount_paid" in order._fields else None
                ret_ = float(od.get("amount_return") or 0.0) if "amount_return" in order._fields else None
                state_ = od.get("state") if "state" in order._fields else getattr(order, "state", None)
                return total_, paid_, ret_, state_

            def _compute_paid_total_from_payments():
                _invalidate(order)
                if "payment_ids" in order._fields:
                    return float(sum(order.payment_ids.mapped("amount")) if order.payment_ids else 0.0)
                if "amount_paid" in order._fields:
                    return float(order.amount_paid or 0.0)
                return 0.0

            # ============================================================
            # 1) CREATE PAYMENT (add_payment -> SQL fallback)
            # ============================================================
            pay_id = None

            # A) coba add_payment (kalau ada)
            add_payment_ok = False
            if hasattr(order, "add_payment"):
                try:
                    with env.cr.savepoint():
                        vals = {"payment_method_id": pm.id, "amount": amount}
                        if ref:
                            vals["payment_name"] = ref
                        order_ctx = order.with_context(
                            active_model="pos.order",
                            active_id=order.id,
                            default_pos_order_id=order.id,
                            pos_order_id=order.id,
                        )
                        order_ctx.add_payment(vals)
                        _flush()
                        _invalidate(order)
                        add_payment_ok = True
                except Exception:
                    _logger.exception("add_payment failed; will fallback to SQL")

            # B) Kalau add_payment tidak sukses, LANGSUNG SQL (karena ORM kamu terbukti insert NULL pos_order_id)
            if not add_payment_ok:
                try:
                    with env.cr.savepoint():
                        pay_id = self._sql_insert_pos_payment(env, order, pm, amount, ref=ref)
                        _flush()
                        _invalidate(order)
                except psycopg2.Error as e:
                    _logger.exception("SQL pos_payment insert failed: order=%s err=%s", order.id, e)
                    return self._err(str(e), 400)
                except Exception as e:
                    _logger.exception("SQL pos_payment insert failed (non-db): order=%s err=%s", order.id, e)
                    return self._err(str(e), 400)

            # ============================================================
            # 2) RECOMPUTE paid/return (fresh)
            # ============================================================
            total, paid_read, ret_read, _state = _read_money_snapshot()

            if paid_read is None:
                paid = _compute_paid_total_from_payments()
            else:
                paid = float(paid_read or 0.0)
                if paid <= 0 and amount > 0:
                    paid = max(paid, _compute_paid_total_from_payments())

            change = max(0.0, paid - total)

            # update amount_paid/return kalau ada
            write_vals = {}
            if "amount_paid" in order._fields:
                write_vals["amount_paid"] = paid
            if "amount_return" in order._fields:
                write_vals["amount_return"] = change

            if write_vals:
                try:
                    with env.cr.savepoint():
                        order.write(write_vals)
                        _flush()
                        _invalidate(order)
                except Exception as e:
                    _logger.exception("ORDER WRITE PAID/RETURN FAILED: order=%s err=%s", order.id, e)
                    return self._err(str(e), 400)

            # ============================================================
            # 3) FINALIZE kalau lunas (rounding currency)
            # ============================================================
            bill_id = self._parse_int(body.get("bill_id"))

            currency = getattr(order, "currency_id", None)

            if bill_id:
                bill = env["poskas.bill"].sudo().browse(bill_id)

                if bill.exists():
                    is_paid = True

                    _logger.warning(
                        "FORCE PAID FROM BILL order=%s bill=%s paid=%s total=%s",
                        order.id,
                        bill.id,
                        paid,
                        total,
                    )
                else:
                    if currency:
                        is_paid = currency.compare_amounts(paid, total) >= 0
                    else:
                        is_paid = (paid + 1e-9) >= total

            else:
                if currency:
                    is_paid = currency.compare_amounts(paid, total) >= 0
                else:
                    is_paid = (paid + 1e-9) >= total
                    
                    
            if is_paid:
                try:
                    with env.cr.savepoint():
                        total2, paid2, ret2, _ = _read_money_snapshot()
                        v = {}
                        if "amount_paid" in order._fields:
                            v["amount_paid"] = float(paid2 or paid)
                        if "amount_return" in order._fields:
                            v["amount_return"] = float(ret2 or change)
                        if v:
                            order.write(v)
                            _flush()
                            _invalidate(order)

                        currency = order.currency_id
                        total = float(order.amount_total or 0.0)

                        # hitung ulang paid dari payment_ids (INI PENTING)
                        paid = sum(order.payment_ids.mapped("amount")) if order.payment_ids else 0.0
                        change = max(0.0, paid - total)
                        net_paid = paid - change  # INI yang dipakai Odoo

                        # pastikan field tersimpan dulu
                        vals = {}
                        if "amount_paid" in order._fields:
                            vals["amount_paid"] = paid
                        if "amount_return" in order._fields:
                            vals["amount_return"] = change

                        if vals:
                            order.write(vals)
                            env.cr.flush()
                            if hasattr(order, "invalidate_recordset"):
                                order.invalidate_recordset()

                        # check lunas ala Odoo
                        is_paid = currency.compare_amounts(net_paid, total) >= 0

                        if is_paid:
                            try:
                                order.with_context(
                                    active_model="pos.order",
                                    active_id=order.id,
                                    default_pos_order_id=order.id,
                                    pos_order_id=order.id,
                                ).action_pos_order_paid()
                            except UserError as ue:
                                _logger.warning(
                                    "action_pos_order_paid blocked, fallback state=paid: order=%s err=%s",
                                    order.id, ue
                                )
                                if "state" in order._fields:
                                    order.write({"state": "paid"})
                        elif hasattr(order, "action_paid"):
                            order.action_paid()
                        elif "state" in order._fields:
                            order.write({"state": "paid"})

                        # TARUH DI SINI
                        try:
                            bill_id = self._parse_int(body.get("bill_id"))
                            if bill_id:
                                bill = env["poskas.bill"].sudo().browse(bill_id)
                                if bill.exists():
                                    bill.write({
                                        "pos_order_id": order.id,
                                        "state": "paid",
                                    })
                        except Exception:
                            _logger.exception("FAILED LINK BILL TO ORDER order_id=%s", order.id)

                        _flush()
                        _invalidate(order)

                except UserError as ue:
                    t3, p3, r3, st3 = _read_money_snapshot()
                    if p3 is None:
                        p3 = _compute_paid_total_from_payments()
                    _logger.warning(
                        "PAY not fully paid per Odoo: order=%s paid=%s total=%s return=%s state=%s err=%s",
                        order.id, p3, t3, r3, st3, ue
                    )
                    return self._err(str(ue), 409, code="ORDER_NOT_FULLY_PAID", data={
                        "order_id": order.id,
                        "amount_total": float(t3),
                        "amount_paid": float(p3),
                        "amount_return": float(r3 or 0.0),
                        "state": st3,
                    })
                except Exception as e:
                    _logger.exception("FINALIZE ORDER PAID FAILED: order=%s err=%s", order.id, e)
                    return self._err(str(e), 400)

            # ============================================================
            # 4) RESPONSE
            # ============================================================
            fields_to_read = ["state", "amount_total"]
            if "amount_paid" in order._fields:
                fields_to_read.append("amount_paid")
            if "amount_return" in order._fields:
                fields_to_read.append("amount_return")
            order_data = order.read(fields_to_read)[0]

            payments_out = []
            if "payment_ids" in order._fields and order.payment_ids:
                for p in order.payment_ids:
                    payments_out.append({
                        "id": p.id,
                        "payment_method_id": p.payment_method_id.id if getattr(p, "payment_method_id", False) else None,
                        "payment_method_name": p.payment_method_id.display_name if getattr(p, "payment_method_id", False) else None,
                        "amount": float(p.amount or 0.0),
                        "ref": getattr(p, "payment_reference", None) or getattr(p, "ref", None) or None,
                    })
            else:
                payments_out.append({
                    "id": pay_id,
                    "payment_method_id": pm.id,
                    "payment_method_name": pm.display_name,
                    "amount": float(amount),
                    "ref": ref or None,
                })

            total_final = float(order_data.get("amount_total") or total or 0.0)
            paid_final = float(order_data.get("amount_paid") or 0.0) if "amount_paid" in order._fields else _compute_paid_total_from_payments()
            return_final = float(order_data.get("amount_return") or 0.0) if "amount_return" in order._fields else max(0.0, paid_final - total_final)

            return {
                "success": True,
                "data": {
                    "order_id": order.id,
                    "amount_total": total_final,
                    "amount_paid": paid_final,
                    "amount_return": return_final,
                    "state": order_data.get("state") or getattr(order, "state", None),
                    "payments": payments_out,
                }
            }

    def _sql_create_order_fallback(self, env, session, partner, table_id, order_line_cmds, total, tax, general_note_text=None):
        cr = env.cr

        config = session.config_id
        company = session.company_id
        user = session.user_id or env.user

        # name / pos_reference
        try:
            name = env["ir.sequence"].sudo().next_by_code("pos.order") or "/"
        except Exception:
            name = "/"

        now_utc = fields.Datetime.now()

        # ---------- INSERT pos_order (dynamic cols) ----------
        cols = [
            "name", "date_order", "state",
            "session_id", "config_id", "company_id", "user_id", "partner_id",
            "amount_total", "amount_tax", "amount_paid", "amount_return",
            "create_date", "write_date",
        ]
        vals = [
            name, now_utc, "draft",
            session.id, config.id, company.id, user.id, (partner.id if partner else None),
            float(total or 0.0), float(tax or 0.0), 0.0, 0.0,
            now_utc, now_utc,
        ]

        # optional columns
        if self._sql_has_col(env, "pos_order", "table_id"):
            cols.append("table_id")
            vals.append(int(table_id))

        if general_note_text and self._sql_has_col(env, "pos_order", "general_note"):
            cols.append("general_note")
            vals.append(general_note_text)

        sql = f"INSERT INTO pos_order ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(vals))}) RETURNING id"
        cr.execute(sql, tuple(vals))
        order_id = cr.fetchone()[0]

        # ---------- INSERT pos_order_line ----------
        has_company_line = self._sql_has_col(env, "pos_order_line", "company_id")
        has_subtotal = self._sql_has_col(env, "pos_order_line", "price_subtotal")
        has_subtotal_incl = self._sql_has_col(env, "pos_order_line", "price_subtotal_incl")

        for cmd in order_line_cmds:
            line_vals = (cmd and len(cmd) >= 3 and cmd[2]) or {}
            product_id = int(line_vals.get("product_id"))
            qty = float(line_vals.get("qty") or 0.0)
            price_unit = float(line_vals.get("price_unit") or 0.0)
            discount = float(line_vals.get("discount") or 0.0)
            name_line = line_vals.get("name") or ""

            # hitung subtotal
            price_subtotal = float(line_vals.get("price_subtotal") or (price_unit * qty))
            price_subtotal_incl = float(line_vals.get("price_subtotal_incl") or price_subtotal)

            line_cols = [
                "order_id", "product_id", "name",
                "qty", "price_unit", "discount",
                "create_date", "write_date",
            ]
            line_params = [
                order_id, product_id, name_line,
                qty, price_unit, discount,
                now_utc, now_utc,
            ]

            if has_subtotal:
                line_cols.append("price_subtotal")
                line_params.append(price_subtotal)

            if has_subtotal_incl:
                line_cols.append("price_subtotal_incl")
                line_params.append(price_subtotal_incl)

            if has_company_line:
                line_cols.append("company_id")
                line_params.append(company.id)

            line_sql = f"INSERT INTO pos_order_line ({', '.join(line_cols)}) VALUES ({', '.join(['%s']*len(line_params))})"
            cr.execute(line_sql, tuple(line_params))

        # flush (bukan commit)
        env.cr.flush()

        return env["pos.order"].sudo().browse(order_id)
    
    
    def _sql_has_col(self, env, table, col, schema="public"):
        env.cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = %s
           AND table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (schema, table, col),
        )
        return bool(env.cr.fetchone())


    def _sql_insert_pos_payment(self, env, order, pm, amount, ref=None):
        from odoo import fields

        now = fields.Datetime.now()
        uid = env.uid
        company_id = order.company_id.id if getattr(order, "company_id", False) else env.company.id

        cols = ["pos_order_id", "payment_method_id", "amount", "create_uid", "write_uid", "create_date", "write_date"]
        vals = [order.id, pm.id, amount, uid, uid, now, now]

        # optional kolom (kompatibel berbagai DB schema)
        if self._sql_has_col(env, "pos_payment", "company_id"):
            cols.append("company_id")
            vals.append(company_id)

        if self._sql_has_col(env, "pos_payment", "payment_date"):
            cols.append("payment_date")
            vals.append(now)

        if ref:
            for c in ("payment_reference", "ref", "name", "payment_name"):
                if self._sql_has_col(env, "pos_payment", c):
                    cols.append(c)
                    vals.append(ref)
                    break

        q = f'INSERT INTO pos_payment ({",".join(cols)}) VALUES ({",".join(["%s"]*len(cols))}) RETURNING id'
        env.cr.execute(q, tuple(vals))
        return env.cr.fetchone()[0]


    def _sql_insert_pos_payment(self, env, order, pm, amount, ref=None):
        now = fields.Datetime.now()
        uid = env.uid
        company_id = order.company_id.id if getattr(order, "company_id", False) else env.company.id

        cols = ["pos_order_id", "payment_method_id", "amount", "create_uid", "write_uid", "create_date", "write_date"]
        vals = [order.id, pm.id, amount, uid, uid, now, now]

        # optional columns kalau ada di DB
        if self._sql_has_col(env, "pos_payment", "company_id"):
            cols.append("company_id")
            vals.append(company_id)

        # beberapa versi punya "payment_date"
        if self._sql_has_col(env, "pos_payment", "payment_date"):
            cols.append("payment_date")
            vals.append(now)

        # simpan ref kalau ada kolomnya
        if ref:
            for c in ("payment_reference", "ref", "name", "payment_name"):
                if self._sql_has_col(env, "pos_payment", c):
                    cols.append(c)
                    vals.append(ref)
                    break

        q = f'INSERT INTO pos_payment ({",".join(cols)}) VALUES ({",".join(["%s"]*len(cols))}) RETURNING id'
        env.cr.execute(q, tuple(vals))
        pid = env.cr.fetchone()[0]
        return pid


    def _find_payment_order_link_field(self, Payment):
        # prioritas nama yang umum
        for name in ("pos_order_id", "order_id", "pos_order", "order"):
            f = Payment._fields.get(name)
            if f and getattr(f, "type", None) == "many2one" and getattr(f, "comodel_name", None) == "pos.order":
                return name

        # fallback: scan semua field many2one ke pos.order
        for name, f in Payment._fields.items():
            if getattr(f, "type", None) == "many2one" and getattr(f, "comodel_name", None) == "pos.order":
                return name
        return None