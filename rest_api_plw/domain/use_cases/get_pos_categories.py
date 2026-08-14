# -*- coding: utf-8 -*-

class GetPosCategoriesUseCase:
    def __init__(self, product_repo):
        self.product_repo = product_repo

    def execute(self, company_id, config_pos_id=None, base_url=""):
        if not company_id:
            return {"success": False, "error": "Missing required parameter 'company_id'", "status": 400}

        try:
            company_id = int(company_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'company_id'", "status": 400}

        if config_pos_id:
            try:
                config_pos_id = int(config_pos_id)
            except ValueError:
                return {"success": False, "error": "Invalid 'config_pos_id'", "status": 400}

        try:
            categories = self.product_repo.find_pos_categories(
                company_id=company_id,
                config_pos_id=config_pos_id,
                base_url=base_url
            )
            return {
                "success": True,
                "data": [category.to_dict() for category in categories]
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 400}


