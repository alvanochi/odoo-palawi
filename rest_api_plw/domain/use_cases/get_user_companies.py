# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class GetUserCompaniesUseCase:
    def __init__(self, company_repo):
        self.company_repo = company_repo

    def execute(self, user_id):
        try:
            companies = self.company_repo.find_allowed_companies(user_id)
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}

        if companies is None:
            return {"success": False, "error": f"User ID {user_id} does not exist", "status": 404}

        return {"success": True, "data": companies}
