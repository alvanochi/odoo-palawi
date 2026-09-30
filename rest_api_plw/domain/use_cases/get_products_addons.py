# -*- coding: utf-8 -*-

class GetProductsAddonsUseCase:
    def __init__(self, product_repo):
        self.product_repo = product_repo

    def execute(self, product_ids, base_url=""):
        if not product_ids:
            return {"success": False, "error": "Missing required parameter 'product_ids'", "status": 400}

        if not isinstance(product_ids, list):
            return {"success": False, "error": "'product_ids' must be a list", "status": 400}

        # Sanitize product_ids
        clean_ids = []
        for val in product_ids:
            try:
                clean_ids.append(int(val))
            except (TypeError, ValueError):
                continue

        if not clean_ids:
            return {"success": False, "error": "'product_ids' list contains no valid integers", "status": 400}

        try:
            addons = self.product_repo.get_products_addons(clean_ids, base_url=base_url)
            return {
                "success": True,
                "data": addons
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
