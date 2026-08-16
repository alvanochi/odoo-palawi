from odoo import http, fields
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class PosBillApi(http.Controller):

    # ---------------------------
    # Helpers
    # ---------------------------
    def _api_env(self, env):
        service_uid = env.ref("base.user_admin").id
        return env(user=service_uid, su=True)

    def _resp(self, payload, status=200):
        body = json.dumps(payload, default=str)
        return request.make_response(body, headers=[
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
        ], status=status)

    def _err(self, msg, status=400, code=None, data=None):
        res = {"success": False, "message": msg, "status": status}
        if code:
            res["code"] = code
        if data is not None:
            res["data"] = data
        return res

    def _parse_json_body(self):
        raw = request.httprequest.data or b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _get_values(self, kw):
        method = request.httprequest.method.upper()
        data = {}
        if method in ("POST", "PUT"):
            data = self._parse_json_body()
            if data is None:
                return None, self._err("Invalid JSON body", 400)

        values = None
        if isinstance(data, dict):
            values = data.get("values")
            if values is None:
                values = data

        params = dict(kw)
        if values is not None:
            params["values"] = values
        return params, None

    # ---------------------------
    # CORS / Router
    # ---------------------------
    @http.route("/api/pos/bill/<string:action>", type="http", auth="none",
                methods=["GET", "POST", "PUT", "OPTIONS"], csrf=False)
    def pos_bill(self, action, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True, "message": "OK"}, 200)

        params, err = self._get_values(kw)
        if err:
            return self._resp(err, err["status"])

        env = self._api_env(request.env)

        try:
            if action == "open" and request.httprequest.method.upper() == "GET":
                res = self._open(env, params)
                return self._resp(res, res.get("status", 200))

            if action == "upsert" and request.httprequest.method.upper() == "POST":
                res = self._upsert(env, params)
                return self._resp(res, res.get("status", 200))

            if action == "move" and request.httprequest.method.upper() == "PUT":
                res = self._move(env, params)
                return self._resp(res, res.get("status", 200))

            if action == "cancel" and request.httprequest.method.upper() == "PUT":
                res = self._cancel(env, params)
                return self._resp(res, res.get("status", 200))

            if action == "open_list" and request.httprequest.method.upper() == "GET":
                res = self._open_list(env, params)
                return self._resp(res, res.get("status", 200))

            if action == "delete" and request.httprequest.method.upper() == "POST":
                res = self._delete(env, params)
                return self._resp(res, res.get("status", 200))

            return self._resp(self._err("Unsupported method/action", 405), 405)

        except Exception as e:
            _logger.exception("POS BILL API ERROR")
            return self._resp(self._err(str(e), 400), 400)

    # ---------------------------
    # Product snapshot helpers
    # ---------------------------
    def _resolve_table(self, env, raw_table):
        """Resolve raw table value from API into (table_id, table_ref).
        
        If raw_table is a valid restaurant.table record ID, returns (int_id, "").
        Otherwise returns (False, raw_string) so it's stored in table_ref.
        """
        if not raw_table:
            return False, ""
        raw_str = str(raw_table).strip()
        if not raw_str:
            return False, ""
        try:
            int_id = int(raw_str)
            table = env["restaurant.table"].browse(int_id)
            if table.exists():
                return int_id, ""
        except (ValueError, TypeError):
            pass
        # Not a valid restaurant.table ID → store as table_ref
        return False, raw_str

    def _bill_table_domain(self, table_id, table_ref):
        """Build domain fragment for matching bill by table."""
        if table_id:
            return ("table_id", "=", table_id)
        return ("table_ref", "=", table_ref)

    def _bill_table_vals(self, table_id, table_ref):
        """Build create/write values for table fields."""
        vals = {}
        if table_id:
            vals["table_id"] = table_id
            vals["table_ref"] = ""
        else:
            vals["table_id"] = False
            vals["table_ref"] = table_ref or ""
        return vals

    def _product_display_name(self, product):
        """Safe display name."""
        try:
            return product.display_name or product.name
        except Exception:
            try:
                return product.name
            except Exception:
                return None

    def _product_category_name(self, env, prod):
        categ_name = ""
        try:
            # misal product punya pos_categ_ids (Many2many)
            if hasattr(prod, "pos_categ_ids") and prod.pos_categ_ids:
                categ_name = prod.pos_categ_ids[0].name or ""
            # fallback ke public category / internal category kalau perlu
            elif hasattr(prod, "categ_id") and prod.categ_id:
                categ_name = prod.categ_id.display_name or prod.categ_id.name or ""
        except Exception:
            pass
        return (categ_name or "").strip() or None


    # ---------------------------
    # Actions
    # ---------------------------
   
    def _open(self, env, params):
        config_id = params.get("config_id")
        raw_table = params.get("table_id")
        if not config_id or not raw_table:
            return self._err("Missing config_id/table_id", 400)

        table_id, table_ref = self._resolve_table(env, raw_table)
        table_domain = self._bill_table_domain(table_id, table_ref)

        bill = env["poskas.bill"].search([
            ("config_id", "=", int(config_id)),
            table_domain,
            ("state", "=", "open"),
        ], limit=1, order="id desc")

        if not bill:
            return {"success": True, "has_open_bill": False, "data": None}

        return {"success": True, "has_open_bill": True, "data": self._serialize_bill(env, bill)}

    def _open_list(self, env, params):
        config_id = params.get("config_id")
        if not config_id:
            return self._err("Missing config_id", 400)

        bills = env["poskas.bill"].search([
            ("config_id", "=", int(config_id)),
            ("state", "=", "open"),
        ], order="write_date desc, id desc")

        data = [self._serialize_bill(env, b) for b in bills]
        return {"success": True, "type": "OK", "data": data}



    def _check_conflict(self, bill, if_match_write_date):
        if not if_match_write_date:
            return None
        server = fields.Datetime.to_string(bill.write_date)
        if server != if_match_write_date:
            return self._err(
                "Bill changed on server. Please refresh.",
                409,
                code="CONFLICT",
                data={"server_write_date": server}
            )
        return None

    def _apply_lines(self, env, bill, items):
        bill.line_ids.unlink()

        BillLine = env["poskas.bill.line"]
        Product = env["product.product"]

        for item in items:
            product_raw = item.get("product_id")
            qty = float(item.get("qty") or 0.0)
            note = item.get("note") or ""
            price_unit = float(item.get("unit_price") or 0.0)
            discount_percent = float(item.get("discount_percent") or 0.0)

            if qty <= 0:
                qty = 1.0

            if price_unit < 0.0:
                price_unit = 0.0

            if discount_percent < 0.0:
                discount_percent = 0.0
            if discount_percent > 100.0:
                discount_percent = 100.0

            product = Product.browse(int(product_raw))
            if not product.exists():
                continue

            BillLine.create({
                "bill_id": bill.id,
                "product_id": product.id,
                "qty": qty,
                "price_unit": price_unit,
                "note": note,
                "discount_percent": discount_percent,
            })

    def _set_dp_safe(self, bill, dp_amount, is_dp):
        dp_amount = float(dp_amount or 0.0)
        if dp_amount < 0:
            dp_amount = 0.0
        if dp_amount > 0:
            is_dp = True
        else:
            is_dp = False

        bill.write({
            "dp_amount": dp_amount,
            "is_dp": is_dp,
        })

    def _upsert(self, env, params):
        values = params.get("values") or {}
        try:
            config_id = int(values["config_id"])
            name_customer = str(values["name_customer"])
            raw_table = values.get("table_id", "")
        except Exception:
            return self._err("Invalid config_id/table_id", 400)

        table_id, table_ref = self._resolve_table(env, raw_table)
        table_domain = self._bill_table_domain(table_id, table_ref)
        table_vals = self._bill_table_vals(table_id, table_ref)

        items = values.get("items") or []
        if_match = values.get("if_match_write_date")

        force_new = bool(values.get("force_new", False))
        dp_amount = float(values.get("dp_amount") or 0.0)
        is_dp = bool(values.get("is_dp") or False)
        type_order = values.get("type_order") or "dine_in"
        allowed_type_order = ["dine_in", "take_away", "online"]
        name_waiters = str(values.get("name_waiters") or "")
        if type_order not in allowed_type_order:
            type_order = "dine_in"

        # normalize dp
        if dp_amount < 0.0:
            dp_amount = 0.0

        if not items:
            if not force_new:
                bill = env["poskas.bill"].search([
                    ("config_id", "=", config_id),
                    ("name_customer", "=", name_customer),
                    table_domain,
                    ("state", "=", "open"),
                ], limit=1, order="id desc")
                if bill:
                    bill.unlink()
            return {"success": True, "type": "NOOP_CART_EMPTY", "data": None}

        create_vals = {
            "config_id": config_id,
            "name_customer": name_customer,
            "name_waiters": name_waiters,
            "state": "open",
            "type_order": type_order,
            **table_vals,
        }

        # ===== FORCE NEW =====
        if force_new:
            bill = env["poskas.bill"].create(create_vals)

            self._apply_lines(env, bill, items)

            bill._compute_amount_total()
            self._set_dp_safe(bill, dp_amount, is_dp)

            return {
                "success": True,
                "type": "CREATED_NEW",
                "data": self._serialize_bill(env, bill),
            }

        # ===== UPDATE EXISTING =====
        bill = env["poskas.bill"].search([
            ("config_id", "=", config_id),
            ("name_customer", "=", name_customer),
            table_domain,
            ("state", "=", "open"),
        ], limit=1, order="id desc")

        if bill:
            conflict = self._check_conflict(bill, if_match)
            if conflict:
                return conflict

            bill.write({
                "type_order": type_order,
                "name_waiters": name_waiters,
            })

            self._apply_lines(env, bill, items)

            bill._compute_amount_total()
            self._set_dp_safe(bill, dp_amount, is_dp)

            return {
                "success": True,
                "type": "UPDATED_EXISTING",
                "data": self._serialize_bill(env, bill),
            }

        # ===== CREATE NEW (NO EXISTING) =====
        bill = env["poskas.bill"].create(create_vals)

        self._apply_lines(env, bill, items)

        bill._compute_amount_total()
        self._set_dp_safe(bill, dp_amount, is_dp)

        return {
            "success": True,
            "type": "CREATED_NEW",
            "data": self._serialize_bill(env, bill),
        }
        
    def _move(self, env, params):
        values = params.get("values") or {}
        bill_id = params.get("id") or values.get("id")
        raw_new_table = values.get("new_table_id")
        if_match = values.get("if_match_write_date")

        if not bill_id or not raw_new_table:
            return self._err("Missing bill id/new_table_id", 400)

        bill = env["poskas.bill"].browse(int(bill_id))
        if not bill.exists():
            return self._err("Bill not found", 404)
        if bill.state != "open":
            return self._err("Bill is not open", 409)

        conflict = self._check_conflict(bill, if_match)
        if conflict:
            return conflict

        new_table_id, new_table_ref = self._resolve_table(env, raw_new_table)
        new_table_domain = self._bill_table_domain(new_table_id, new_table_ref)

        existing = env["poskas.bill"].search([
            ("config_id", "=", bill.config_id.id),
            new_table_domain,
            ("state", "=", "open"),
            ("id", "!=", bill.id),
        ], limit=1)

        if existing:
            return self._err(
                "Target table already has open bill",
                409,
                code="TABLE_OCCUPIED",
                data={"existing_bill_id": existing.id}
            )

        new_table_vals = self._bill_table_vals(new_table_id, new_table_ref)
        bill.write(new_table_vals)
        return {"success": True, "data": self._serialize_bill(env, bill)}

    def _cancel(self, env, params):
        values = params.get("values") or {}
        bill_id = params.get("id") or values.get("id")
        if_match = values.get("if_match_write_date")

        if not bill_id:
            return self._err("Missing bill id", 400)

        bill = env["poskas.bill"].browse(int(bill_id))
        if not bill.exists():
            return self._err("Bill not found", 404)

        conflict = self._check_conflict(bill, if_match)
        if conflict:
            return conflict

        bill.write({"state": "cancel"})
        return {"success": True, "data": self._serialize_bill(env, bill)}

    def _delete(self, env, params):
        """
        Soft delete: change state to 'paid' instead of actually deleting.
        This keeps the bill history in Odoo while appearing deleted to mobile.
        """
        values = params.get("values") or {}

        bill_id = params.get("id") or values.get("id") or values.get("bill_id")
        if_match = values.get("if_match_write_date")

        if bill_id:
            bill = env["poskas.bill"].browse(int(bill_id))
            if not bill.exists():
                return self._err("Bill not found", 404)

            conflict = self._check_conflict(bill, if_match)
            if conflict:
                return conflict

            if bill.state != "open":
                return self._err("Bill is not open", 409)

            # Soft delete: change state to 'paid' instead of unlink()
            bill.write({"state": "paid"})
            return {"success": True, "message": "Bill deleted", "data": {"id": int(bill_id)}}

        config_id = values.get("config_id")
        raw_table = values.get("table_id")
        if config_id and raw_table:
            table_id, table_ref = self._resolve_table(env, raw_table)
            table_domain = self._bill_table_domain(table_id, table_ref)

            bill = env["poskas.bill"].search([
                ("config_id", "=", int(config_id)),
                table_domain,
                ("state", "=", "open"),
            ], limit=1, order="id desc")

            if not bill:
                return self._err("Open bill not found for table", 404)

            conflict = self._check_conflict(bill, if_match)
            if conflict:
                return conflict

            # Soft delete: change state to 'paid' instead of unlink()
            deleted_id = bill.id
            bill.write({"state": "paid"})
            return {"success": True, "message": "Bill deleted", "data": {"id": deleted_id}}

        return self._err("Missing bill_id (or id) or config_id/table_id", 400)

    def _get_table_name_from_order(self, o):
        if not o:
            return ""
        # Odoo resto biasanya restaurant.table
        if "table_id" in o._fields and o.table_id:
            return o.table_id.name or ""
        if "table_ids" in o._fields and o.table_ids:
            return (o.table_ids[0].name or "")
        return ""
    
    from odoo import fields

    
    
    def _serialize_bill(self, env, bill):
        return {
        "id": str(bill.id),
        "name": bill.name or "",
        "table_id": str(bill.table_id.id) if bill.table_id else "",
        "name_customer": bill.name_customer or "",
        "state": bill.state or "open",
        "write_date": fields.Datetime.to_string(bill.write_date) if bill.write_date else None,
        "amount_total": bill.amount_total or 0.0,
        "is_dp": bool(bill.is_dp),
        "dp_amount": bill.dp_amount or 0.0,
        "name_waiters": bill.name_waiters,
        "amount_due": bill.amount_due or 0.0,
        "type_order": bill.type_order or "dine_in",
        "items": [
            {
                "id": str(line.id),
                "product_id": line.product_id.id,
                "product_name": line.product_id.display_name or "",
                "product_category": line.product_id.categ_id.name if line.product_id.categ_id else "",
                "qty": line.qty or 0.0,
                "price_unit": line.price_unit or 0.0,
                "discount_percent": line.discount_percent or 0.0,
                "note": line.note or "",
                "subtotal": line.subtotal or 0.0,
            }
            for line in bill.line_ids
        ],
    }