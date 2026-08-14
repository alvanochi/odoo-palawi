# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request
from .utils import require_jwt_plw, _cors_headers
from ..repositories.product_repository import ProductRepository
from ..repositories.promotion_repository import PromotionRepository
from ..repositories.company_repository import CompanyRepository
from ..domain.use_cases.get_matched_promotions import GetMatchedPromotionsUseCase

class PromotionsController(http.Controller):

    @http.route('/api/loyalty/promotions', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    @require_jwt_plw
    def get_matched_promotions(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return http.Response(status=204, headers=_cors_headers())

        try:
            data = json.loads((request.httprequest.get_data() or b'{}').decode('utf-8'))
        except Exception:
            return request.make_json_response({'error': 'Invalid request JSON payload'}, status=400, headers=_cors_headers())

        cart_items = data.get('cart') or data.get('products') or []
        req_company_id = data.get('company_id') or data.get('company') or 0

        # Wire up repositories & use case
        env = request.env
        use_case = GetMatchedPromotionsUseCase(
            ProductRepository(env),
            PromotionRepository(env),
            CompanyRepository(env),
        )

        try:
            result = use_case.execute(cart_items, env.user.id, req_company_id)
        except Exception as e:
            return request.make_json_response(
                {'error': str(e)}, status=500, headers=_cors_headers()
            )

        if not result.get("success"):
            return request.make_json_response(
                {'error': result.get("error")}, 
                status=result.get("status", 400), 
                headers=_cors_headers()
            )

        return request.make_json_response({
            'matched_programs': result.get("matched_programs")
        }, headers=_cors_headers())
