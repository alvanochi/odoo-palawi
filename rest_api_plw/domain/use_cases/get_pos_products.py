# -*- coding: utf-8 -*-

class GetPosProductsUseCase:
    def __init__(self, product_repo):
        self.product_repo = product_repo

    def execute(self, company_id, config_pos_id, pos_categ_id=None, search=None, page=1, limit=10, base_url=""):
        if not company_id:
            return {"success": False, "error": "Missing required parameter 'company_id'", "status": 400}
        if not config_pos_id:
            return {"success": False, "error": "Missing required parameter 'config_pos_id'", "status": 400}

        try:
            company_id = int(company_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'company_id'", "status": 400}

        try:
            config_pos_id = int(config_pos_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'config_pos_id'", "status": 400}

        try:
            products = self.product_repo.find_pos_products(
                company_id=company_id,
                config_pos_id=config_pos_id,
                pos_categ_id=pos_categ_id,
                search=search,
                page=page,
                limit=limit,
                base_url=base_url
            )
            return {
                "success": True,
                "data": [product.to_dict() for product in products]
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 400}

