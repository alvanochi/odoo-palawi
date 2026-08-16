from odoo import http
from odoo.http import request
import json
import math
import logging

_logger = logging.getLogger(__name__)

class PosMembershipApi(http.Controller):

    @http.route(
        "/api/pos/membership",
        type="http",
        auth="none",
        methods=["GET", "POST", "OPTIONS"],
        csrf=False
    )
    def pos_membership(self, **kw):
        # CORS preflight
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, company-id, db, api_key, api-key"),
            ])

        try:
            if request.httprequest.method == "GET":
                result = self._list_membership(request.env, kw)
                return self._resp(result, result.get("status", 200))

            if request.httprequest.method == "POST":
                payload = request.httprequest.get_data(as_text=True) or "{}"
                body = json.loads(payload)
                result = self._create_member(request.env, body)
                return self._resp(result, result.get("status", 200))

            return self._resp(self._err("Method not allowed", 405), 405)

        except Exception as e:
            _logger.exception("POS MEMBERSHIP API ERROR")
            return self._resp(self._err(str(e), 400), 400)

    def _resp(self, payload, status=200):
        return request.make_response(
            json.dumps(payload),
            headers=[
                ("Content-Type", "application/json"),
                ("Access-Control-Allow-Origin", "*"),
            ],
            status=status
        )

    def _err(self, message, status=400):
        return {"ok": False, "status": status, "error": message}

    # ===== CREATE =====
    def _create_member(self, env, body):
        name = (body.get("name") or "").strip()
        display_name = (body.get("display_name") or "").strip()
        phone = (body.get("phone") or "").strip()
        member_type_id = body.get("member_type_id")

        # validate required
        if not name:
            return self._err("name is required", 400)
        if not display_name:
            return self._err("display_name is required", 400)
        if not phone:
            return self._err("phone is required", 400)
        if not member_type_id:
            return self._err("member_type_id is required", 400)

        try:
            member_type_id = int(member_type_id)
        except:
            return self._err("member_type_id must be integer", 400)

        Partner = env["res.partner"].sudo()

        # inject defaults
        vals = {
            "name": name,
            "display_name": display_name,
            "phone": phone,
            "member_type_id": member_type_id,
            "autopost_bills": "always",   # inject
            # "image_1920": False,        # optional: skip or set False
        }

        # optional: prevent duplicate phone
        # if Partner.search_count([("phone", "=", phone)]) > 0:
        #     return self._err("phone already exists", 409)

        rec = Partner.create(vals)

        # return created data (mirip GET format)
        data = rec.read([
            "id", "name", "email", "phone", "mobile", "active",
            "member_points", "member_type_id",
        ])[0]

        m2o = data.get("member_type_id")
        data["member_type"] = {"id": m2o[0], "name": m2o[1]} if isinstance(m2o, list) and len(m2o) == 2 else None
        data.pop("member_type_id", None)

        return {"ok": True, "status": 200, "data": data}

    # ===== LIST MEMBERSHIP (punya kamu) =====
    def _list_membership(self, env, kw):
        q = (kw.get("q") or "").strip()
        search_no = (kw.get("search_no") or "").strip()
        phone = (kw.get("phone") or "").strip()
        mobile = (kw.get("mobile") or "").strip()

        try:
            page = int(kw.get("page") or 1)
            limit = int(kw.get("limit") or 20)
        except ValueError:
            return self._err("page/limit must be integer", 400)

        page = max(page, 1)
        limit = min(max(limit, 1), 200)
        offset = (page - 1) * limit
        order = (kw.get("order") or "id desc").strip()

        Partner = env["res.partner"].sudo()

        domain = []
        if q:
            domain += ["|", ("name", "ilike", q), ("email", "ilike", q)]
        if search_no:
            domain += ["|", ("phone", "ilike", search_no), ("mobile", "ilike", search_no)]
        if phone:
            domain.append(("phone", "ilike", phone))
        if mobile:
            domain.append(("mobile", "ilike", mobile))

        total = Partner.search_count(domain)
        recs = Partner.search(domain, limit=limit, offset=offset, order=order)

        rows = recs.read([
            "id", "name", "email", "phone", "mobile", "active",
            "member_points", "member_type_id",
        ])

        data = []
        for r in rows:
            m2o = r.get("member_type_id")
            r["member_type"] = {"id": m2o[0], "name": m2o[1]} if isinstance(m2o, list) and len(m2o) == 2 else None
            r.pop("member_type_id", None)
            data.append(r)

        return {
            "ok": True,
            "status": 200,
            "paging": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": int(math.ceil(total / float(limit))) if limit else 1,
            },
            "data": data,
        }
