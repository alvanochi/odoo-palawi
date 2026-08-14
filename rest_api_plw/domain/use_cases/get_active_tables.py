# -*- coding: utf-8 -*-

class GetActiveTablesUseCase:
    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, company_id, pos_id=None):
        if not company_id:
            return {"success": False, "error": "Missing required parameter 'company_id'", "status": 400}

        try:
            company_id = int(company_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'company_id'", "status": 400}

        try:
            tables = self.checkout_repo.find_active_tables(company_id=company_id, pos_id=pos_id)
            return {
                "success": True,
                "data": tables
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
