import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosMobileFeatureFlags(http.Controller):
    """Feature flag API for the external Android POS app.

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

    # -------------------------------------------------------------- endpoints
    @http.route(
        ['/api/pos/feature-flags', '/api/pos/feature-flags/<int:config_id>'],
        type='http', auth='public', methods=['GET'], csrf=False)
    def feature_flags(self, config_id=None, **params):
        user = self._authenticate_user()
        if not user:
            return self._error(401, 'Authentication required.')
        if not user.has_group('point_of_sale.group_pos_user'):
            return self._error(403, 'POS access required.')

        detail = str(params.get('detail', '')).lower() in ('1', 'true', 'yes')
        config_id = config_id or params.get('config_id') or params.get('pos_config_id')
        Config = request.env['pos.config']

        if not config_id:
            configs = Config.search([])
            return self._json({'configs': [
                c._mobile_feature_flags_payload(detail=detail) for c in configs]})

        try:
            config = Config.browse(int(config_id)).exists()
            config.check_access('read')  # Odoo 18: raises if the user can't read it
        except (ValueError, TypeError):
            return self._error(400, 'Invalid config_id.')
        except Exception:  # noqa: BLE001  (AccessError)
            return self._error(403, 'No access to this POS.')
        if not config:
            return self._error(404, 'POS config not found.')

        return self._json(config._mobile_feature_flags_payload(detail=detail))
