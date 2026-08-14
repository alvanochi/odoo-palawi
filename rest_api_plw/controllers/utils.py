# -*- coding: utf-8 -*-
import json
import jwt
from odoo import http
from odoo.http import request

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, api-key",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    }

def _jwt_secret():
    return request.env['ir.config_parameter'].sudo().get_param('api_jwt_secret') or 'dev-secret-change-me'

def require_jwt_plw(func):
    def wrapper(*args, **kwargs):
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
            
            request.update_env(user=user)
            return func(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return request.make_json_response({"error": "Unauthorized: Token has expired"}, status=401, headers=_cors_headers())
        except Exception:
            return request.make_json_response({"error": "Unauthorized: Invalid token"}, status=401, headers=_cors_headers())
            
    return wrapper


def require_api_key_plw(func):
    def wrapper(*args, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())
            
        api_key = request.httprequest.headers.get("api-key")
        if not api_key:
            return request.make_json_response({"success": False, "message": "No API key provided", "status": 401}, status=401, headers=_cors_headers())
            
        # Read static API key from Odoo System Parameters
        IrParam = request.env["ir.config_parameter"].sudo()
        valid_key = IrParam.get_param("api_key_palawi", default=False)
        
        if not valid_key:
            return request.make_json_response({"success": False, "message": "API key not configured on server (api_key_palawi not set)", "status": 500}, status=500, headers=_cors_headers())
            
        if api_key != valid_key:
            return request.make_json_response({"success": False, "message": "Invalid API key", "status": 401}, status=401, headers=_cors_headers())
            
        # Update request env to superuser context
        request.update_env(user=1, su=True)
        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Shared response / parsing helpers
#
# The api-key endpoints all answer with the same envelope, so the boilerplate
# lives here instead of being repeated in every controller.
# ---------------------------------------------------------------------------

def _json_ok(data, status=200, **extra):
    payload = {"success": True, "data": data}
    payload.update(extra)
    return request.make_json_response(payload, status=status, headers=_cors_headers())


def _json_err(message, status=400):
    return request.make_json_response(
        {"success": False, "message": message, "status": status},
        status=status,
        headers=_cors_headers(),
    )


def _json_result(result):
    """Turn a use case result dict into an HTTP response."""
    if not result.get("success", False):
        return _json_err(result.get("error", "Error"), result.get("status", 400))
    return request.make_json_response(result, status=200, headers=_cors_headers())


def _parse_int(value, name, required=True, default=None):
    """-> (int|None, error_message|None)"""
    if value in (None, "", False):
        if required:
            return None, f"Missing required parameter '{name}'"
        return default, None
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, f"Invalid '{name}', must be an integer"


def _parse_csv(value, default=None):
    """'paid,processing' -> ['paid', 'processing']. 'all' / empty -> default."""
    if not value or str(value).strip().lower() == "all":
        return default
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _parse_json_body():
    """-> (dict, None) | (None, error_message)"""
    try:
        body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
    except Exception:
        return None, "Invalid JSON request body"
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object"
    return body, None


def _api_timezone():
    """Timezone used to decide what 'today' means for POS sessions.

    The api-key decorator runs as superuser (uid 1) whose tz is usually UTC,
    so we cannot rely on the request user's timezone here.
    """
    return request.env['ir.config_parameter'].sudo().get_param('api_pos_timezone') or 'Asia/Jakarta'
