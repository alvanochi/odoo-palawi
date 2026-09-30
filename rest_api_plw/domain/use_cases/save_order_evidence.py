# -*- coding: utf-8 -*-
from odoo.exceptions import UserError


class SaveOrderEvidenceUseCase:
    """Upload payment evidence and mark the POS order as paid."""

    def __init__(self, pos_order_repo):
        self.pos_order_repo = pos_order_repo

    def execute(self, order_id, evidence_data):
        if not order_id:
            return {
                "success": False,
                "error": "Missing parameter 'pos_order_id'",
                "status": 400,
            }
        if not evidence_data:
            return {
                "success": False,
                "error": "Missing parameter 'evidence'",
                "status": 400,
            }

        try:
            order = self.pos_order_repo.save_evidence_and_mark_paid(
                order_id=order_id, evidence_data=evidence_data
            )
            return {
                "success": True,
                "message": "Payment evidence uploaded and order marked as paid successfully",
                "data": {
                    "pos_order_id": order.id,
                    "name": order.name,
                    "pos_reference": order.pos_reference,
                    "state": order.state,
                    "amount_total": order.amount_total,
                    "amount_paid": order.amount_paid,
                },
            }
        except UserError as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
