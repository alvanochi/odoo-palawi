# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class GetPricelistsUseCase:
    def __init__(self, pricelist_repo):
        self.pricelist_repo = pricelist_repo

    def execute(self, pos_config_id=None, company_id=None):
        if not pos_config_id and not company_id:
            return {
                "success": False,
                "error": "Missing required parameter 'pos_config_id' (or 'company_id')",
                "status": 400,
            }

        try:
            if pos_config_id:
                pricelists = self.pricelist_repo.find_pricelists_for_config(pos_config_id)
            else:
                pricelists = self.pricelist_repo.find_pricelists_for_company(company_id)
            return {"success": True, "data": pricelists}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class GetPricelistPricesUseCase:
    def __init__(self, pricelist_repo):
        self.pricelist_repo = pricelist_repo

    def execute(self, pricelist_id, items, partner_id=None, pos_config_id=None):
        if not pricelist_id:
            return {"success": False, "error": "Missing required parameter 'pricelist_id'", "status": 400}
        if not isinstance(items, list) or not items:
            return {"success": False, "error": "'items' must be a non-empty list", "status": 400}

        try:
            data = self.pricelist_repo.compute_prices(
                pricelist_id=pricelist_id,
                items=items,
                partner_id=partner_id,
                pos_config_id=pos_config_id,
            )
            return {"success": True, "data": data}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
