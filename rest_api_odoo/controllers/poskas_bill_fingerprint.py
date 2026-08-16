# -*- coding: utf-8 -*-
import json
import traceback
from odoo import http
from odoo.http import request

class PoskasBillFingerprintController(http.Controller):

    def _resp(self, payload, status=200):
        body = json.dumps(payload, default=str)
        return request.make_response(body, headers=[
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, api-key, company-id, db"),
        ], status=status)

    def _parse_json_body(self):
        raw = request.httprequest.data or b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    @http.route("/api/pos/bill/fingerprint", type="http", auth="public", methods=["OPTIONS"], csrf=False)
    def bill_fingerprint_options(self, **kw):
        return self._resp({"success": True}, status=200)

    @http.route("/api/pos/bill/fingerprint", type="http", auth="public", methods=["POST"], csrf=False)
    def bill_fingerprint(self, **kw):
        try:
            body = self._parse_json_body()
            if body is None:
                return self._resp({"success": False, "message": "Invalid JSON body"}, status=400)

            pos_config_id = body.get("pos_config_id") or kw.get("pos_config_id")
            try:
                pos_config_id = int(pos_config_id)
            except Exception:
                pos_config_id = 0

            if not pos_config_id:
                return self._resp({"success": False, "message": "pos_config_id is required"}, status=400)

            env = request.env(user=1, su=True)
            BillModel = env["poskas.bill"]

            domain = [
                ("config_id", "=", pos_config_id),
                ("state", "=", "open"),
            ]

            open_count = BillModel.search_count(domain)

            last = BillModel.search(domain, order="write_date desc", limit=1)
            max_write_date = None
            if last and last.write_date:
                max_write_date = last.write_date.strftime("%Y-%m-%d %H:%M:%S")

            fingerprint = f"{open_count}|{max_write_date or ''}"

            return self._resp({
                "success": True,
                "data": {
                    "pos_config_id": pos_config_id,
                    "open_count": open_count,
                    "max_write_date": max_write_date,
                    "fingerprint": fingerprint,
                }
            }, status=200)

        except Exception as e:
            return self._resp({
                "success": False,
                "message": str(e),
                "trace": traceback.format_exc()
            }, status=500)
