# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from .utils import require_api_key_plw, _cors_headers
from ..repositories.product_repository import ProductRepository
from ..domain.use_cases.get_pos_products import GetPosProductsUseCase
from ..domain.use_cases.get_pos_categories import GetPosCategoriesUseCase

class ProductController(http.Controller):

    @http.route("/api/pos/products", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_products(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        repo = ProductRepository(request.env)
        use_case = GetPosProductsUseCase(repo)
        
        # Get base_url from Odoo System Parameters
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "http://localhost:8069")
        
        company_id = kw.get("company_id")
        config_pos_id = kw.get("config_pos_id")
        pos_categ_id = kw.get("pos_categ_id")
        search = kw.get("search")
        page = kw.get("page")
        limit = kw.get("limit")

        result = use_case.execute(
            company_id=company_id,
            config_pos_id=config_pos_id,
            pos_categ_id=pos_categ_id,
            search=search,
            page=page,
            limit=limit,
            base_url=base_url
        )

        if not result.get("success", False):
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route("/api/pos/categories", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_categories(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        repo = ProductRepository(request.env)
        use_case = GetPosCategoriesUseCase(repo)

        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "http://localhost:8069")
        
        company_id = kw.get("company_id")
        config_pos_id = kw.get("config_pos_id")

        result = use_case.execute(
            company_id=company_id,
            config_pos_id=config_pos_id,
            base_url=base_url
        )

        if not result.get("success", False):
            err_payload = {
                "success": False, 
                "message": result.get("error", "Error"), 
                "status": result.get("status", 400)
            }
            return request.make_json_response(err_payload, status=result.get("status", 400), headers=_cors_headers())

        return request.make_json_response(result, status=200, headers=_cors_headers())

    @http.route([
        "/api/pos/product/image/<int:template_id>",
        "/api/pos/product/image/<int:template_id>/<string:field>"
    ], type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    def get_product_image(self, template_id, field="image_128", **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,OPTIONS"),
            ])

        # Execute as superuser to bypass multi-company record rules
        env = request.env(user=1, su=True)
        tmpl = env["product.template"].browse(template_id)

        if not tmpl.exists() or not getattr(tmpl, field, False):
            return request.make_response(b"", headers=[
                ("Content-Type", "image/png"),
                ("Access-Control-Allow-Origin", "*"),
            ], status=404)

        import base64
        try:
            image_data = base64.b64decode(getattr(tmpl, field))
        except Exception:
            return request.make_response(b"", headers=[
                ("Access-Control-Allow-Origin", "*"),
            ], status=400)

        return request.make_response(image_data, headers=[
            ("Content-Type", "image/png"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "public, max-age=604800"),
        ])

