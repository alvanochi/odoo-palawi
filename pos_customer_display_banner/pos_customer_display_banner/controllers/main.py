# -*- coding: utf-8 -*-
import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosCustomerDisplayBannerController(http.Controller):
    """Customer display banner API for POS.

    Auth: either an Odoo session (cookie) or an Odoo API key sent as
    ``Authorization: Bearer <api_key>``. The user must be a POS user.
    """

    # ---------------------------------------------------------------- helpers
    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _error(self, status, message):
        return self._json({'error': message}, status=status)

    def _authenticate_user(self):
        header = request.httprequest.headers.get('Authorization', '')
        if header.lower().startswith('bearer '):
            key = header[7:].strip()
            try:
                uid = request.env['res.users.apikeys'].sudo()._check_credentials(
                    scope='rpc', key=key)
            except Exception:  # noqa: BLE001
                uid = False
            if not uid:
                return False
            request.update_env(user=uid)
            return request.env.user
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
