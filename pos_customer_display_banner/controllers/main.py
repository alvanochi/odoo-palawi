# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import logging
import time

from odoo import http, fields
from odoo.exceptions import AccessDenied
from odoo.http import request

_logger = logging.getLogger(__name__)


def _b64d(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


class PosCustomerDisplayBannerController(http.Controller):
    """Customer display banner API for POS.

    Headers (same as the existing FE):
        Authorization: Bearer <JWT>
        login: <odoo login>
        password: <odoo password>
        db: <database name>
        api-key: <static key>

    Authentication = ``login`` + ``password`` (verified against res.users).
    Optional hardening via ir.config_parameter (skipped when unset):
        pos_customer_display.api_key     -> must equal the ``api-key`` header
        pos_customer_display.jwt_secret  -> HS256 secret; Bearer JWT must be
                                            valid, not expired and ``sub`` must
                                            equal the authenticated user id.
    Fallbacks when no login/password header: Odoo API key as
    ``Authorization: Bearer <odoo_api_key>``, or a normal session cookie.
    The user must be a POS user.
    """

    # ---------------------------------------------------------------- helpers
    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _error(self, status, message):
        return self._json({'error': message}, status=status)

    def _header(self, name):
        return (request.httprequest.headers.get(name) or '').strip()

    def _bearer(self):
        header = self._header('Authorization')
        if header.lower().startswith('bearer '):
            return header[7:].strip()
        return ''

    @staticmethod
    def _verify_jwt(token, secret):
        """Minimal HS256 verification. Returns the payload dict or None."""
        try:
            head_b64, body_b64, sig_b64 = token.split('.')
            if json.loads(_b64d(head_b64)).get('alg') != 'HS256':
                return None
            expected = hmac.new(
                secret.encode(), ('%s.%s' % (head_b64, body_b64)).encode(),
                hashlib.sha256).digest()
            if not hmac.compare_digest(expected, _b64d(sig_b64)):
                return None
            payload = json.loads(_b64d(body_b64))
            if payload.get('exp') and payload['exp'] < time.time():
                return None
            return payload
        except Exception:  # noqa: BLE001
            return None

    def _authenticate_user(self):
        icp = request.env['ir.config_parameter'].sudo()

        # Optional static api-key check.
        expected_key = icp.get_param('pos_customer_display.api_key')
        if expected_key and not hmac.compare_digest(
                self._header('api-key'), expected_key):
            return False

        # ``db`` header must match the database serving this request.
        db = self._header('db')
        if db and request.db and db != request.db:
            return False

        bearer = self._bearer()
        login = self._header('login')
        password = request.httprequest.headers.get('password')

        # 1) login + password headers (existing FE contract)
        if login and password:
            user = request.env['res.users'].sudo().search(
                [('login', '=', login)], limit=1)
            if not user:
                return False
            try:
                user.with_user(user)._check_credentials(
                    {'type': 'password', 'password': password},
                    {'interactive': False})
            except AccessDenied:
                return False
            secret = icp.get_param('pos_customer_display.jwt_secret')
            if secret:
                payload = self._verify_jwt(bearer, secret)
                if not payload or payload.get('sub') != user.id:
                    return False
            request.update_env(user=user.id)
            return request.env.user

        # 2) Odoo API key as Bearer
        if bearer:
            try:
                uid = request.env['res.users.apikeys'].sudo()._check_credentials(
                    scope='rpc', key=bearer)
            except Exception:  # noqa: BLE001
                uid = False
            if not uid:
                return False
            request.update_env(user=uid)
            return request.env.user

        # 3) session cookie
        user = request.env.user
        return user if user and not user._is_public() else False

    def _base_url(self):
        base = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return (base or request.httprequest.host_url).rstrip('/')

    # -------------------------------------------------------------- endpoints
    @http.route(
        '/api/pos/customer-display/banners/<int:config_id>',
        type='http', auth='public', methods=['GET'], csrf=False)
    def get_banners(self, config_id, **params):
        user = self._authenticate_user()
        if not user:
            return self._error(401, 'Authentication required.')
        if not user.has_group('point_of_sale.group_pos_user'):
            return self._error(403, 'POS access required.')

        try:
            config = request.env['pos.config'].browse(config_id).exists()
            config.check_access('read')
        except Exception:  # noqa: BLE001  (AccessError)
            return self._error(403, 'No access to this POS.')
        if not config:
            return self._error(404, 'POS config not found.')

        banners = request.env['pos.customer.display.banner']._get_active_banners(config)
        base_url = self._base_url()

        data = []
        for banner in banners:
            unique = fields.Datetime.to_string(banner.write_date) if banner.write_date else ''
            data.append({
                'id': banner.id,
                'name': banner.name,
                'sequence': banner.sequence,
                'duration': banner.duration,
                'image_url': '%s/api/pos/customer-display/banners/%s/image?unique=%s' % (
                    base_url, banner.id, unique.replace(' ', 'T')),
                'date_start': fields.Datetime.to_string(banner.date_start) or None,
                'date_end': fields.Datetime.to_string(banner.date_end) or None,
            })

        return self._json({
            'pos_config_id': config.id,
            'pos_config_name': config.name,
            'count': len(data),
            'banners': data,
        })

    @http.route(
        '/api/pos/customer-display/banners/<int:banner_id>/image',
        type='http', auth='public', methods=['GET'], csrf=False)
    def get_banner_image(self, banner_id, **params):
        user = self._authenticate_user()
        if not user:
            return self._error(401, 'Authentication required.')
        if not user.has_group('point_of_sale.group_pos_user'):
            return self._error(403, 'POS access required.')

        banner = request.env['pos.customer.display.banner'].browse(banner_id).exists()
        if not banner or not banner.active or not banner.image:
            return request.not_found()
        stream = request.env['ir.binary']._get_image_stream_from(banner, 'image')
        return stream.get_response(max_age=3600)