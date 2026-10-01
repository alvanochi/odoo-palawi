import logging

from odoo import http
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

MANAGER_GROUP = "pos_payment_gateway.group_pos_payment_gateway_manager"


def _error(status, code, message):
    return request.make_json_response(
        {"success": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _forbidden():
    return _error(403, "FORBIDDEN", "You are not allowed to access this credential")


class PosPaymentGatewayController(http.Controller):

    def _authenticate_api_key(self):
        """Validasi header 'Authorization: Bearer <odoo_api_key>'. Return uid atau None."""
        header = request.httprequest.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            return None
        key = header[7:].strip()
        if not key:
            return None
        try:
            uid = request.env["res.users.apikeys"].sudo()._check_credentials(
                scope="rpc", key=key
            )
        except AccessDenied:
            return None
        return uid or None

    @http.route(
        "/api/payment-gateway/credential/<int:pos_config_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def get_credential(self, pos_config_id, gateway=None, **kwargs):
        uid = self._authenticate_api_key()
        if not uid:
            return _error(401, "UNAUTHORIZED", "Invalid or missing API key")

        request.update_env(user=uid)
        env = request.env
        if not env.user.has_group(MANAGER_GROUP):
            return _forbidden()

        # env user (bukan sudo) supaya record rule multi-company berlaku.
        pos_config = env["pos.config"].search([("id", "=", pos_config_id)], limit=1)
        if not pos_config:
            if env["pos.config"].sudo().search_count([("id", "=", pos_config_id)]):
                return _forbidden()
            return _error(
                404, "POS_CONFIG_NOT_FOUND", f"POS config {pos_config_id} not found"
            )

        Cred = env["pos.payment.gateway.credential"]
        try:
            if gateway:
                gw = env["pos.payment.gateway"].search([("code", "=", gateway)], limit=1)
                if not gw:
                    return _error(
                        404, "GATEWAY_NOT_FOUND", f"Payment gateway '{gateway}' not found"
                    )
                cred = Cred.search(
                    [("pos_config_id", "=", pos_config.id), ("gateway_id", "=", gw.id)],
                    limit=1,
                )
                if not cred:
                    return _error(
                        404,
                        "CREDENTIAL_NOT_FOUND",
                        f"No active '{gateway}' credential for pos_config_id {pos_config_id}",
                    )
                data = cred._to_api_dict()
            else:
                creds = Cred.search([("pos_config_id", "=", pos_config.id)])
                data = [c._to_api_dict() for c in creds]
        except AccessError:
            return _forbidden()

        _logger.info(
            "Payment gateway credential (pos.config=%s, gateway=%s) fetched by %s",
            pos_config_id,
            gateway or "*",
            env.user.login,
        )
        return request.make_json_response({"success": True, "data": data})
