# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request
from .utils import _cors_headers, _jwt_secret
from ..repositories.user_repository import UserRepository
from ..repositories.company_repository import CompanyRepository
from ..repositories.auth_service import OdooAuthService
from ..repositories.otp_repository import OtpRepository
from ..repositories.mail_service import MailService
from ..domain.services.jwt_service import JWTService
from ..domain.use_cases.sso_login import SsoLoginUseCase
from ..domain.use_cases.employee_login import EmployeeLoginUseCase
from ..domain.use_cases.request_otp import RequestOtpUseCase
from ..domain.use_cases.verify_otp import VerifyOtpUseCase

class AuthController(http.Controller):

    @http.route('/api/employee/login/sso', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def login_employee_sso(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        id_token = (body.get('id_token') or '').strip()

        env = request.env
        user_repo = UserRepository(env)
        otp_repo = OtpRepository(env)
        mail_service = MailService(env)

        # Get duration from System Parameter, default is 10 minutes (600 seconds)
        duration_param = env['ir.config_parameter'].sudo().get_param('api_otp_duration_seconds', '600')
        try:
            otp_duration_seconds = int(duration_param)
        except Exception:
            otp_duration_seconds = 600

        # Load google_client_id
        google_client_id = env['ir.config_parameter'].sudo().get_param('google_sso_client_id')
        if not google_client_id:
            try:
                import os
                from odoo.modules.module import get_module_path
                base_path = os.path.dirname(os.path.dirname(get_module_path('rest_api_plw')))
                json_path = os.path.join(base_path, 'google-services-econique-pos.json')
                if os.path.exists(json_path):
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                        clients = data.get('client', [])
                        if clients:
                            oauth = clients[0].get('oauth_client', [])
                            if oauth:
                                google_client_id = oauth[0].get('client_id')
            except Exception:
                pass
        if not google_client_id:
            google_client_id = "995897856510-f4t55s8tdqucj7jtake9s0ghnqf46g4a.apps.googleusercontent.com"

        use_case = SsoLoginUseCase(
            user_repo=user_repo,
            otp_repo=otp_repo,
            mail_service=mail_service,
            otp_duration_seconds=otp_duration_seconds,
            google_client_id=google_client_id
        )
        result = use_case.execute(id_token)

        if not result.get("success"):
            return request.make_json_response(
                {'error': result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result.get("data"), headers=_cors_headers())

    @http.route('/api/employee/login', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def login_employee(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())

        try:
            vals = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            vals = {}

        email = (vals.get('email') or vals.get('login') or request.params.get('email') or request.params.get('login') or '').strip()
        password = (vals.get('password') or request.params.get('password') or '')

        # Wire up dependencies
        env = request.env
        user_repo = UserRepository(env)
        company_repo = CompanyRepository(env)
        jwt_service = JWTService(_jwt_secret())
        auth_service = OdooAuthService(env, request.session)

        use_case = EmployeeLoginUseCase(user_repo, company_repo, jwt_service, auth_service)
        result = use_case.execute(email, password)

        if not result.get("success"):
            return request.make_json_response(
                {'error': result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result.get("data"), headers=_cors_headers())

    @http.route('/api/auth/otp/request', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def request_otp(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        email = (body.get('email') or body.get('login') or '').strip()
        password = (body.get('password') or '')

        env = request.env
        user_repo = UserRepository(env)
        otp_repo = OtpRepository(env)
        auth_service = OdooAuthService(env, request.session)
        mail_service = MailService(env)

        # Get duration from System Parameter, default is 10 minutes (600 seconds)
        duration_param = env['ir.config_parameter'].sudo().get_param('api_otp_duration_seconds', '600')
        try:
            otp_duration_seconds = int(duration_param)
        except Exception:
            otp_duration_seconds = 600

        use_case = RequestOtpUseCase(user_repo, otp_repo, auth_service, mail_service, otp_duration_seconds)
        result = use_case.execute(email, password)

        if not result.get("success"):
            return request.make_json_response(
                {'error': result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result.get("data"), headers=_cors_headers())

    @http.route('/api/auth/otp/verify', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def verify_otp(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())

        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        email = (body.get('email') or '').strip()
        otp_code = (body.get('otp') or body.get('otp_code') or '').strip()

        env = request.env
        user_repo = UserRepository(env)
        company_repo = CompanyRepository(env)
        otp_repo = OtpRepository(env)
        jwt_service = JWTService(_jwt_secret())

        use_case = VerifyOtpUseCase(user_repo, company_repo, otp_repo, jwt_service)
        result = use_case.execute(email, otp_code)

        if not result.get("success"):
            return request.make_json_response(
                {'error': result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result.get("data"), headers=_cors_headers())
