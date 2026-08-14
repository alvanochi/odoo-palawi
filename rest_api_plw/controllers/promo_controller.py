# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from .utils import (
    require_api_key_plw, _cors_headers, _json_err, _json_result,
    _parse_int, _parse_csv, _parse_json_body,
)
from ..repositories.product_repository import ProductRepository
from ..repositories.promotion_repository import PromotionRepository
from ..repositories.pricelist_repository import PricelistRepository
from ..repositories.pos_config_repository import PosConfigRepository
from ..domain.use_cases.get_active_promotions import GetActivePromotionsUseCase
from ..domain.use_cases.match_pos_promotions import MatchPosPromotionsUseCase
from ..domain.use_cases.validate_coupon import ValidateCouponUseCase
from ..domain.use_cases.get_pricelists import GetPricelistsUseCase, GetPricelistPricesUseCase


class PromoController(http.Controller):
    """Promo, voucher and pricelist endpoints for the web and mobile apps."""

    @http.route("/api/pos/promotions", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_promotions(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(kw.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        program_types = _parse_csv(kw.get("program_type"))

        use_case = GetActivePromotionsUseCase(PromotionRepository(request.env))
        return _json_result(use_case.execute(pos_config_id, program_types))

    @http.route("/api/pos/promotions/match", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def match_promotions(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        body, error = _parse_json_body()
        if error:
            return _json_err(error, 400)

        pos_config_id, error = _parse_int(body.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        pricelist_id, error = _parse_int(body.get("pricelist_id"), "pricelist_id", required=False)
        if error:
            return _json_err(error, 400)

        partner_id, error = _parse_int(body.get("partner_id"), "partner_id", required=False)
        if error:
            return _json_err(error, 400)

        coupon_codes = body.get("coupon_codes") or []
        if body.get("coupon_code"):
            coupon_codes = list(coupon_codes) + [body.get("coupon_code")]

        env = request.env
        use_case = MatchPosPromotionsUseCase(
            ProductRepository(env),
            PromotionRepository(env),
            PricelistRepository(env),
            PosConfigRepository(env),
        )
        return _json_result(use_case.execute(
            pos_config_id=pos_config_id,
            cart_items=body.get("cart") or body.get("products") or [],
            pricelist_id=pricelist_id,
            partner_id=partner_id,
            coupon_codes=coupon_codes,
        ))

    @http.route("/api/pos/coupons/validate", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def validate_coupon(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        body, error = _parse_json_body()
        if error:
            return _json_err(error, 400)

        pos_config_id, error = _parse_int(body.get("pos_config_id"), "pos_config_id")
        if error:
            return _json_err(error, 400)

        partner_id, error = _parse_int(body.get("partner_id"), "partner_id", required=False)
        if error:
            return _json_err(error, 400)

        pricelist_id, error = _parse_int(body.get("pricelist_id"), "pricelist_id", required=False)
        if error:
            return _json_err(error, 400)

        use_case = ValidateCouponUseCase(PromotionRepository(request.env))
        return _json_result(use_case.execute(
            pos_config_id=pos_config_id,
            code=body.get("code") or body.get("coupon_code"),
            partner_id=partner_id,
            pricelist_id=pricelist_id,
        ))

    @http.route("/api/pos/pricelists", type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_pricelists(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        pos_config_id, error = _parse_int(kw.get("pos_config_id"), "pos_config_id", required=False)
        if error:
            return _json_err(error, 400)

        company_id, error = _parse_int(kw.get("company_id"), "company_id", required=False)
        if error:
            return _json_err(error, 400)

        use_case = GetPricelistsUseCase(PricelistRepository(request.env))
        return _json_result(use_case.execute(pos_config_id, company_id))

    @http.route("/api/pos/pricelists/prices", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    @require_api_key_plw
    def get_pricelist_prices(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return http.Response(status=204, headers=_cors_headers())

        body, error = _parse_json_body()
        if error:
            return _json_err(error, 400)

        pricelist_id, error = _parse_int(body.get("pricelist_id"), "pricelist_id")
        if error:
            return _json_err(error, 400)

        partner_id, error = _parse_int(body.get("partner_id"), "partner_id", required=False)
        if error:
            return _json_err(error, 400)

        pos_config_id, error = _parse_int(body.get("pos_config_id"), "pos_config_id", required=False)
        if error:
            return _json_err(error, 400)

        use_case = GetPricelistPricesUseCase(PricelistRepository(request.env))
        return _json_result(use_case.execute(
            pricelist_id=pricelist_id,
            items=body.get("items") or [],
            partner_id=partner_id,
            pos_config_id=pos_config_id,
        ))
