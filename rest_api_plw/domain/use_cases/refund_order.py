# -*- coding: utf-8 -*-
from odoo.exceptions import UserError


class RefundOrderUseCase:
    """Create and settle a POS refund order for a paid POS order."""

    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, order_id_or_ref, payment_method_id, reason=None):
        if not order_id_or_ref:
            return {
                "success": False,
                "error": "Missing parameter 'order_id' or 'pos_reference'",
                "status": 400,
            }
        if payment_method_id in (None, "", False):
            return {
                "success": False,
                "error": "Missing required parameter 'payment_method_id'",
                "status": 400,
            }

        try:
            data = self.checkout_repo.refund_order(
                order_id_or_ref=order_id_or_ref,
                payment_method_id=payment_method_id,
                reason=reason,
            )
            return {
                "success": True,
                "message": "POS Order refunded successfully",
                "data": data,
            }
        except UserError as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
