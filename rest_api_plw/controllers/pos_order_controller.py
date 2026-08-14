# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from .utils import (
    require_api_key_plw, _cors_headers, _json_err, _json_result,
    _parse_int, _parse_csv, _parse_json_body,
)
from ..repositories.pos_order_repository import (
    PosOrderRepository, KITCHEN_STATES, KITCHEN_PENDING_STATES,
)
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
