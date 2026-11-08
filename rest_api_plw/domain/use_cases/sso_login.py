# -*- coding: utf-8 -*-
import requests
import random
from datetime import datetime, timedelta

# Google documents exactly these two issuer values for ID tokens.
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class SsoLoginUseCase:
    def __init__(self, user_repo, otp_repo, mail_service, otp_duration_seconds, google_client_ids):
        """
        google_client_ids: every OAuth client id whose ID tokens this backend accepts.
        The POS app signs in through two Google clients of the same Cloud project:
          - the WEB client (Play Services flows: Credential Manager / legacy GoogleSignIn)
          - the ANDROID client (browser OAuth flow on devices without Play Services)
        Accepts a set/list, or a single string (optionally comma-separated).
        """
        self.user_repo = user_repo
        self.otp_repo = otp_repo
        self.mail_service = mail_service
        self.otp_duration_seconds = otp_duration_seconds

        if isinstance(google_client_ids, str):
            google_client_ids = google_client_ids.split(",")
        self.google_client_ids = {
            c.strip() for c in (google_client_ids or []) if c and c.strip()
        }

    def execute(self, id_token):
        if not id_token:
            return {"success": False, "error": "Missing parameter 'id_token'", "status": 400}

        if not self.google_client_ids:
            return {"success": False, "error": "Google SSO is not configured (no client id)", "status": 500}

        # 1. Validate id_token with Google TokenInfo API
        try:
            resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=10
            )
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to Google: {str(e)}", "status": 500}

        if resp.status_code != 200:
            try:
                err_data = resp.json()
                msg = err_data.get("error_description") or err_data.get("error") or "Invalid token"
            except Exception:
                msg = "Invalid token"
            return {"success": False, "error": f"Google Token validation failed: {msg}", "status": 401}

        token_info = resp.json()

        # 2. Verify audience and issuer
        #    CHANGED: the audience may be any of the accepted client ids, not one fixed id.
        aud = (token_info.get("aud") or "").strip()
        if aud not in self.google_client_ids:
            return {"success": False, "error": "Google Token audience mismatch", "status": 401}

        #    CHANGED: exact issuer match instead of substring.
        iss = (token_info.get("iss") or "").strip()
        if iss not in _GOOGLE_ISSUERS:
            return {"success": False, "error": "Invalid token issuer", "status": 401}

        #    ADDED: tokeninfo returns email_verified as the string "true".
        email_verified = str(token_info.get("email_verified") or "").lower()
        if email_verified != "true":
            return {"success": False, "error": "Google account email is not verified", "status": 401}

        email = (token_info.get("email") or "").strip().lower()
        if not email:
            return {"success": False, "error": "Email not found in Google Token", "status": 400}

        # 3. Find Employee by email
        employee = self.user_repo.find_employee_by_email(email)
        if not employee:
            return {"success": False, "error": "Employee not found", "status": 401}

        if not employee.user_id:
            return {"success": False, "error": "Employee has no linked Odoo user account", "status": 400}

        user = employee.user_id

        # 4. Find Head Users (Atasan)
        company_id = employee.company_id.id
        head_users = self.user_repo.find_head_users_by_company(company_id)

        if not head_users:
            return {
                "success": False,
                "error": "Tidak ada Head User (Atasan) yang dikonfigurasi untuk perusahaan ini.",
                "status": 400
            }

        # 5. Generate 6-digit numeric OTP
        otp_code = str(random.randint(100000, 999999))

        # 6. Store OTP with expiration
        expired_at = datetime.now() + timedelta(seconds=self.otp_duration_seconds)
        self.otp_repo.create_otp(user.login, otp_code, expired_at)

        # 7. Send OTP to all Head Users
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