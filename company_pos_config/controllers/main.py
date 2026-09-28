# -*- coding: utf-8 -*-
import json
import time
import jwt
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessDenied

# ==========================================
# JWT Authentication Helpers
# ==========================================

def _jwt_secret():
    return request.env['ir.config_parameter'].sudo().get_param('api_jwt_secret') or 'dev-secret-change-me'

def _jwt_issue_pos(user, ttl_seconds=5 * 24 * 60 * 60):  # 5 days expiration
    now = int(time.time())
    payload = {
        "sub": user.id,
        "login": user.login,
        "email": user.email,
        "iat": now,
        "exp": now + ttl_seconds,
        "scopes": ["pos_config"],
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")

def require_jwt_pos(func):
    def wrapper(*args, **kwargs):
        # Handle CORS preflight request
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())
            
        authz = request.httprequest.headers.get('Authorization', '')
        if not authz.startswith('Bearer '):
            return request.make_json_response({"error": "Unauthorized: Missing or invalid token"}, status=401, headers=_cors_headers())
        
        token = authz.split(' ', 1)[1].strip()
        try:
            payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"], options={"verify_sub": False})
            uid = payload.get("sub")
            user = request.env['res.users'].sudo().browse(uid)
            if not user.exists() or not user.active:
                return request.make_json_response({"error": "Unauthorized: User not found or inactive"}, status=401, headers=_cors_headers())
            
            # Put the verified user record in context
            request.update_env(user=user)
            return func(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return request.make_json_response({"error": "Unauthorized: Token has expired"}, status=401, headers=_cors_headers())
        except Exception:
            return request.make_json_response({"error": "Unauthorized: Invalid token"}, status=401, headers=_cors_headers())
            
    return wrapper

# ==========================================
# CORS Headers Helper
# ==========================================
def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


class CompanyPosConfigController(http.Controller):

    # Helper method to format company config data
    def _get_companies_data(self, user):
        companies_data = []
        for company in user.company_ids:
            try:
                wifi_profiles = json.loads(company.wifi_profiles_json or '[]')
            except Exception:
                wifi_profiles = []

            companies_data.append({
                'company_id': company.id,
                'company_name': company.name,
                'pos_config_prefs': {
                    'POS_CONFIG_ID': company.pos_config_id or '',
                    'POS_CONFIG_NAME': company.pos_config_name or '',
                    'server_domain': company.server_domain or '',
                    'offline_mode': company.offline_mode or False,
                    'offline_mode_pin': company.offline_mode_pin or '',
                    'db_name': company.db_name or '',
                    'db_user': company.db_user or '',
                    'db_pass': company.db_pass or '',
                    'primary_color': company.primary_color or '',
                    'secondary_color': company.secondary_color or '',
                    'logo_uri': company.logo_uri or '',
                    'store_name': company.store_name or '',
                    'receipt_title': company.receipt_title or '',
                    'receipt_address': company.receipt_address or '',
                    'wifi_name': company.wifi_name or '',
                    'wifi_pass': company.wifi_pass or '',
                    'soc_ig': company.soc_ig or '',
                    'soc_tiktok': company.soc_tiktok or '',
                    'soc_fb': company.soc_fb or '',
                    'qris_submerchant_id': company.qris_submerchant_id or '',
                    'ip_printer_external': company.ip_printer_external or '',
                    'POS_DISCOUNT_PRODUCT_ID': company.pos_discount_product_id or '',
                    'wifi_profiles_json': wifi_profiles,
                    'printer_paper_width': company.printer_paper_width or '58',
                }
            })
        return companies_data
