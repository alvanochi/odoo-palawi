# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from .utils import require_jwt_plw, _cors_headers
from ..repositories.company_repository import CompanyRepository
from ..domain.use_cases.get_company_pos_config import GetCompanyPosConfigUseCase

class CompanyController(http.Controller):

    @http.route('/api/company/pos_config', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def get_company_pos_config(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())
            
        user = request.env.user
        company_repo = CompanyRepository(request.env)
        
        use_case = GetCompanyPosConfigUseCase(company_repo)
        result = use_case.execute(user.id, user.login)

        return request.make_json_response(result, headers=_cors_headers())
