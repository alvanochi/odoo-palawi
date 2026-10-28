# -*- coding: utf-8 -*-
"""Versi terenkripsi (v2) dari endpoint POS.

Prosesnya sama persis dengan v1 -- controller ini hanya mendekripsi body POST
lalu menyerahkannya ke logika v1 yang sama. Format amplop ada di
services/payload_crypto.py.

    /api/pos/membership         -> /api/pos/v2/membership
    /api/pos/order              -> /api/pos/v2/order
    /api/pos/order/pay          -> /api/pos/v2/order/pay
    /api/pos/coupons/validate   -> /api/pos/v2/coupons/validate

GET (daftar membership / order) tidak punya body, jadi diteruskan apa adanya.
"""
import json
import logging
import uuid

from odoo import http
from odoo.http import request

from ..services.payload_crypto import PayloadError, decrypt_body
from .pos_membership_api import PosMembershipApi
from .pos_order_api import PosOrderApi
from .promo_api import PromoApi

_logger = logging.getLogger(__name__)

CORS_HEADERS = "Content-Type, login, password, company-id, db, api_key, api-key"


class PosSecureV2Api(http.Controller):

    def _preflight(self, methods):
        return request.make_response("OK", headers=[
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", methods),
            ("Access-Control-Allow-Headers", CORS_HEADERS),
        ])

    def _payload_error(self, e):
        return request.make_response(
            json.dumps({"success": False, "ok": False, "status": e.status,
                        "message": e.message, "error": e.message}),
            headers=[("Content-Type", "application/json"),
                     ("Access-Control-Allow-Origin", "*")],
            status=e.status,
        )

    def _decrypt(self, path):
        return decrypt_body(request.env, request.httprequest.data, path)

    # ------------------------------------------------------------------
    # /api/pos/v2/membership
    # ------------------------------------------------------------------
    @http.route("/api/pos/v2/membership", type="http", auth="none",
                methods=["GET", "POST", "OPTIONS"], csrf=False)
    def membership(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._preflight("GET,POST,OPTIONS")

        v1 = PosMembershipApi()
        try:
            if request.httprequest.method == "GET":
                result = v1._list_membership(request.env, kw)
            else:
                body = self._decrypt("/api/pos/v2/membership")
                result = v1._create_member(request.env, body)
            return v1._resp(result, result.get("status", 200))
        except PayloadError as e:
            return self._payload_error(e)
        except Exception as e:
            _logger.exception("POS MEMBERSHIP V2 API ERROR")
            return v1._resp(v1._err(str(e), 400), 400)

    # ------------------------------------------------------------------
    # /api/pos/v2/order
    # ------------------------------------------------------------------
    @http.route("/api/pos/v2/order", type="http", auth="none",
                methods=["GET", "POST", "OPTIONS"], csrf=False)
    def order(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._preflight("GET,POST,OPTIONS")

        v1 = PosOrderApi()
        req_id = str(uuid.uuid4())
        try:
            env = v1._api_env(request.env)

            if request.httprequest.method == "GET":
                result = v1._list_orders(env, kw)
                if isinstance(result, dict):
                    result.setdefault("req_id", req_id)
                return v1._resp(result, result.get("status", 200) if isinstance(result, dict) else 200)

            body = self._decrypt("/api/pos/v2/order")
            return v1.create_order_from_body(env, body, req_id)
        except PayloadError as e:
            return self._payload_error(e)
        except Exception:
            _logger.exception("POS ORDER V2 API ERROR req_id=%s", req_id)
            return v1._resp(v1._err(f"Internal server error (req_id={req_id})", 500), 500)

    # ------------------------------------------------------------------
    # /api/pos/v2/order/pay
    # ------------------------------------------------------------------
    @http.route("/api/pos/v2/order/pay", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    def order_pay(self, **kw):
        """Sama dengan /api/pos/order/pay, dengan tiga perbedaan:

        - id order dibaca dari body terenkripsi (key "id"), bukan query string,
          jadi ikut terlindungi. Query string diabaikan.
        - hanya order berstatus draft yang bisa dibayar (v1 membiarkan order
          yang sudah paid dibayar lagi).
        - bill_id harus milik POS yang sama dengan order dan belum terhubung
          ke order lain; bill_id menandai order lunas walau nominal kurang.
        """
        if request.httprequest.method == "OPTIONS":
            return self._preflight("POST,OPTIONS")

        v1 = PosOrderApi()
        try:
            body = self._decrypt("/api/pos/v2/order/pay")
        except PayloadError as e:
            return self._payload_error(e)

        try:
            env = v1._api_env(request.env)

            order_id = v1._parse_int(body.get("id"))
            if not order_id:
                return v1._resp(v1._err("Missing id", 400), 400)

            order = env["pos.order"].browse(order_id)
            if not order.exists():
                return v1._resp(v1._err("Order not found", 404), 404)
            if order.state != "draft":
                return v1._resp(v1._err(
                    "Order cannot be paid because state is '%s'" % order.state,
                    409, code="ORDER_NOT_DRAFT",
                    data={"id": order.id, "state": order.state}), 409)

            bill_id = v1._parse_int(body.get("bill_id"))
            if bill_id:
                bill = env["poskas.bill"].sudo().browse(bill_id)
                if bill.exists() and (
                        bill.config_id != order.session_id.config_id
                        or (bill.pos_order_id and bill.pos_order_id != order)):
                    return v1._resp(v1._err(
                        "bill_id does not belong to this order", 409,
                        code="BILL_MISMATCH"), 409)

            return v1.pay_order_from_body(env, order_id, body)
        except Exception as e:
            _logger.exception("POS ORDER PAY V2 API ERROR")
            return v1._resp(v1._err(str(e), 400), 400)

    # ------------------------------------------------------------------
    # /api/pos/v2/coupons/validate
    # ------------------------------------------------------------------
    @http.route("/api/pos/v2/coupons/validate", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    def validate_coupon(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._preflight("POST,OPTIONS")

        v1 = PromoApi()
        denied = v1._authenticate()
        if denied:
            return denied
        if not v1._loyalty_ready():
            return v1._err("Module 'loyalty' is not installed", 400)

        try:
            body = self._decrypt("/api/pos/v2/coupons/validate")
        except PayloadError as e:
            return self._payload_error(e)
        return v1.validate_coupon_from_body(body)
