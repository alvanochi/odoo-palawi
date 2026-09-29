# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class ProductAddonsApi(http.Controller):
    """
    External API endpoint to retrieve add-on products for a given product variant.

    Response format per add-on:
        {
            "id":         <int>,
            "name":       <str>,
            "price":      <float>,
            "qty":        1,
            "categoryId": <int|null>,
            "imageUrl":   <str>,
            "imageRes":   <str>,
            "category":   <str|null>
        }
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _json_response(self, success, data=None, message=None, status=200):
        body = {"success": success}
        if message is not None:
            body["message"] = message
        if data is not None:
            body["data"] = data
        return Response(
            json.dumps(body),
            status=status,
            content_type="application/json",
        )

    def _auth_api_key(self):
        """Validate API key from request headers."""
        api_key = request.httprequest.headers.get("api-key")
        if not api_key:
            return False
        user = request.env["res.users"].sudo().search(
            [("api_key", "=", api_key)], limit=1
        )
        return bool(user)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route(
        "/api/product-addons/<int:product_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def get_product_addons(self, product_id, **kw):
        """Return the list of add-on products for *product_id*."""

        # 1) Auth
        if not self._auth_api_key():
            return self._json_response(
                False, message="Unauthorized: invalid or missing API key", status=401
            )

        # 2) Fetch product
        product = (
            request.env["product.product"]
            .sudo()
            .browse(product_id)
        )
        if not product.exists():
            return self._json_response(
                False, message="Product not found", status=404
            )

        # 3) Build add-on list
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        addons_data = []
        for addon in product.addon_product_ids:
            # Determine category info from pos_categ_ids (first one)
            categ = addon.pos_categ_ids[:1]
            category_id = categ.id if categ else None
            category_name = categ.display_name if categ else None

            addons_data.append({
                "id": addon.id,
                "name": addon.display_name or addon.name,
                "price": addon.lst_price,
                "qty": 1,
                "categoryId": category_id,
                "imageUrl": f"{base_url}/web/image/product.product/{addon.id}/image_1920" if addon.image_1920 else None,
                "imageRes": f"{base_url}/web/image/product.product/{addon.id}/image_128" if addon.image_128 else None,
                "category": category_name,
            })

        return self._json_response(True, data={
            "product_id": product.id,
            "product_name": product.display_name or product.name,
            "addons": addons_data,
            "count": len(addons_data),
        })

    @http.route(
        "/api/product-addons",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def get_all_products_with_addons(self, **kw):
        """Return all products that have at least one add-on defined."""

        # 1) Auth
        if not self._auth_api_key():
            return self._json_response(
                False, message="Unauthorized: invalid or missing API key", status=401
            )

        # 2) Fetch all products with add-ons
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        products = (
            request.env["product.product"]
            .sudo()
            .search([("addon_product_ids", "!=", False), ("available_in_pos", "=", True)])
        )

        result = []
        for product in products:
            addons_data = []
            for addon in product.addon_product_ids:
                categ = addon.pos_categ_ids[:1]
                category_id = categ.id if categ else None
                category_name = categ.display_name if categ else None

                addons_data.append({
                    "id": addon.id,
                    "name": addon.display_name or addon.name,
                    "price": addon.lst_price,
                    "qty": 1,
                    "categoryId": category_id,
                    "imageUrl": f"{base_url}/web/image/product.product/{addon.id}/image_1920" if addon.image_1920 else None,
                    "imageRes": f"{base_url}/web/image/product.product/{addon.id}/image_128" if addon.image_128 else None,
                    "category": category_name,
                })

            result.append({
                "product_id": product.id,
                "product_name": product.display_name or product.name,
                "addons": addons_data,
                "count": len(addons_data),
            })

        return self._json_response(True, data={
            "products": result,
            "total": len(result),
        })
