# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request
from .utils import _cors_headers, require_jwt_plw
from ..repositories.table_repository import TableRepository
from ..domain.use_cases.get_table_layout import GetTableLayoutUseCase
from ..domain.use_cases.manage_floor import CreateFloorUseCase, UpdateFloorUseCase, DeleteFloorUseCase
from ..domain.use_cases.manage_table import CreateTableUseCase, UpdateTableUseCase, DeleteTableUseCase

class TableLayoutController(http.Controller):

    @http.route('/api/pos/table_layout', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def get_table_layout(self, **kwargs):
        # Fetch pos_config_id from query params
        pos_config_id_str = request.params.get('pos_config_id')
        if not pos_config_id_str:
            return request.make_json_response(
                {"error": "pos_config_id query parameter is required"},
                status=400,
                headers=_cors_headers()
            )
        try:
            pos_config_id = int(pos_config_id_str)
        except ValueError:
            return request.make_json_response(
                {"error": "pos_config_id must be an integer"},
                status=400,
                headers=_cors_headers()
            )

        env = request.env
        table_repo = TableRepository(env)
        use_case = GetTableLayoutUseCase(table_repo)
        result = use_case.execute(pos_config_id)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/floors', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def create_floor(self, **kwargs):
        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        pos_config_id = body.get('pos_config_id')
        name = body.get('name')
        floor_type = body.get('floor_type', 'indoor')
        background_color = body.get('background_color')

        env = request.env
        table_repo = TableRepository(env)
        use_case = CreateFloorUseCase(table_repo)
        result = use_case.execute(pos_config_id, name, floor_type, background_color)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/floors/<int:floor_id>', type='http', auth='public', methods=['PUT', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def update_floor(self, floor_id, **kwargs):
        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        env = request.env
        table_repo = TableRepository(env)
        use_case = UpdateFloorUseCase(table_repo)
        result = use_case.execute(floor_id, body)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/floors/<int:floor_id>', type='http', auth='public', methods=['DELETE', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def delete_floor(self, floor_id, **kwargs):
        env = request.env
        table_repo = TableRepository(env)
        use_case = DeleteFloorUseCase(table_repo)
        result = use_case.execute(floor_id)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/tables', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def create_table(self, **kwargs):
        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        floor_id = body.get('floor_id')

        env = request.env
        table_repo = TableRepository(env)
        use_case = CreateTableUseCase(table_repo)
        result = use_case.execute(floor_id, body)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/tables/<int:table_id>', type='http', auth='public', methods=['PUT', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def update_table(self, table_id, **kwargs):
        try:
            body = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            body = {}

        env = request.env
        table_repo = TableRepository(env)
        use_case = UpdateTableUseCase(table_repo)
        result = use_case.execute(table_id, body)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())

    @http.route('/api/pos/table_layout/tables/<int:table_id>', type='http', auth='public', methods=['DELETE', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def delete_table(self, table_id, **kwargs):
        env = request.env
        table_repo = TableRepository(env)
        use_case = DeleteTableUseCase(table_repo)
        result = use_case.execute(table_id)

        if not result.get("success"):
            return request.make_json_response(
                {"error": result.get("error")},
                status=result.get("status", 400),
                headers=_cors_headers()
            )

        return request.make_json_response(result, headers=_cors_headers())
