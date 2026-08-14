# -*- coding: utf-8 -*-
from odoo.exceptions import UserError

class SavePaymentEvidenceUseCase:
    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, order_id_or_ref, payload):
        if not order_id_or_ref:
            return {"success": False, "error": "Missing parameter 'order_id' or 'pos_reference'", "status": 400}
        if payload is None:
            return {"success": False, "error": "Missing parameter 'payload'", "status": 400}

        try:
            evidence_id = self.checkout_repo.create_payment_evidence(order_id_or_ref, payload)
            return {
                "success": True,
                "data": {
                    "message": "Evidence saved successfully",
                    "evidence_id": evidence_id
                }
            }
        except UserError as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
