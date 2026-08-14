# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

class ProcessCheckoutUseCase:
    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, payload):
        config_pos_id = payload.get("config_pos_id")
        detail_product = payload.get("detail_product")

        if not config_pos_id:
            return {"success": False, "error": "Missing required parameter 'config_pos_id'", "status": 400}
        if not detail_product or not isinstance(detail_product, list):
            return {"success": False, "error": "Missing or invalid parameter 'detail_product' (must be a list)", "status": 400}

        try:
            config_pos_id = int(config_pos_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'config_pos_id'", "status": 400}

        customer_name = payload.get("nama")
        customer_phone = payload.get("no_hp") or payload.get("phone")
        table_id = payload.get("table_id")
        table_number = payload.get("no_meja") or payload.get("table_number")

        pricelist_id = payload.get("pricelist_id")
        if pricelist_id:
            try:
                pricelist_id = int(pricelist_id)
            except (TypeError, ValueError):
                return {"success": False, "error": "Invalid 'pricelist_id'", "status": 400}

        rewards = payload.get("rewards") or []
        if not isinstance(rewards, list):
            return {"success": False, "error": "'rewards' must be a list", "status": 400}

        try:
            checkout_result = self.checkout_repo.process_checkout(
                pos_id=config_pos_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                table_id=table_id,
                table_number=table_number,
                detail_product=detail_product,
                pricelist_id=pricelist_id,
                coupon_code=payload.get("coupon_code") or payload.get("code"),
                rewards=rewards,
                auto_open_session=bool(payload.get("auto_open_session")),
            )
            return {
                "success": True,
                "message": "POS Checkout completed successfully",
                "data": checkout_result.to_dict()
            }
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
        
