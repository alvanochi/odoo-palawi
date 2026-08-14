# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from .utils import (
    require_api_key_plw, _cors_headers, _json_err, _json_result,
    _parse_int, _parse_csv, _api_timezone,
)
from ..repositories.company_repository import CompanyRepository
from ..repositories.pos_config_repository import PosConfigRepository, SESSION_STATE_IN_PROGRESS
from ..domain.use_cases.get_user_companies import GetUserCompaniesUseCase
from ..domain.use_cases.get_pos_configs import GetPosConfigsUseCase
from ..domain.use_cases.get_pos_sessions import GetPosSessionsUseCase, GetActivePosSessionUseCase


class PosContextController(http.Controller):
    """Company -> POS config -> POS session, the context a client resolves
    before it may create an order."""

    @http.route("/api/pos/companies", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_companies(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        user_id, error = _parse_int(kw.get("user_id"), "user_id")
        if error:
            return _json_err(error, 400)

        use_case = GetUserCompaniesUseCase(CompanyRepository(request.env))
        return _json_result(use_case.execute(user_id))

    @http.route("/api/pos/configs", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_pos_configs(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        company_id, error = _parse_int(kw.get("company_id"), "company_id")
        if error:
            return _json_err(error, 400)

        include_inactive = str(kw.get("active", "")).lower() == "all"

        use_case = GetPosConfigsUseCase(PosConfigRepository(request.env))
        return _json_result(use_case.execute(company_id, include_inactive))

    @http.route("/api/pos/sessions", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_pos_sessions(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(kw.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        limit, error = _parse_int(kw.get("limit"), "limit", required=False, default=20)
        if error:
            return _json_err(error, 400)

        # Default to sessions in progress; pass state=all for the full history.
        states = _parse_csv(kw.get("state") or SESSION_STATE_IN_PROGRESS)

        use_case = GetPosSessionsUseCase(PosConfigRepository(request.env))
        return _json_result(use_case.execute(
            pos_config_id=pos_config_id,
            states=states,
            date_str=kw.get("date"),
            limit=limit,
            tz_name=_api_timezone(),
        ))

    @http.route("/api/pos/sessions/active", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_active_pos_session(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(kw.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        require_today = str(kw.get("require_today", "")).lower() in ("1", "true", "yes")

        use_case = GetActivePosSessionUseCase(PosConfigRepository(request.env))
        return _json_result(use_case.execute(
            pos_config_id=pos_config_id,
            require_today=require_today,
            tz_name=_api_timezone(),
        ))
