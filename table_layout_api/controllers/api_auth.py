"""Shared API-key auth + JSON response helpers for table_layout_api.

Mirrors the pattern already in production for coa_api /
sales_order_api: a single key in a System Parameter, compared with
hmac.compare_digest, where an EMPTY configured key means "not configured yet"
(503) -- never "open access". See design.md for the full rationale.
"""
import functools
import hmac
import json
import logging

from odoo import SUPERUSER_ID
from odoo.http import request

_logger = logging.getLogger(__name__)

API_KEY_PARAM = 'table_layout_api.key'


def _json(data, status=200):
    return request.make_response(
        json.dumps(data),
        status=status,
        headers=[
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ],
    )


def _svg(body, status=200):
    """Same idea as _json but for the SVG-rendering route -- header-auth
    only (see render-floor-svg/requirements.md), so this is never meant to
    be hit as a bare <img src> URL; it's a normal authenticated fetch whose
    body the caller inlines."""
    return request.make_response(
        body,
        status=status,
        headers=[
            ('Content-Type', 'image/svg+xml; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ],
    )


def _error(status, code, message):
    return _json({'error': {'code': code, 'message': message}}, status=status)


def _supplied_key(headers):
    key = headers.get('X-API-Key')
    if key:
        return key.strip()
    auth = headers.get('Authorization', '') or ''
    if auth[:7].lower() == 'bearer ':
        return auth[7:].strip()
    return ''


class ApiError(Exception):
    """Raised by any helper below the route layer; require_api_key's wrapper
    turns it into the matching HTTP response, so individual routes don't
    each need their own try/except around every scoping call."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def response(self):
        return _error(self.status, self.code, self.message)


def require_api_key(func):
    """Checks the API key, then promotes the request env to superuser --
    same order and same reasoning as coa_api: "is this API configured
    at all" is checked (and answered with 503) before "is this key right"
    (401), so an unconfigured install never *looks* like a real, just-wrong
    key to whoever is probing it.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        configured = request.env['ir.config_parameter'].sudo().get_param(API_KEY_PARAM)
        if not configured:
            _logger.warning('table_layout_api: called with no API key configured yet.')
            return _error(503, 'api_not_configured', 'This API is not configured yet.')

        supplied = _supplied_key(request.httprequest.headers)
        if not supplied or not hmac.compare_digest(supplied, configured):
            return _error(401, 'unauthorized', 'Missing or invalid API key.')

        # Same accepted trade-off as coa_api: this key is DB-wide read
        # access, so every route built on this module must stay read-only.
        request.update_env(user=SUPERUSER_ID, su=True)
        try:
            return func(self, *args, **kwargs)
        except ApiError as exc:
            return exc.response()

    return wrapper
