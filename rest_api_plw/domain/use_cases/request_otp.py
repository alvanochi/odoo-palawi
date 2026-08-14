# -*- coding: utf-8 -*-
import random
from datetime import datetime, timedelta

class RequestOtpUseCase:
    def __init__(self, user_repo, otp_repo, auth_service, mail_service, otp_duration_seconds):
        self.user_repo = user_repo
        self.otp_repo = otp_repo
        self.auth_service = auth_service
        self.mail_service = mail_service
        self.otp_duration_seconds = otp_duration_seconds

    def execute(self, email, password):
        if not email or not password:
            return {"success": False, "error": "Email/login and password are required", "status": 400}

        # 1. Search employee to match email
        employee = self.user_repo.find_employee_by_email(email)
        if not employee:
            return {"success": False, "error": "Employee not found", "status": 401}

        if not employee.user_id:
            return {"success": False, "error": "Employee has no linked Odoo user account", "status": 400}

        user = employee.user_id

        # 2. Authenticate employee password
        is_valid = self.auth_service.authenticate(user.login, password)
        if not is_valid:
            return {"success": False, "error": "Invalid credentials", "status": 401}

        # 3. Find company & Head Users (Atasan)
        company_id = employee.company_id.id
        head_users = self.user_repo.find_head_users_by_company(company_id)

        if not head_users:
            return {
                "success": False,
                "error": "Tidak ada Head User (Atasan) yang dikonfigurasi untuk perusahaan ini.",
                "status": 400
            }

        # 4. Generate 6-digit numeric OTP
        otp_code = str(random.randint(100000, 999999))

        # 5. Store OTP with expiration
        expired_at = datetime.now() + timedelta(seconds=self.otp_duration_seconds)
        self.otp_repo.create_otp(user.login, otp_code, expired_at)

        # 6. Send OTP to all Head Users
        duration_minutes = int(self.otp_duration_seconds / 60)
        for head in head_users:
            recipient_email = head.email or head.login
            recipient_name = head.name
            if recipient_email:
                self.mail_service.send_otp_email(
                    recipient_email=recipient_email,
                    recipient_name=recipient_name,
                    employee_name=employee.name,
                    otp_code=otp_code,
                    duration_minutes=duration_minutes
                )

        return {
            "success": True,
            "data": {
                "message": "Kode OTP telah dikirimkan ke email atasan Anda.",
                "email": user.login
            }
        }
