# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from psycopg2.errors import SerializationFailure
import json
import logging
import pytz
import time
_logger = logging.getLogger(__name__)

class PosSessionApi(http.Controller):
    # =========================================================
    # BASIC UTILS
    # =========================================================
    def _api_env(self, env):
        # pakai admin service untuk integrasi
        service_uid = env.ref("base.user_admin").id
        return env(user=service_uid, su=True)

    def _resp(self, payload, status=200):
        body = json.dumps(payload, default=str)
        return request.make_response(
            body,
            headers=[
                ("Content-Type", "application/json"),
                ("Access-Control-Allow-Origin", "*"),
            ],
            status=status,
        )

    def _err(self, msg, status=400, code=None, data=None):
        res = {"success": False, "message": msg, "status": status}
        if code:
            res["code"] = code
        if data is not None:
            res["data"] = data
        return res

    def _cr_flush_reload(self, rec):
        """Flush cursor + reload record (pengganti rec.flush / invalidate_cache)."""
        try:
            rec.env.cr.flush()
        except Exception:
            pass
        return rec.env[rec._name].browse(rec.id)

    # =========================================================
    # TIME PARSER
    # =========================================================
    def _parse_wib_to_utc_str(self, dt_str):
        """
        dt_str format: 'YYYY-MM-DD HH:MM:SS' (WIB)
        return: UTC datetime string untuk Odoo.
        """
        tz = pytz.timezone("Asia/Jakarta")
        try:
            if dt_str:
                dt_naive = fields.Datetime.from_string(dt_str)
                dt_local = tz.localize(dt_naive, is_dst=None)
                dt_utc = dt_local.astimezone(pytz.utc)
                return fields.Datetime.to_string(dt_utc)
        except Exception:
            pass
        return fields.Datetime.to_string(fields.Datetime.now())

    # =========================================================
    # OPEN FLOW (NORMAL) + FORCE OPENED (HARD)
    # =========================================================
    def _try_open_flow(self, session_rec):
        """
        Coba keluarkan session dari opening_control -> opened lewat flow normal Odoo.
        Tidak pakai flush/invalidate_cache.
        """
        if not session_rec or not session_rec.exists():
            return session_rec

        if getattr(session_rec, "state", None) != "opening_control":
            return session_rec

        candidates = [
            "action_pos_session_open",              # umum
            "action_pos_session_opening_control",   # sebagian flow/custom
            "action_open_session",
            "action_open",
            "open_session",
        ]
        for m in candidates:
            fn = getattr(session_rec, m, None)
            if fn:
                _logger.warning("[OPEN_FLOW] calling %s session=%s state=%s", m, session_rec.id, session_rec.state)
                try:
                    fn()
                except Exception:
                    _logger.exception("[OPEN_FLOW] failed calling %s session=%s", m, session_rec.id)
                break

        session_rec = self._cr_flush_reload(session_rec)
        _logger.warning("[OPEN_FLOW] after open session=%s state=%s", session_rec.id, session_rec.state)
        return session_rec

    def _force_state_opened(self, session_rec, start_at_val=None):
        """
        HARD BYPASS: state=opened (menghindari opening_control) sesuai kebutuhan integrasi Android.
        """
        if not session_rec or not session_rec.exists():
            return session_rec

        vals = {}
        if "state" in session_rec._fields:
            vals["state"] = "opened"
        if start_at_val and "start_at" in session_rec._fields:
            vals["start_at"] = start_at_val

        if vals:
            _logger.warning("[FORCE_OPEN] session=%s prev_state=%s write=%s", session_rec.id, session_rec.state, vals)
            try:
                session_rec.sudo().write(vals)
            except Exception:
                _logger.exception("[FORCE_OPEN] failed session=%s", session_rec.id)

        return self._cr_flush_reload(session_rec)

    # =========================================================
    # APPLY OPENING CASH DIRECTLY TO pos.session (SAFE)
    # =========================================================
    def _apply_opening_cash_fields(self, session, amount, start_at_val=None):
        """
        Override opening cash langsung di pos.session.
        Ini penting kalau statement belum kebentuk.
        """
        if not session or not session.exists():
            return session

        try:
            amount = float(amount or 0.0)
        except Exception:
            amount = 0.0

        vals = {}
        if "cash_register_balance_start" in session._fields:
            vals["cash_register_balance_start"] = amount
        if "cash_register_balance_start_real" in session._fields:
            vals["cash_register_balance_start_real"] = amount
        if start_at_val and "start_at" in session._fields:
            vals["start_at"] = start_at_val

        if vals:
            _logger.warning("[OPEN_CASH_FIELDS] session=%s write=%s", session.id, vals)
            try:
                session.sudo().write(vals)
            except Exception:
                _logger.exception("[OPEN_CASH_FIELDS] failed write session=%s", session.id)

        return self._cr_flush_reload(session)

    # =========================================================
    # ENSURE STATEMENTS EXIST (SAFE)
    # =========================================================
    def _ensure_statements(self, session):
        """
        Pastikan statement kebentuk (kalau model punya field statement).
        Jangan akses field yang tidak ada.
        """
        if not session or not session.exists():
            return session

        has_cash_register_field = "cash_register_id" in session._fields
        has_statement_field = "statement_ids" in session._fields

        if not has_cash_register_field and not has_statement_field:
            _logger.warning("[ENSURE_ST] pos.session has no cash_register_id/statement_ids fields. skip.")
            return session

        cash_register = session.cash_register_id if has_cash_register_field else False
        statements = session.statement_ids if has_statement_field else False

        # sudah ada
        if cash_register or statements:
            return session

        # coba create statements (nama method tergantung module/versi)
        candidates = [
            "_create_bank_statements",
            "_create_account_bank_statements",
            "_create_statements",
        ]
        for m in candidates:
            fn = getattr(session, m, None)
            if fn:
                _logger.warning("[ENSURE_ST] calling %s session=%s", m, session.id)
                try:
                    fn()
                except Exception:
                    _logger.exception("[ENSURE_ST] failed calling %s session=%s", m, session.id)
                break

        return self._cr_flush_reload(session)

    # =========================================================
    # SINGLE SOURCE OF TRUTH: OVERRIDE STARTING BALANCE STATEMENT
    # =========================================================
    def _override_cash_statement_start(self, session, amount):
        """
        Paksa saldo awal cash statement = input Android.
        Menimpa carry-over dari session sebelumnya.
        """
        if not session or not session.exists():
            return

        try:
            amount = float(amount or 0.0)
        except Exception:
            amount = 0.0

        # statement_ids lebih universal daripada cash_register_id (tapi keduanya bisa berbeda per versi)
        if "statement_ids" not in session._fields:
            _logger.warning("[CASH_OVERRIDE] session=%s has no statement_ids field. skip.", session.id)
            return

        statements = session.statement_ids
        if not statements:
            _logger.warning("[CASH_OVERRIDE] no statement_ids session=%s", session.id)
            return

        # ambil statement journal cash kalau bisa
        cash_statements = statements
        try:
            cash_statements = statements.filtered(
                lambda s: getattr(getattr(s, "journal_id", None), "type", "") == "cash"
            ) or statements
        except Exception:
            cash_statements = statements

        for st in cash_statements:
            vals = {}
            if "balance_start" in st._fields:
                vals["balance_start"] = amount
            if "balance_start_real" in st._fields:
                vals["balance_start_real"] = amount

            if vals:
                _logger.warning(
                    "[CASH_OVERRIDE] session=%s statement=%s OVERRIDE start=%s vals=%s",
                    session.id, st.id, amount, vals
                )
                try:
                    st.sudo().write(vals)
                except Exception:
                    _logger.exception("[CASH_OVERRIDE] failed write statement=%s session=%s", st.id, session.id)

    # =========================================================
    # FINALIZE OPENING (SINGLE FLOW)
    # =========================================================
    def _finalize_opening_numbers(self, session, start_cash, start_at_val):
        """
        Urutan FINAL:
        1) apply opening ke session (biar field session ikut android)
        2) coba open normal
        3) kalau masih opening_control => force opened
        4) ensure statements
        5) override starting balance statement (paling akhir)
        """
        session = self._cr_flush_reload(session)

        # (1) set dulu (session fields)
        session = self._apply_opening_cash_fields(session, start_cash, start_at_val)

        # (2) coba open normal
        if getattr(session, "state", None) == "opening_control":
            session = self._try_open_flow(session)

        # (3) hard bypass kalau masih nyangkut
        session = self._cr_flush_reload(session)
        if getattr(session, "state", None) == "opening_control":
            session = self._force_state_opened(session, start_at_val=start_at_val)

        # (4) ensure statements (kalau model punya)
        session = self._ensure_statements(session)
        session = self._cr_flush_reload(session)

        # (5) paling akhir: override statement cash start (kalau ada)
        self._override_cash_statement_start(session, start_cash)

        # set lagi di pos.session after semua flow (buat jaga-jaga ada compute yang nimpa)
        session = self._apply_opening_cash_fields(session, start_cash, start_at_val)

        return self._cr_flush_reload(session)

    # =========================================================
    # ROUTES
    # =========================================================
    @http.route("/api/pos/session/active", type="http", auth="none", methods=["GET"], csrf=False)
    def get_active_session(self, **kw):
        env = self._api_env(request.env)

        # ---- params ----
        config_id = kw.get("config_id")
        user_id = kw.get("user_id")  # OPTIONAL: kirim dari app biar session match kasir

        if not config_id:
            return self._resp(self._err("Missing config_id", 400), 400)

        try:
            config_id = int(config_id)
        except Exception:
            return self._resp(self._err("Invalid config_id", 400), 400)

        u_id = None
        if user_id:
            try:
                u_id = int(user_id)
            except Exception:
                u_id = None

        # ---- debug log ----
        _logger.warning("[GET_ACTIVE_SESSION] config_id=%s user_id=%s", config_id, u_id)

        # ---- domain: ACTIVE only ----
        domain = [
            ("config_id", "=", config_id),
            ("state", "in", ["opening_control", "opened"]),  # NOTE: no closing_control
        ]
        if u_id:
            domain.append(("user_id", "=", u_id))

        session = env["pos.session"].sudo().search(
            domain,
            limit=1,
            order="start_at desc, id desc",
        )

        if not session:
            _logger.warning("[GET_ACTIVE_SESSION] not found for config_id=%s user_id=%s", config_id, u_id)
            return self._resp({"success": True, "has_active_session": False, "data": None})

        # ---- force read latest values (avoid stale cache) ----
        try:
            session.flush()
        except Exception:
            pass

        data = session.read([
            "id", "name", "state", "start_at", "stop_at", "write_date",
            "config_id", "user_id"
        ])[0]

        _logger.warning(
            "[GET_ACTIVE_SESSION] found id=%s name=%s state=%s config=%s user=%s",
            data.get("id"), data.get("name"), data.get("state"),
            data.get("config_id"), data.get("user_id")
        )

        return self._resp({
            "success": True,
            "has_active_session": True,
            "data": {
                "id": data["id"],
                "name": data["name"],
                "start_at": fields.Datetime.to_string(data["start_at"]) if data.get("start_at") else None,
                "stop_at": fields.Datetime.to_string(data["stop_at"]) if data.get("stop_at") else None,
                "state": data["state"],
                "config_id": data["config_id"],   # (id, name)
                "user_id": data["user_id"],       # (id, name)
                "write_date": fields.Datetime.to_string(data["write_date"]) if data.get("write_date") else None,
            },
        })
        
    @http.route("/api/pos/session", type="http", auth="none", methods=["GET", "POST", "PUT", "OPTIONS"], csrf=False)
    def pos_session(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response(
                "OK",
                headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS"),
                    ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, company-id"),
                ],
            )

        method = request.httprequest.method.upper()

        data = {}
        if method in ("POST", "PUT"):
            raw = request.httprequest.data or b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._resp({"success": False, "message": "Invalid JSON body", "status": 400}, 400)

        values = None
        if isinstance(data, dict):
            values = data.get("values")
            if values is None:
                values = data

        params = dict(kw)
        if values is not None:
            params["values"] = values

        env = request.env

        if method == "POST":
            res = self._open_session(env, params)
            return self._resp(res, res.get("status", 200))

        if method == "PUT":
            session_id = params.get("id") or params.get("Id")
            if session_id:
                params["id"] = session_id
            res = self._close_session(env, params)
            return self._resp(res, res.get("status", 200))

        if method == "GET":
            api_env = self._api_env(env)
            name = params.get("name")
            start_at = params.get("start_at")
            domain = []
            if name:
                domain.append(("name", "=", name))
            if start_at:
                date = fields.Date.from_string(start_at)
                domain += [
                    ("start_at", ">=", fields.Datetime.to_datetime(date)),
                    ("start_at", "<", fields.Datetime.to_datetime(date + fields.Date.delta(days=1))),
                ]
            sessions = api_env["pos.session"].search_read(
                domain,
                ["id", "name", "config_id", "start_at", "stop_at", "state", "access_token"],
                limit=1,
            )
            return self._resp({"success": True, "data": sessions[0] if sessions else None})

        return self._resp({"success": False, "message": "Unsupported method", "status": 405}, 405)
    # =========================================================
    # OPEN SESSION
    # =========================================================
    def _open_session(self, env, params):
        api_env = self._api_env(env)
        values = params.get("values") or {}

        # validate
        try:
            config_id = int(values["config_id"])
            user_id = int(values["user_id"])
        except Exception:
            return self._err("Invalid config_id or user_id", 400)

        # opening cash
        try:
            start_cash = float(values.get("cash_register_balance_start") or 0.0)
        except Exception:
            start_cash = 0.0

        # start_at WIB -> UTC
        start_at_val = self._parse_wib_to_utc_str(values.get("start_at"))

        _logger.warning(
            "[OPEN_SESSION] IN config_id=%s user_id=%s start_cash=%s start_at_utc=%s",
            config_id, user_id, start_cash, start_at_val
        )

        # cari active termasuk closing_control
        last = api_env["pos.session"].search(
            [
                ("config_id", "=", config_id),
                ("state", "in", ["opening_control", "opened", "closing_control"]),
            ],
            limit=1,
            order="id desc",
        )
        
        if last and last.state in ("opened", "opening_control"):
            notes = ""
            try:
                if "closing_notes" in last._fields:
                    notes = (last.closing_notes or "")
            except Exception:
                notes = ""

            if "[SOFT_CLOSED]" in (notes or ""):
                _logger.warning(
                    "[OPEN_SESSION] last session=%s state=%s is SOFT_CLOSED -> create new session",
                    last.id, last.state
                )
                last = api_env["pos.session"]

        # kalau masih closing_control -> jangan buat baru
        if last and last.state == "closing_control":
            return self._err(
                "Session sedang proses closing. Selesaikan close dulu.",
                status=409,
                code="SESSION_CLOSING",
                data={"id": last.id, "state": last.state},
            )

        # reuse existing
        if last:
            last = self._apply_user(last, user_id)
            last = self._finalize_opening_numbers(last, start_cash, start_at_val)
            return {
                "success": True,
                "data": {
                    "id": last.id,
                    "name": last.name,
                    "state": last.state,
                    "start_at": fields.Datetime.to_string(last.start_at) if last.start_at else None,
                    "already_opened": True,
                    "cash_register_balance_start": start_cash,
                },
            }

        # create new
        try:
            create_vals = {
                "name": values.get("name"),
                "config_id": config_id,
                "user_id": user_id,
            }
            # set start_at kalau field ada
            if "start_at" in api_env["pos.session"]._fields:
                create_vals["start_at"] = start_at_val
            # set start cash session-level kalau field ada
            if "cash_register_balance_start" in api_env["pos.session"]._fields:
                create_vals["cash_register_balance_start"] = start_cash

            rec = api_env["pos.session"].sudo().create(create_vals)
            rec = self._cr_flush_reload(rec)

        except ValidationError as ve:
            _logger.warning("[OPEN_SESSION] ValidationError create: %s", str(ve))
            # fallback race: cari lagi
            last = api_env["pos.session"].search(
                [
                    ("config_id", "=", config_id),
                    ("state", "in", ["opening_control", "opened", "closing_control"]),
                ],
                limit=1,
                order="id desc",
            )
            if last:
                last = self._finalize_opening_numbers(last, start_cash, start_at_val)
                return {
                    "success": True,
                    "data": {
                        "id": last.id,
                        "name": last.name,
                        "state": last.state,
                        "start_at": fields.Datetime.to_string(last.start_at) if last.start_at else None,
                        "already_opened": True,
                        "cash_register_balance_start": start_cash,
                    },
                }
            return self._err(str(ve), 409, code="VALIDATION_ERROR")

        # finalize one single flow
        rec = self._finalize_opening_numbers(rec, start_cash, start_at_val)

        return {
            "success": True,
            "data": {
                "id": rec.id,
                "name": rec.name,
                "state": rec.state,
                "start_at": fields.Datetime.to_string(rec.start_at) if rec.start_at else None,
                "already_opened": False,
                "cash_register_balance_start": start_cash,
            },
        }
    
    # =========================================================
    # CLOSE SESSION
    # =========================================================
    def _get_candidates(self, record, keywords=None, limit=120):
        keywords = keywords or ("process", "final", "done", "post", "confirm", "complete", "paid", "close",
                           "validate", "account", "move", "entry", "picking", "stock")
        out = []
        for name in dir(record):
            low = name.lower()
            if any(k in low for k in keywords):
                attr = getattr(record, name, None)
                if callable(attr):
                    out.append(name)
        out = sorted(set(out), key=lambda x: (len(x), x))
        return out[:limit]

    def _apply_user(self, session, user_id):
        if not session or not session.exists():
            return session
        if "user_id" in session._fields and user_id:
            try:
                session.sudo().write({"user_id": int(user_id)})
            except Exception:
                _logger.exception("[APPLY_USER] failed session=%s user_id=%s", session.id, user_id)
        return self._cr_flush_reload(session)

    
    def _force_fix_online_payment_partner(self, api_env, session):
        _logger = logging.getLogger(__name__)

        cfg = session.config_id  # <- pastikan selalu ada
        fallback_partner = None

        # 1) cfg.default_partner_id
        if cfg and hasattr(cfg, "_fields") and "default_partner_id" in cfg._fields:
            fallback_partner = cfg.default_partner_id

        # 2) alternatif field
        if not fallback_partner and cfg and hasattr(cfg, "_fields"):
            for fn in ("anonymous_partner_id", "walkin_partner_id", "default_customer_id"):
                if fn in cfg._fields and getattr(cfg, fn):
                    fallback_partner = getattr(cfg, fn)
                    break

        # 3) walk-in by name
        if not fallback_partner:
            fallback_partner = api_env["res.partner"].sudo().search(
                [("name", "ilike", "walk"), ("company_id", "in", [False, session.company_id.id])],
                limit=1
            )

        # 4) fallback terakhir
        if not fallback_partner:
            fallback_partner = api_env["res.partner"].sudo().search(
                [("company_id", "in", [False, session.company_id.id])],
                limit=1
            )

        if not fallback_partner:
            return {"fixed": 0, "missing": [], "note": "no_fallback_partner"}

        model_names = ["pos.online.payment", "pos_online_payment.payment", "pos.online.payment.transaction"]
        fixed = 0
        missing_ids = []
        used = []

        for mn in model_names:
            try:
                Pay = api_env[mn].sudo()  # <- cara cek model paling jelas
            except KeyError:
                continue

            try:
                if "partner_id" not in Pay._fields:
                    continue

                if "session_id" in Pay._fields:
                    pays = Pay.search([("session_id", "=", session.id)])
                elif "order_id" in Pay._fields:
                    pays = Pay.search([("order_id.session_id", "=", session.id)])
                elif "pos_order_id" in Pay._fields:
                    pays = Pay.search([("pos_order_id.session_id", "=", session.id)])
                else:
                    continue

                used.append(mn)

                missing = pays.filtered(lambda p: not p.partner_id)
                if missing:
                    missing_ids += missing.ids
                    missing.sudo().write({"partner_id": fallback_partner.id})
                    fixed += len(missing)

            except Exception as e:
                _logger.exception("force_fix_online_payment_partner failed on %s: %s", mn, e)
                continue

        return {
            "fixed": fixed,
            "missing": missing_ids[:50],
            "models_used": used,
            "fallback_partner_id": fallback_partner.id,
        }

    def _close_session(self, env, params):
        api_env = self._api_env(env)
        session_id = params.get("id") or params.get("Id")
        values = params.get("values") or {}

        # -------------------------
        # Response helpers (STRICT)
        # -------------------------
        def fail(message, code="ERROR", data=None, error=None):
            payload = {
                "success": False,
                "code": code,
                "message": message,
                "data": data or {},
            }
            if error:
                payload["error"] = error
            return payload

        def ok_success(session, note=None, extra=None):
            session_data = session.read(
                ["id", "state", "stop_at", "cash_register_balance_end_real", "cash_register_balance_end"]
            )[0]
            payload = {"success": True, "data": session_data}
            if note:
                payload["note"] = note
            if extra:
                payload.update(extra)
            return payload

        # -------------------------
        # Basic validation
        # -------------------------
        if not session_id:
            return fail("Missing session id", code="MISSING_SESSION_ID")
        if not isinstance(values, dict):
            return fail("Missing values", code="MISSING_VALUES")

        session = api_env["pos.session"].browse(int(session_id))
        if not session.exists():
            return fail("Session not found", code="SESSION_NOT_FOUND", data={"session_id": session_id})

        # -------------------------
        # Idempotent
        # -------------------------
        if getattr(session, "state", None) == "closed":
            return ok_success(session, note="already_closed", extra={"validated": True})

        # -------------------------
        # Parse payload
        # -------------------------
        stop_at_val = self._parse_wib_to_utc_str(values.get("stop_at"))
        try:
            end_real = float(values.get("cash_register_balance_end_real") or 0.0)
        except Exception:
            end_real = 0.0
        closing_notes = (values.get("closing_notes", "") or "").strip()

        # =========================
        # SAFE FLAGS (explicit)
        # =========================
        # allow_unposted: kalau ada order PAID belum posted, tetap boleh "tutup operasional"
        allow_unposted = bool(values.get("allow_unposted") or values.get("allowUnposted"))

        # force_close: paksa tetap jalankan close flow sampai state=closed (RISIKO data accounting)
        # Default False, hanya untuk emergency. Jika accounting benar-benar belum dipakai, tetap lebih aman pakai allow_unposted.
        force_close = bool(values.get("force_close") or values.get("forceClose"))

        # STRICT: tidak ada fast/safe mode implisit
        safe_close = False
        fast_close = False

        _logger.warning(
            "[CLOSE_SESSION] session_id=%s end_real=%s stop_at_utc=%s state=%s allow_unposted=%s force_close=%s",
            session.id, end_real, stop_at_val, getattr(session, "state", None), allow_unposted, force_close
        )

        # -------------------------
        # Write end payload with retry
        # -------------------------
        def _write_end_payload_with_retry(session, tries=5, sleep_s=0.25):
            last_err = None
            for _ in range(tries):
                try:
                    vals = {"stop_at": stop_at_val}
                    if "closing_notes" in session._fields:
                        vals["closing_notes"] = closing_notes

                    if "cash_register_balance_end_real" in session._fields:
                        vals["cash_register_balance_end_real"] = end_real
                    if "cash_real_transaction" in session._fields:
                        vals["cash_real_transaction"] = end_real

                    session.sudo().write(vals)

                    # update cash statement end_real (kalau ada)
                    try:
                        st = None
                        if "cash_register_id" in session._fields and session.cash_register_id:
                            st = session.cash_register_id
                        elif "statement_ids" in session._fields and session.statement_ids:
                            cash_st = session.statement_ids.filtered(
                                lambda x: getattr(getattr(x, "journal_id", None), "type", "") == "cash"
                            )
                            st = (cash_st[:1] or session.statement_ids[:1])

                        if st and st.exists():
                            if "balance_end_real" in st._fields:
                                st.sudo().write({"balance_end_real": end_real})
                            elif "balance_end" in st._fields:
                                st.sudo().write({"balance_end": end_real})
                    except Exception:
                        _logger.exception("[CLOSE_SESSION] failed write cash statement end_real session=%s", session.id)

                    return True, None

                except SerializationFailure as e:
                    last_err = e
                    try:
                        session.env.cr.rollback()
                    except Exception:
                        pass
                    time.sleep(sleep_s)
                except Exception as e:
                    last_err = e
                    break

            return False, str(last_err) if last_err else "unknown_error"

        ok_write, err_write = _write_end_payload_with_retry(session)
        session = self._cr_flush_reload(session)

        if not ok_write:
            return fail(
                "Server sedang sibuk (concurrent update). Coba lagi.",
                code="CONCURRENT_UPDATE",
                data={"session_id": session.id},
                error=err_write,
            )

        # -------------------------
        # Normalize opening_control -> opened (best effort)
        # -------------------------
        if getattr(session, "state", None) == "opening_control":
            try:
                session = self._try_open_flow(session)
                session = self._cr_flush_reload(session)
            except Exception:
                _logger.exception("[CLOSE_SESSION] _try_open_flow failed session=%s", session.id)

        if getattr(session, "state", None) == "opening_control":
            try:
                session = self._force_state_opened(session)
                session = self._cr_flush_reload(session)
            except Exception:
                _logger.exception("[CLOSE_SESSION] _force_state_opened failed session=%s", session.id)

        # -------------------------
        # Block if draft orders (tetap strict)
        # -------------------------
        try:
            draft_total = api_env["pos.order"].search_count(
                [("session_id", "=", session.id), ("state", "=", "draft")]
            )
            if draft_total:
                return fail(
                    "Tidak bisa close: masih ada order DRAFT.",
                    code="DRAFT_ORDERS",
                    data={"session_id": session.id, "draft_total": draft_total},
                )
        except Exception as e:
            _logger.exception("[CLOSE_SESSION] draft check failed session=%s", session.id)
            return fail(
                "Tidak bisa close: gagal cek order draft.",
                code="DRAFT_CHECK_FAILED",
                data={"session_id": session.id},
                error=str(e),
            )

        # -------------------------
        # Hitung remaining PAID (sebelum validate)
        # -------------------------
        remaining_paid = 0
        try:
            remaining_paid = api_env["pos.order"].search_count(
                [("session_id", "=", session.id), ("state", "=", "paid")]
            )
        except Exception as e:
            _logger.exception("[CLOSE_SESSION] remaining paid check failed session=%s", session.id)
            return fail(
                "Tidak bisa close: gagal cek order paid.",
                code="PAID_CHECK_FAILED",
                data={"session_id": session.id},
                error=str(e),
            )

        # =========================
        # SOFT CLOSE PATH (AMAN)
        # =========================
        # Kalau ada PAID yang belum posted, dan allow_unposted=True,
        # kita STOP di sini: tidak validate, tidak close session jadi 'closed'.
        # Tapi kita tetap anggap "tutup operasional" dan kasih payload lengkap supaya UI bisa lock.
        if remaining_paid and allow_unposted and not force_close:
            try:
                tag = f"[SOFT_CLOSED] remaining_paid={remaining_paid}"
                if "closing_notes" in session._fields:
                    prev = (session.closing_notes or "").strip() if hasattr(session, "closing_notes") else ""
                    merged = "\n".join([x for x in [prev, closing_notes, tag] if x]).strip()
                    session.sudo().write({"closing_notes": merged})
            except Exception:
                _logger.exception("[CLOSE_SESSION] failed to write SOFT_CLOSED tag session=%s", session.id)

            session = self._cr_flush_reload(session)
            return ok_success(
                session,
                note="soft_closed_unposted_paid",
                extra={
                    "validated": False,
                    "soft_closed": True,
                    "remaining_paid": remaining_paid,
                    "draft_total": 0,
                    "warning": "Session ditutup operasional, tapi masih ada order PAID belum ter-post.",
                },
            )

        # -------------------------
        # Validate session (Odoo-like) - only if not soft-close
        # -------------------------
        validated = False
        validate_error = None
        validate_reason = None

        try:
            if hasattr(session, "action_pos_session_validate"):
                _logger.warning("[CLOSE_SESSION] calling action_pos_session_validate session=%s", session.id)

                # optional fix hook (keep)
                try:
                    self._force_fix_online_payment_partner(api_env, session)
                    session = self._cr_flush_reload(session)
                except Exception:
                    _logger.exception("[CLOSE_SESSION] force_fix_online_payment_partner failed session=%s", session.id)

                session.sudo().action_pos_session_validate()
                session = self._cr_flush_reload(session)
                validated = True

            elif hasattr(session, "_validate_session"):
                _logger.warning("[CLOSE_SESSION] calling _validate_session session=%s", session.id)
                session._validate_session()
                session = self._cr_flush_reload(session)
                validated = True

            else:
                return fail(
                    "Tidak bisa close: method validate session tidak tersedia.",
                    code="NO_SESSION_VALIDATE_METHOD",
                    data={"session_id": session.id},
                )

        except SerializationFailure as e:
            validate_error = str(e)
            return fail(
                "Server sedang sibuk (concurrent update) saat validate. Coba lagi.",
                code="CONCURRENT_UPDATE",
                data={"session_id": session.id},
                error=validate_error,
            )
        except Exception as e:
            validate_error = str(e)
            _logger.exception("[CLOSE_SESSION] validate failed session=%s", session.id)
            try:
                cannot = getattr(session, "_cannot_close_session", None)
                if callable(cannot):
                    validate_reason = cannot()
            except Exception:
                validate_reason = None

            # Kalau force_close diminta, kita lanjut ke closing/close step meskipun validate gagal (RISIKO).
            if force_close:
                _logger.warning("[CLOSE_SESSION] force_close=True: continue despite validate error session=%s err=%s", session.id, validate_error)
            else:
                return fail(
                    "Tidak bisa close: validasi/posting gagal. Cek konfigurasi accounting/stock/journal.",
                    code="SESSION_VALIDATE_FAILED",
                    data={"session_id": session.id, "reason": validate_reason},
                    error=validate_error,
                )

        # If validate already closed
        session = self._cr_flush_reload(session)
        if getattr(session, "state", None) == "closed":
            return ok_success(session, extra={"validated": True})

        # -------------------------
        # Re-check remaining paid after validate
        # -------------------------
        try:
            remaining_paid_after = api_env["pos.order"].search_count(
                [("session_id", "=", session.id), ("state", "=", "paid")]
            )
        except Exception as e:
            _logger.exception("[CLOSE_SESSION] remaining paid check (after validate) failed session=%s", session.id)
            return fail(
                "Tidak bisa close: gagal cek order paid.",
                code="PAID_CHECK_FAILED",
                data={"session_id": session.id},
                error=str(e),
            )

        if remaining_paid_after and not force_close:
            return fail(
                "Tidak bisa close: masih ada order PAID yang belum ter-post.",
                code="PAID_NOT_POSTED",
                data={"session_id": session.id, "remaining_paid": remaining_paid_after},
            )

        # -------------------------
        # Closing control (Odoo-like)
        # -------------------------
        if hasattr(session, "action_pos_session_closing_control"):
            try:
                _logger.warning("[CLOSE_SESSION] calling action_pos_session_closing_control session=%s", session.id)
                session.action_pos_session_closing_control()
                session = self._cr_flush_reload(session)
            except Exception as e:
                _logger.exception("[CLOSE_SESSION] closing_control failed session=%s", session.id)
                if not force_close:
                    return fail(
                        "Tidak bisa close: closing control gagal.",
                        code="CLOSING_CONTROL_FAILED",
                        data={"session_id": session.id},
                        error=str(e),
                    )
                _logger.warning("[CLOSE_SESSION] force_close=True: ignore closing_control failure session=%s", session.id)

        # -------------------------
        # Final close (force_close may still try)
        # -------------------------
        try:
            if getattr(session, "state", None) != "closed":
                session.action_pos_session_close()
                session = self._cr_flush_reload(session)
        except Exception as e:
            _logger.exception("[CLOSE_SESSION] action_pos_session_close failed session=%s", session.id)
            return fail(
                "Tidak bisa close: action_pos_session_close gagal.",
                code="SESSION_CLOSE_FAILED",
                data={"session_id": session.id, "state": getattr(session, "state", None)},
                error=str(e),
            )

        session = self._cr_flush_reload(session)
        if getattr(session, "state", None) == "closed":
            return ok_success(session, extra={
                "validated": bool(validated),
                "force_close": bool(force_close),
            })

        return fail(
            "Tidak bisa close: session belum closed setelah close flow.",
            code="NOT_CLOSED",
            data={"session_id": session.id, "state": getattr(session, "state", None)},
        )

    
    @http.route("/api/pos/session/closing_summary", type="http", auth="none", methods=["GET"], csrf=False)
    def closing_summary(self, **kw):
        api_env = self._api_env(request.env)

        session_id = kw.get("id") or kw.get("session_id")
        if not session_id:
            return self._resp(self._err("Missing session id", 400), 400)

        try:
            session_id = int(session_id)
        except Exception:
            return self._resp(self._err("Invalid session id", 400), 400)

        session = api_env["pos.session"].browse(session_id)
        if not session.exists():
            return self._resp(self._err("Session not found", 404), 404)

        data = self._build_closing_summary(api_env, session)
        return self._resp({"success": True, "data": data}, 200)

    def _build_closing_summary(self, api_env, session):
        state_ok = ["paid", "done", "invoiced"]
        Order = api_env["pos.order"].sudo()
        orders = Order.search([
            ("session_id", "=", session.id),
            ("state", "in", state_ok)
        ])

        counts_by_state = {"paid": 0, "done": 0, "invoiced": 0}
        for o in orders:
            st = (o.state or "").lower()
            if st in counts_by_state:
                counts_by_state[st] += 1

        pending_paid_unposted = counts_by_state.get("paid", 0)

        total_gross = 0.0
        total_tax = 0.0
        total_net = 0.0
        total_discount = 0.0


        items_map = {}
        items_detail = []

        for o in orders:
            if "amount_total" in o._fields:
                total_gross += float(o.amount_total or 0.0)
            if "amount_tax" in o._fields:
                total_tax += float(o.amount_tax or 0.0)

            line_field = "lines" if "lines" in o._fields else ("lines_ids" if "lines_ids" in o._fields else None)
            lines = getattr(o, line_field) if line_field else False
            if not lines:
                continue

            order_name = getattr(o, "name", None)

            for l in lines:
                pid = l.product_id.id if getattr(l, "product_id", None) else 0
                if not pid:
                    continue

                name = l.product_id.display_name or l.product_id.name or "Produk"
                is_discount_product = (
                    "discount" in (name or "").lower()
                )
                qty = float(getattr(l, "qty", 0.0) or 0.0)
                price_unit = float(getattr(l, "price_unit", 0.0) or 0.0)
                discount_percent = float(getattr(l, "discount", 0.0) or 0.0) if "discount" in l._fields else 0.0

                if "price_subtotal" in l._fields:
                    subtotal_excl = float(l.price_subtotal or 0.0)
                else:
                    subtotal_excl = price_unit * qty

                if "price_subtotal_incl" in l._fields:
                    subtotal_incl = float(l.price_subtotal_incl or 0.0)
                else:
                    subtotal_incl = subtotal_excl

                if "price_subtotal_incl" in l._fields:
                    line_total = float(l.price_subtotal_incl or 0.0)
                elif "price_subtotal" in l._fields:
                    line_total = float(l.price_subtotal or 0.0)
                else:
                    line_total = price_unit * qty

                gross_line = price_unit * qty


                # =====================================
                # ITEM DISCOUNT
                # =====================================
                discount_amount = 0.0

                if discount_percent > 0 and gross_line > 0:
                    discount_amount = gross_line - subtotal_excl

                # =====================================
                # TRANSACTION DISCOUNT
                # =====================================
                if is_discount_product:
                    discount_amount = abs(line_total)

                total_discount += discount_amount

                tmpl = getattr(l.product_id, "product_tmpl_id", False)

                pos_categ_id = None
                pos_categ_name = None

                if tmpl and "pos_categ_ids" in tmpl._fields:
                    categs = tmpl.pos_categ_ids
                    if categs:
                        first = categs[0]
                        pos_categ_id = first.id
                        pos_categ_name = first.display_name
                        
                if is_discount_product:
                    continue

                items_detail.append({
                    "order_id": o.id,
                    "order_name": order_name,
                    "product_id": pid,
                    "name": name,
                    "qty": qty,
                    "price_unit": price_unit,
                    "discount_percent": discount_percent,
                    "discount_amount": discount_amount,
                    "subtotal_excl": subtotal_excl,
                    "subtotal_incl": subtotal_incl,
                    "pos_categ_id": pos_categ_id,
                    "pos_categ_name": pos_categ_name,
                })

                key = (pid, pos_categ_id or 0)

                if key not in items_map:
                    items_map[key] = {
                        "product_id": pid,
                        "name": name,
                        "qty": 0.0,
                        "total": 0.0,
                        "discount_amount": 0.0,
                        "discount_percent_total": 0.0,
                        "pos_categ_id": pos_categ_id,
                        "pos_categ_name": pos_categ_name,
                    }

                items_map[key]["qty"] += qty
                items_map[key]["total"] += line_total
                items_map[key]["discount_amount"] += discount_amount
                items_map[key]["discount_percent_total"] += discount_percent

        total_net = (total_gross - total_tax) if total_tax > 0 else total_gross

        pay_breakdown = self._compute_payment_breakdown(api_env, session, orders)

        items = list(items_map.values())
        items.sort(key=lambda x: (x["total"] or 0.0), reverse=True)

        sread = session.read(["id", "name", "state", "start_at", "stop_at", "config_id", "user_id"])[0]

        warning = None
        if pending_paid_unposted > 0:
            warning = (
                f"Ada {pending_paid_unposted} order PAID belum ter-post (pending). "
                f"Shift bisa ditutup operasional, tapi session Odoo belum bisa full close."
            )

        return {
            "session": {
                "id": sread.get("id"),
                "name": sread.get("name"),
                "state": sread.get("state"),
                "start_at": fields.Datetime.to_string(sread.get("start_at")) if sread.get("start_at") else None,
                "stop_at": fields.Datetime.to_string(sread.get("stop_at")) if sread.get("stop_at") else None,
                "config_id": sread.get("config_id"),
                "user_id": sread.get("user_id"),
            },
            "orders_count": len(orders),
            "orders_count_by_state": counts_by_state,
            "pending": {
                "paid_unposted_count": pending_paid_unposted,
            },
            "totals": {
                "gross": total_gross,
                "tax": total_tax,
                "net": total_net,
                "discount": total_discount,
            },
            "payments": pay_breakdown,
            "items": items,
            "items_detail": items_detail,
            "warning": warning,
        }

    def _compute_payment_breakdown(self, api_env, session, orders):
        """
        Coba beberapa model/field untuk breakdown pembayaran.
        Tujuan: dapat total per metode (CASH/QRIS/others)
        """
        out = {
            "total": 0.0,
            "by_method": [],  # [{name, amount}]
        }

        # 1) Versi baru: pos.payment (umum di Odoo 14+)
        try:
            Pay = api_env["pos.payment"].sudo()
            pays = Pay.search([("pos_order_id.session_id", "=", session.id)])
            if pays:
                m = {}
                for p in pays:
                    amt = float(getattr(p, "amount", 0.0) or 0.0)
                    pm = getattr(p, "payment_method_id", None)
                    name = (pm and (pm.name or pm.display_name)) or "Unknown"
                    m[name] = m.get(name, 0.0) + amt
                out["by_method"] = [{"name": k, "amount": v} for k, v in sorted(m.items())]
                out["total"] = sum(x["amount"] for x in out["by_method"])
                return out
        except Exception:
            pass

        # 2) Fallback: statement lines dari orders (versi lama/custom)
        try:
            m = {}
            for o in orders:
                st_field = "statement_ids" if "statement_ids" in o._fields else None
                stmts = getattr(o, st_field) if st_field else False
                if not stmts:
                    continue
                for st in stmts:
                    amt = float(getattr(st, "amount", 0.0) or 0.0)
                    j = getattr(st, "journal_id", None)
                    name = (j and (j.name or j.display_name)) or "Unknown"
                    m[name] = m.get(name, 0.0) + amt
            if m:
                out["by_method"] = [{"name": k, "amount": v} for k, v in sorted(m.items())]
                out["total"] = sum(x["amount"] for x in out["by_method"])
                return out
        except Exception:
            pass

        # 3) Last fallback: total gross only (no breakdown)
        try:
            total = 0.0
            for o in orders:
                if "amount_total" in o._fields:
                    total += float(o.amount_total or 0.0)
            out["total"] = total
        except Exception:
            pass

        return out