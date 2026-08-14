# -*- coding: utf-8 -*-

class VerifyOtpUseCase:
    def __init__(self, user_repo, company_repo, otp_repo, jwt_service):
        self.user_repo = user_repo
        self.company_repo = company_repo
        self.otp_repo = otp_repo
        self.jwt_service = jwt_service

    def execute(self, email, otp_code):
        if not email or not otp_code:
            return {"success": False, "error": "Email and OTP code are required", "status": 400}

        # 1. Look up employee
        employee = self.user_repo.find_employee_by_email(email)
        if not employee:
            return {"success": False, "error": "Employee not found", "status": 404}

        user = employee.user_id
        if not user:
            return {"success": False, "error": "Employee has no linked user account", "status": 400}

        # 2. Verify active OTP (in repositories, this checks expiration time and if used)
        otp_rec = self.otp_repo.find_active_otp(user.login, otp_code)
        if not otp_rec:
            return {"success": False, "error": "Kode OTP tidak valid atau sudah kedaluwarsa", "status": 403}

        # 3. Mark OTP as used
        self.otp_repo.mark_as_used(otp_rec)

        # 4. Generate 5-day JWT Token
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
