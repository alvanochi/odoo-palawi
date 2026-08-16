# controllers/pos_cash_movement_api.py
from odoo import http
from odoo.http import request
import json
import math
import logging
import datetime

_logger = logging.getLogger(__name__)

class PosCashMovementApi(http.Controller):

    @http.route(
        "/api/pos/cash_movement",
        type="http",
        auth="none",
        methods=["GET", "POST", "OPTIONS"],
        csrf=False
    )
    def pos_cash_movement(self, **kw):
        # CORS preflight
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, company-id, db, api_key, api-key"),
            ])

        try:
            if request.httprequest.method == "GET":
                result = self._list(request.env, kw)
                return self._resp(result, result.get("status", 200))

            if request.httprequest.method == "POST":
                payload = request.httprequest.get_data(as_text=True) or "{}"
                body = json.loads(payload)
                result = self._create(request.env, body)
                return self._resp(result, result.get("status", 200))

            return self._resp(self._err("Method not allowed", 405), 405)

        except Exception as e:
            _logger.exception("POS CASH MOVEMENT API ERROR")
            return self._resp(self._err(str(e), 400), 400)

    def _json_default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
             return obj.isoformat()
        return str(obj)

    def _resp(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, default=self._json_default),
            headers=[
                ("Content-Type", "application/json"),
                ("Access-Control-Allow-Origin", "*"),
            ],
            status=status
        )

    def _err(self, message, status=400):
        return {"ok": False, "status": status, "error": message}

    # ===== CREATE =====
    def _create(self, env, body):
        cm_id = (body.get("cm_id") or "").strip()
        session_id = (body.get("session_id") or "").strip()
        movement_type = (body.get("type") or "").strip().lower()   # cash_in / cash_out
        reason = (body.get("reason") or "").strip()
        pos_name = (body.get("pos_name") or "").strip()
        user_name = (body.get("user_name") or "").strip()
        movement_time = body.get("movement_time")  # optional ISO string

        amount = body.get("amount")
        if not cm_id:
            return self._err("cm_id is required", 400)
        if not session_id:
            return self._err("session_id is required", 400)
        if movement_type not in ("cash_in", "cash_out"):
            return self._err("type must be cash_in or cash_out", 400)
        if amount is None:
            return self._err("amount is required", 400)

        try:
            amount = int(amount)
        except:
            return self._err("amount must be integer", 400)

        if amount <= 0:
            return self._err("amount must be > 0", 400)

        Mov = env["pos.cash.movement"].sudo()

        # idempotent: kalau cm_id sudah ada, return existing (biar retry Android aman)
        existing = Mov.search([("name", "=", cm_id)], limit=1)
        if existing:
            data = existing.read(self._fields())[0]
            return {"ok": True, "status": 200, "data": data, "idempotent": True}

        vals = {
            "name": cm_id,
            "session_id": session_id,
            "movement_type": movement_type,
            "amount": amount,
            "reason": reason,
            "pos_name": pos_name,
            "user_name": user_name,
        }
        if movement_time:
            vals["movement_time"] = movement_time

        rec = Mov.create(vals)
        data = rec.read(self._fields())[0]
        return {"ok": True, "status": 200, "data": data}

    def _fields(self):
        return ["id", "name", "session_id", "movement_type", "amount", "reason", "pos_name", "user_name", "movement_time"]

    # ===== LIST =====
    def _list(self, env, kw):
        q = (kw.get("q") or "").strip()
        session_id = (kw.get("session_id") or "").strip()
        pos_name = (kw.get("pos_name") or "").strip()
        movement_type = (kw.get("type") or "").strip().lower()

        try:
            page = int(kw.get("page") or 1)
            limit = int(kw.get("limit") or 20)
        except ValueError:
            return self._err("page/limit must be integer", 400)

        page = max(page, 1)
        limit = min(max(limit, 1), 200)
        offset = (page - 1) * limit
        order = (kw.get("order") or "id desc").strip()

        Mov = env["pos.cash.movement"].sudo()
        domain = []
        if q:
            domain += ["|", ("name", "ilike", q), ("reason", "ilike", q)]
        if session_id:
            domain += [("session_id", "=", session_id)]
        if pos_name:
            domain += [("pos_name", "=", pos_name)]
        if movement_type in ("cash_in", "cash_out"):
            domain += [("movement_type", "=", movement_type)]

        total = Mov.search_count(domain)
        recs = Mov.search(domain, limit=limit, offset=offset, order=order)
        rows = recs.read(self._fields())

        return {
            "ok": True,
            "status": 200,
            "paging": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": int(math.ceil(total / float(limit))) if limit else 1,
            },
            "data": rows,
        }
