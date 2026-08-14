# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request
from .utils import require_api_key_plw, require_jwt_plw, _cors_headers
from ..repositories.checkout_repository import CheckoutRepository
from ..domain.use_cases.get_active_tables import GetActiveTablesUseCase
from ..domain.use_cases.process_checkout import ProcessCheckoutUseCase
from ..domain.use_cases.save_payment_evidence import SavePaymentEvidenceUseCase
from ..domain.use_cases.pay_order import PayOrderUseCase
from ..domain.use_cases.move_bill_table import MoveBillTableUseCase


class CheckoutController(http.Controller):

    @http.route("/api/pos/tables", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_tables(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        repo = CheckoutRepository(request.env)
        use_case = GetActiveTablesUseCase(repo)

        company_id = kw.get("company_id")
        config_pos_id = kw.get("config_pos_id")

        result = use_case.execute(company_id=company_id, pos_id=config_pos_id)

        if not result.get("success", False):
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route("/api/pos/checkout", type="http", auth="none", methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def pos_checkout(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        # Parse request body
        try:
            payload = json.loads(request.httprequest.data)
        except Exception:
            err_payload = {
                "success": False, 
                "message": "Invalid JSON request body", 
                "status": 400
            }
            return request.make_json_response(err_payload, status=400, headers=_cors_headers())

        repo = CheckoutRepository(request.env)
        use_case = ProcessCheckoutUseCase(repo)

        result = use_case.execute(payload)

        if not result.get("success", False):
            # The use case catches its own exceptions, so Odoo never sees one
            # and would happily commit the half-built order. Roll back here or
            # a failed checkout leaves an orphan draft order behind.
            request.env.cr.rollback()
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route("/api/pos/payment/evidence", type="http", auth="none", methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def save_payment_evidence(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            err_payload = {
                "success": False, 
                "message": "Invalid JSON request body", 
                "status": 400
            }
            return request.make_json_response(err_payload, status=400, headers=_cors_headers())

        order_id_or_ref = body.get("order_id") or body.get("pos_reference")
        payload = body.get("payload")

        repo = CheckoutRepository(request.env)
        use_case = SavePaymentEvidenceUseCase(repo)

        result = use_case.execute(order_id_or_ref, payload)

        if not result.get("success", False):
            request.env.cr.rollback()
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route("/api/pos/order/mark_paid", type="http", auth="none", methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def pay_order(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            err_payload = {
                "success": False, 
                "message": "Invalid JSON request body", 
                "status": 400
            }
            return request.make_json_response(err_payload, status=400, headers=_cors_headers())

        order_id_or_ref = body.get("order_id") or body.get("pos_reference")

        repo = CheckoutRepository(request.env)
        use_case = PayOrderUseCase(repo)

        result = use_case.execute(order_id_or_ref)

        if not result.get("success", False):
            # mark_order_as_paid writes payment, picking and bill state, so a
            # half-applied failure must not survive the response.
            request.env.cr.rollback()
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route("/api/pos/bill/move_table", type="http", auth="none", methods=["POST", "OPTIONS"], csrf=False)
    @require_jwt_plw
    def move_bill_table(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            err_payload = {
                "success": False,
                "message": "Invalid JSON request body",
                "status": 400
            }
            return request.make_json_response(err_payload, status=400, headers=_cors_headers())

        config_pos_id = body.get("config_pos_id")
        bill_id = body.get("bill_id")
        table_id = body.get("table_id")

        repo = CheckoutRepository(request.env)
        use_case = MoveBillTableUseCase(repo)

        result = use_case.execute(config_pos_id=config_pos_id, bill_id=bill_id, table_id=table_id)

        if not result.get("success", False):
            request.env.cr.rollback()
            err_payload = {
                "success": False,
                "message": result.get("error", "Error"),
                "status": result.get("status", 400)
            }
            if result.get("code") == "TABLE_OCCUPIED":
                err_payload["code"] = "TABLE_OCCUPIED"
                err_payload["data"] = {"existing_bill_id": result.get("existing_bill_id")}
            
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())
