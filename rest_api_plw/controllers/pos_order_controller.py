# -*- coding: utf-8 -*-
from urllib.parse import urlsplit, urlunsplit

from odoo import http
from odoo.http import request
from odoo.addons.bus.websocket import WebsocketConnectionHandler

from .utils import (
    require_api_key_plw, _cors_headers, _json_err, _json_result,
    _parse_int, _parse_csv, _parse_json_body, _api_timezone,
)
from ..repositories.pos_order_repository import (
    PosOrderRepository, KITCHEN_STATES, KITCHEN_PENDING_STATES,
)
from ..repositories.pos_config_repository import PosConfigRepository
from ..domain.use_cases.get_pos_orders import GetPosOrdersUseCase, GetPosOrderDetailUseCase
from ..domain.use_cases.update_line_kitchen_state import UpdateLineKitchenStateUseCase


class PosOrderController(http.Controller):
    """Read the kitchen queue and move each dish along the cooking states."""

    @http.route("/api/v2/pos/orders", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_orders(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        session_id, error = _parse_int(
            kw.get("pos_session_id") or kw.get("session_id"), "pos_session_id", required=False)
        if error:
            return _json_err(error, 400)

        pos_config_id, error = _parse_int(kw.get("pos_config_id"), "pos_config_id", required=False)
        if error:
            return _json_err(error, 400)

        table_id, error = _parse_int(kw.get("table_id"), "table_id", required=False)
        if error:
            return _json_err(error, 400)

        limit, error = _parse_int(kw.get("limit"), "limit", required=False, default=100)
        if error:
            return _json_err(error, 400)

        offset, error = _parse_int(kw.get("offset"), "offset", required=False, default=0)
        if error:
            return _json_err(error, 400)

        # No filter at all -> the kitchen queue: paid orders that still have
        # dishes to cook. Both defaults apply together so a bare call is
        # immediately useful to a kitchen display.
        #
        # The moment the caller names either filter they are asking a different
        # question -- usually history -- so the other default is dropped rather
        # than silently narrowing the answer. A second, invisible filter is how
        # 'state=all' would quietly keep hiding served orders.
        raw_state = kw.get("state")
        raw_kitchen_state = kw.get("kitchen_state")
        explicit = bool(raw_state or raw_kitchen_state)

        states = _parse_csv(raw_state or (None if explicit else ",".join(KITCHEN_STATES)))
        kitchen_states = _parse_csv(
            raw_kitchen_state or (None if explicit else ",".join(KITCHEN_PENDING_STATES)))

        use_case = GetPosOrdersUseCase(PosOrderRepository(request.env))
        return _json_result(use_case.execute(
            session_id=session_id,
            pos_config_id=pos_config_id,
            states=states,
            table_id=table_id,
            limit=limit,
            offset=offset,
            kitchen_states=kitchen_states,
        ))

    @http.route("/api/v2/pos/kitchen/orders", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_active_kitchen_orders(self, **kw):
        """Resolve session aktif dan antreannya dalam satu request.

        Frontend KDS sebaiknya menyimpan pos_config_id, bukan session_id.
        Session berubah ketika kasir menutup/membuka POS; endpoint ini selalu
        memilih session dengan aturan yang sama seperti checkout.
        """
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(
            kw.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        config = request.env['pos.config'].sudo().browse(pos_config_id)
        if not config.exists():
            return _json_err(
                "POS Config ID %s does not exist" % pos_config_id, 404)

        limit, error = _parse_int(
            kw.get("limit"), "limit", required=False, default=100)
        if error:
            return _json_err(error, 400)

        offset, error = _parse_int(
            kw.get("offset"), "offset", required=False, default=0)
        if error:
            return _json_err(error, 400)

        table_id, error = _parse_int(
            kw.get("table_id"), "table_id", required=False)
        if error:
            return _json_err(error, 400)

        require_today = str(kw.get("require_today", "")).lower() in (
            "1", "true", "yes")
        session_context = PosConfigRepository(request.env).find_active_session(
            pos_config_id=pos_config_id,
            require_today=require_today,
            tz_name=_api_timezone(),
        )

        session_data = session_context.get("session")
        if not session_context.get("can_create_order") or not session_data:
            return _json_result({
                "success": True,
                "data": {
                    "pos_config_id": pos_config_id,
                    "session": None,
                    "orders": [],
                    "reason": session_context.get("reason"),
                    "open_session_count": session_context.get("open_session_count", 0),
                    "stale_session_ids": session_context.get("stale_session_ids", []),
                    "filters": {
                        "state": KITCHEN_STATES,
                        "kitchen_state": KITCHEN_PENDING_STATES,
                    },
                },
            })

        states = _parse_csv(kw.get("state") or ",".join(KITCHEN_STATES))
        kitchen_states = _parse_csv(
            kw.get("kitchen_state") or ",".join(KITCHEN_PENDING_STATES))
        orders_result = GetPosOrdersUseCase(
            PosOrderRepository(request.env)).execute(
                session_id=session_data["id"],
                states=states,
                table_id=table_id,
                limit=limit,
                offset=offset,
                kitchen_states=kitchen_states,
            )
        if not orders_result.get("success"):
            return _json_result(orders_result)

        return _json_result({
            "success": True,
            "data": {
                "pos_config_id": pos_config_id,
                "session": session_data,
                "orders": orders_result["data"],
                "reason": None,
                "open_session_count": session_context.get("open_session_count", 1),
                "stale_session_ids": session_context.get("stale_session_ids", []),
                "filters": {
                    "state": states,
                    "kitchen_state": kitchen_states,
                },
            },
        })

    @http.route("/api/v2/pos/kitchen/realtime", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_kitchen_realtime_config(self, **kw):
        """Berikan capability channel dan versi WebSocket Odoo kepada KDS."""
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(
            kw.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        config = request.env['pos.config'].sudo().browse(pos_config_id)
        if not config.exists():
            return _json_err(
                "POS Config ID %s does not exist" % pos_config_id, 404)
        if not hasattr(config, '_get_kds_realtime_channel'):
            return _json_err(
                "Module 'pos_order_extra_states' version 18.0.2.2.0 or newer "
                "is required for KDS realtime", 503)

        parameters = request.env['ir.config_parameter'].sudo()
        base_url = (
            parameters.get_param('api_kds_websocket_base_url')
            or parameters.get_param('web.base.url')
            or request.httprequest.host_url.rstrip('/')
        )
        parts = urlsplit(base_url)
        ws_scheme = 'wss' if parts.scheme == 'https' else 'ws'
        websocket_url = urlunsplit((
            ws_scheme,
            parts.netloc,
            '%s/websocket' % parts.path.rstrip('/'),
            'version=%s' % WebsocketConnectionHandler._VERSION,
            '',
        ))

        return _json_result({
            "success": True,
            "data": {
                "pos_config_id": config.id,
                "websocket_url": websocket_url,
                "channel": config._get_kds_realtime_channel(),
                "notification_type": "pos_kds/update",
                "snapshot_url": (
                    "/api/v2/pos/kitchen/orders?pos_config_id=%s" % config.id
                ),
                "protocol": {
                    "subscribe_event": "subscribe",
                    "keepalive_seconds": 50,
                },
            },
        })

    @http.route("/api/v2/pos/orders/<int:order_id>", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_order_detail(self, order_id, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        use_case = GetPosOrderDetailUseCase(PosOrderRepository(request.env))
        return _json_result(use_case.execute(order_id))

    @http.route("/api/v2/pos/orders/<int:order_id>/lines/<int:line_id>/state",
                type="http", auth="none", methods=["PUT", "POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def update_line_kitchen_state(self, order_id, line_id, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        body, error = _parse_json_body()
        if error:
            return _json_err(error, 400)

        target_state = body.get("state") or body.get("action")
        source = body.get("source") or "staff"

        use_case = UpdateLineKitchenStateUseCase(PosOrderRepository(request.env))
        return _json_result(use_case.execute(order_id, line_id, target_state, source))
