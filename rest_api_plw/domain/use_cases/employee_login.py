# -*- coding: utf-8 -*-

class EmployeeLoginUseCase:
    def __init__(self, user_repo, company_repo, jwt_service, auth_service):
        self.user_repo = user_repo
        self.company_repo = company_repo
        self.jwt_service = jwt_service
        self.auth_service = auth_service

    def execute(self, email, password):
        if not email or not password:
            return {"success": False, "error": "Email/login and password are required", "status": 400}

        employee = self.user_repo.find_employee_by_email(email)
        if not employee:
            return {"success": False, "error": "Employee not found", "status": 401}

        if not employee.user_id:
            return {"success": False, "error": "Employee has no linked Odoo user account", "status": 400}

        user = employee.user_id

        # Authenticate
        is_valid = self.auth_service.authenticate(user.login, password)
        if not is_valid:
            return {"success": False, "error": "Invalid credentials", "status": 401}

        # Issue 5-day JWT token (matching original employee login spec)
        token = self.jwt_service.issue_token_with_ttl(user.id, user.login, user.email, ttl_seconds=5 * 24 * 60 * 60)
        companies_data = self.company_repo.get_companies_config_by_user_id(user.id)

        return {
            "success": True,
            "data": {
                'api_token': token,
                'user_id': user.id,
                'user_login': user.login,
                'employee_id': employee.id,
                'employee_name': employee.name,
                'companies': companies_data
            }
        }
