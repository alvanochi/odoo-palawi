# -*- coding: utf-8 -*-
from odoo.exceptions import UserError

class PayOrderUseCase:
    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, order_id_or_ref, payment_method_id=None):
        if not order_id_or_ref:
            return {"success": False, "error": "Missing parameter 'order_id' or 'pos_reference'", "status": 400}

        try:
            payment = self.checkout_repo.mark_order_as_paid(order_id_or_ref, payment_method_id=payment_method_id)
            return {
                "success": True,
                "data": {
                    "message": "Order and bills marked as paid successfully",
                    "payment": payment
                }
            }
        except UserError as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
