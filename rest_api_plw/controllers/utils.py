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


def compress_image_bytes(image_bytes, max_bytes=1024 * 1024):
    """Compress image bytes so the size does not exceed max_bytes (default 1MB).

    If the payload is not an image or fails to process, returns the original bytes.
    """
    if not image_bytes or len(image_bytes) <= max_bytes:
        return image_bytes

    try:
        import io
        from PIL import Image
    except ImportError:
        return image_bytes

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return image_bytes

    resample = getattr(getattr(Image, 'Resampling', None), 'LANCZOS', getattr(Image, 'ANTIALIAS', None))

    # Convert non-RGB modes (RGBA, LA, P, CMYK) to RGB for JPEG encoding
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        mask = image.split()[-1] if 'A' in image.mode else None
        background.paste(image, mask=mask)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    # Initial downscale if dimensions are very large (e.g. mobile photo > 1920px)
    max_dim = 1920
    if max(image.size) > max_dim:
        image.thumbnail((max_dim, max_dim), resample)

    # 1. First phase: adjust JPEG quality
    compressed = image_bytes
    for quality in (85, 75, 65, 50, 35):
        out = io.BytesIO()
        image.save(out, format='JPEG', quality=quality, optimize=True)
        compressed = out.getvalue()
        if len(compressed) <= max_bytes:
            return compressed

    # 2. Second phase: downscale dimensions until under max_bytes
    while len(compressed) > max_bytes and max(image.size) > 300:
        new_w = max(1, int(image.width * 0.75))
        new_h = max(1, int(image.height * 0.75))
        image = image.resize((new_w, new_h), resample)
        out = io.BytesIO()
        image.save(out, format='JPEG', quality=60, optimize=True)
        compressed = out.getvalue()

    return compressed
