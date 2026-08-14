# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError
from ..services.promotion_matcher import build_cart_data, match_programs


class GetMatchedPromotionsUseCase:
    def __init__(self, product_repo, promotion_repo, company_repo):
        self.product_repo = product_repo
        self.promotion_repo = promotion_repo
        self.company_repo = company_repo

    def execute(self, cart_items, user_id, company_id):
        if not isinstance(cart_items, list):
            return {"success": False, "error": "Cart/products must be a list of items", "status": 400}

        company = self.company_repo.resolve_allowed_company(user_id, company_id)
        if not company:
            return {"success": False, "error": "No accessible company for this user", "status": 403}

        product_ids = [item.get('product_id') for item in cart_items if item.get('product_id')]
        try:
            product_ids = [int(pid) for pid in product_ids]
        except (TypeError, ValueError):
            return {"success": False, "error": "product_id must be integers", "status": 400}

        try:
            product_map = self.product_repo.get_products_by_ids_and_company(product_ids, company)
            cart_data = build_cart_data(cart_items, product_map)
            active_programs = self.promotion_repo.get_active_programs_for_company(company)
            return {
                "success": True,
                "matched_programs": match_programs(active_programs, cart_data),
            }
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
