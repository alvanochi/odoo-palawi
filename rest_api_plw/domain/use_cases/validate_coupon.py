# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class ValidateCouponUseCase:
    def __init__(self, promotion_repo):
        self.promotion_repo = promotion_repo

    def execute(self, pos_config_id, code, partner_id=None, pricelist_id=None):
        if not code:
            return {"success": False, "error": "Missing required parameter 'code'", "status": 400}

        try:
            result = self.promotion_repo.validate_coupon_code(
                pos_config_id, code, partner_id, pricelist_id)
            # A wrong or expired code is a normal validation outcome, not an
            # HTTP error: the client shows result.message as-is.
            return {"success": True, "data": result}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
