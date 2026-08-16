# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError
import json
import uuid
import logging

_logger = logging.getLogger(__name__)


class PosOrderDetailApi(http.Controller):

    @http.route(
        "/api/pos/order/<int:order_id>",
        type="http",
        auth="none",
        methods=["GET", "OPTIONS"],
        csrf=False
    )
    def pos_order_detail(self, order_id, **kw):
        # CORS preflight
        if request.httprequest.method == "OPTIONS":
            return request.make_response("OK", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, login, password, api-key, api_key, company-id"),
            ])

        req_id = str(uuid.uuid4())
        try:
            env = self._api_env(request.env)

            include_lines = self._parse_bool(kw.get("include_lines"), True)
            include_payments = self._parse_bool(kw.get("include_payments"), True)
            include_stock = self._parse_bool(kw.get("include_stock"), True)
            include_invoice = self._parse_bool(kw.get("include_invoice"), True)

            order = env["pos.order"].sudo().browse(int(order_id))
            if not order.exists():
                return self._resp(self._err(f"Order not found (req_id={req_id})", 404), 404)

            data = self._order_detail_to_dict(
                env, order,
                include_lines=include_lines,
                include_payments=include_payments,
                include_stock=include_stock,
                include_invoice=include_invoice
            )

            return self._resp({
                "success": True,
                "req_id": req_id,
                "data": data,
            }, 200)

        except Exception:
            _logger.exception("POS ORDER DETAIL API ERROR req_id=%s order_id=%s", req_id, order_id)
            return self._resp(self._err(f"Internal server error (req_id={req_id})", 500), 500)

    # ---------------- helpers ----------------

    def _api_env(self, env):
        service_uid = env.ref("base.user_admin").id
        return env(user=service_uid, su=True)

    def _resp(self, payload, status=200):
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

    def _parse_bool(self, v, default=False):
        if v is None:
            return default
        return str(v).lower() in ("1", "true", "yes", "y", "on")

    # ---------------- core mapper ----------------

    def _table_name(self, t):
            """Return safe table name across versions/customizations."""
            if not t:
                return None

            # coba field umum
            for f in ("name", "table_number", "code"):
                try:
                    if f in getattr(t, "_fields", {}):
                        v = getattr(t, f, None)
                        if v:
                            return v
                except Exception:
                    pass

            # fallback paling aman
            return getattr(t, "display_name", None) or None


    def _order_detail_to_dict(self, env, order, include_lines=True, include_payments=True, include_stock=True, include_invoice=True):
        order = order.sudo()
        company = order.company_id

        out = {
            "id": order.id,
            "name": order.name,
            "pos_reference": getattr(order, "pos_reference", None),
            "state": getattr(order, "state", None),
            "date_order": fields.Datetime.to_string(order.date_order) if order.date_order else None,

            "amount_total": float(getattr(order, "amount_total", 0.0) or 0.0),
            "amount_tax": float(getattr(order, "amount_tax", 0.0) or 0.0),
            "amount_paid": float(getattr(order, "amount_paid", 0.0) or 0.0) if "amount_paid" in order._fields else None,
            "amount_return": float(getattr(order, "amount_return", 0.0) or 0.0) if "amount_return" in order._fields else None,
            # ✅ field baru
            "change_amount": float(getattr(order, "change_amount", 0.0) or 0.0) if "change_amount" in order._fields else None,
            "name_waiters": None,
            "name_customer": None,
            "bill_id": None,
            "dp_amount": 0.0,
            "is_dp": False,

            "company": {
                "id": company.id if company else None,
                "name": company.name if company else None,
            },

            "session": {
                "id": order.session_id.id if getattr(order, "session_id", False) else None,
                "name": order.session_id.name if getattr(order, "session_id", False) else None,
                "state": order.session_id.state if getattr(order, "session_id", False) else None,
                "config_id": order.session_id.config_id.id if getattr(order, "session_id", False) and order.session_id.config_id else None,
                "config_name": order.session_id.config_id.name if getattr(order, "session_id", False) and order.session_id.config_id else None,
            },

            "partner": {
                "id": order.partner_id.id if getattr(order, "partner_id", False) else None,
                "name": order.partner_id.name if getattr(order, "partner_id", False) else None,
                "phone": order.partner_id.phone if getattr(order, "partner_id", False) else None,
                "mobile": order.partner_id.mobile if getattr(order, "partner_id", False) else None,
                "email": order.partner_id.email if getattr(order, "partner_id", False) else None,
            },

            "user": {
                "id": order.user_id.id if getattr(order, "user_id", False) else None,
                "name": order.user_id.name if getattr(order, "user_id", False) else None,
            },

            "table": None,
            "lines": [],
            "payments": [],
            "stock": None,
            "invoice": None,
        }

        # kalau field ini kebetulan ada juga di pos.order (misal dari module lain),
        # pakai nilainya dulu sebagai default awal sebelum di-override oleh data bill
        if "name_waiters" in order._fields:
            out["name_waiters"] = order.name_waiters or None
        if "name_customer" in order._fields:
            out["name_customer"] = order.name_customer or None

        # bill / DP
        try:
            bill = env["poskas.bill"].sudo().search([
                ("pos_order_id", "=", order.id)
            ], limit=1)

            if bill:
                out["bill_id"] = bill.id
                out["dp_amount"] = float(bill.dp_amount or 0.0)
                out["is_dp"] = bool(bill.is_dp)
                out["name_waiters"] = bill.name_waiters or None
                out["name_customer"] = bill.name_customer or None
        except Exception:
            _logger.exception("FAILED GET BILL DP order_id=%s", order.id)

        # table
        t = None
        if "table_id" in order._fields:
            t = order.table_id

        out["table"] = {
            "id": t.id if t else None,
            "name": self._table_name(t),
            "floor_id": t.floor_id.id if t and getattr(t, "floor_id", False) else None,
            "floor_name": (
                getattr(t.floor_id, "name", None) if t and getattr(t, "floor_id", False)
                else getattr(t.floor_id, "display_name", None) if t and getattr(t, "floor_id", False)
                else None
            ),
        }

        # lines
        if include_lines:
            for l in order.lines:
                prod = l.product_id
                uom = None
                if "uom_id" in l._fields:
                    uom = l.uom_id
                elif "product_uom_id" in l._fields:
                    uom = l.product_uom_id

                out["lines"].append({
                    "id": l.id,
                    "product_id": prod.id if prod else None,
                    "product_name": prod.display_name if prod else None,
                    "qty": float(getattr(l, "qty", 0.0) or 0.0),
                    "price_unit": float(getattr(l, "price_unit", 0.0) or 0.0),
                    "discount": float(getattr(l, "discount", 0.0) or 0.0),
                    "uom_id": uom.id if uom else None,
                    "uom_name": uom.name if uom else None,
                    "price_subtotal": float(getattr(l, "price_subtotal", 0.0) or 0.0) if "price_subtotal" in l._fields else None,
                    "price_subtotal_incl": float(getattr(l, "price_subtotal_incl", 0.0) or 0.0) if "price_subtotal_incl" in l._fields else None,
                    "note": getattr(l, "note", None) if "note" in l._fields else None,
                    "customer_note": getattr(l, "customer_note", None) if "customer_note" in l._fields else None,
                    "name": getattr(l, "name", None),
                })

        # payments
        if include_payments:
            pay_ids = getattr(order, "payment_ids", False)
            if pay_ids:
                for p in pay_ids:
                    out["payments"].append({
                        "id": p.id,
                        "amount": float(getattr(p, "amount", 0.0) or 0.0),
                        "payment_date": fields.Datetime.to_string(getattr(p, "payment_date", None)) if getattr(p, "payment_date", None) else None,
                        "payment_method_id": p.payment_method_id.id if getattr(p, "payment_method_id", False) else None,
                        "payment_method_name": p.payment_method_id.name if getattr(p, "payment_method_id", False) else None,
                        "ref": getattr(p, "payment_reference", None) or getattr(p, "ref", None) or getattr(p, "name", None),
                    })

        # stock
        if include_stock:
            stock_block = {
                "picking_ids": [],
                "pickings": [],
            }

            pickings = getattr(order, "picking_ids", False)
            if pickings:
                stock_block["picking_ids"] = pickings.ids

                for pk in pickings:
                    mv_lines = []
                    mls = getattr(pk, "move_line_ids", False)

                    if mls:
                        for ml in mls:
                            mv_lines.append({
                                "id": ml.id,
                                "product_id": ml.product_id.id if ml.product_id else None,
                                "product_name": ml.product_id.display_name if ml.product_id else None,
                                "qty_done": float(getattr(ml, "qty_done", 0.0) or 0.0),
                                "reserved_uom_qty": float(getattr(ml, "reserved_uom_qty", 0.0) or 0.0) if "reserved_uom_qty" in ml._fields else None,
                                "uom_id": ml.product_uom_id.id if getattr(ml, "product_uom_id", False) else None,
                                "uom_name": ml.product_uom_id.name if getattr(ml, "product_uom_id", False) else None,
                            })

                    stock_block["pickings"].append({
                        "id": pk.id,
                        "name": pk.name,
                        "state": pk.state,
                        "picking_type_id": pk.picking_type_id.id if pk.picking_type_id else None,
                        "picking_type_name": pk.picking_type_id.name if pk.picking_type_id else None,
                        "location_id": pk.location_id.id if pk.location_id else None,
                        "location_name": pk.location_id.display_name if pk.location_id else None,
                        "location_dest_id": pk.location_dest_id.id if pk.location_dest_id else None,
                        "location_dest_name": pk.location_dest_id.display_name if pk.location_dest_id else None,
                        "scheduled_date": fields.Datetime.to_string(getattr(pk, "scheduled_date", None)) if getattr(pk, "scheduled_date", None) else None,
                        "date_done": fields.Datetime.to_string(getattr(pk, "date_done", None)) if getattr(pk, "date_done", None) else None,
                        "move_lines": mv_lines,
                    })

            out["stock"] = stock_block

        # invoice
        if include_invoice:
            invoice = None

            for fn in ("account_move", "invoice_id", "account_move_id"):
                if fn in order._fields and getattr(order, fn):
                    invoice = getattr(order, fn)
                    break

            if invoice:
                out["invoice"] = {
                    "id": invoice.id,
                    "name": invoice.name,
                    "state": getattr(invoice, "state", None),
                    "move_type": getattr(invoice, "move_type", None),
                    "invoice_date": str(getattr(invoice, "invoice_date", None) or "") or None,
                    "amount_total": float(getattr(invoice, "amount_total", 0.0) or 0.0),
                    "amount_residual": float(getattr(invoice, "amount_residual", 0.0) or 0.0) if "amount_residual" in invoice._fields else None,
                }

        return out