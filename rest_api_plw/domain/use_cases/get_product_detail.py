# -*- coding: utf-8 -*-

class GetProductDetailUseCase:
    def __init__(self, product_repo):
        self.product_repo = product_repo

    def execute(self, product_id, base_url=""):
        if not product_id:
            return {"success": False, "error": "Missing required parameter 'product_id'", "status": 400}

        try:
            product_id = int(product_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'product_id'", "status": 400}

        try:
            detail = self.product_repo.get_product_detail(product_id, base_url=base_url)
            if not detail:
                return {"success": False, "error": f"Product with ID {product_id} not found", "status": 404}

            return {
                "success": True,
                "data": detail
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
