# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

from ..services.promotion_matcher import (
    build_cart_data, compute_claim_count, match_rule, serialize_program,
)
from ..services.reward_calculator import describe_reward


class MatchPosPromotionsUseCase:
    """Evaluate a cart against a POS's promo programs.

    Returns both the matched programs (for display) and claimable_rewards,
    which is the payload the client posts back to /api/pos/checkout.
    """

    def __init__(self, product_repo, promotion_repo, pricelist_repo, pos_config_repo):
        self.product_repo = product_repo
        self.promotion_repo = promotion_repo
        self.pricelist_repo = pricelist_repo
        self.pos_config_repo = pos_config_repo

    def execute(self, pos_config_id, cart_items, pricelist_id=None,
                partner_id=None, coupon_codes=None):
        if not isinstance(cart_items, list):
            return {"success": False, "error": "'cart' must be a list of items", "status": 400}

        try:
            config = self.pos_config_repo.resolve_config(pos_config_id)
            company = config.company_id

            product_ids = []
            for item in cart_items:
                pid = item.get('product_id')
                if not pid:
                    continue
                try:
                    product_ids.append(int(pid))
                except (TypeError, ValueError):
                    return {"success": False, "error": "product_id must be integers", "status": 400}

            product_map = self.product_repo.get_products_by_ids_and_company(product_ids, company)

            partner = self.pos_config_repo.find_partner(partner_id)

            # Baseline prices come from the pricelist when one is given, so the
            # promo thresholds are evaluated against the price actually charged.
            price_resolver = None
            if pricelist_id:
                pricelist = self.pricelist_repo.resolve_pricelist(pricelist_id, config)

                def price_resolver(product, qty, _pl=pricelist, _partner=partner):
                    return _pl._get_product_price(product, qty, _partner or False)

            # Thresholds and discounts run on the tax-inclusive amount, matching
            # what checkout charges and what the POS UI shows. price_resolver
            # stays tax-exclusive on purpose: checkout prices reward products
            # that way too, so both endpoints agree on a free product's value.
            fiscal_position = config.default_fiscal_position_id

            def subtotal_resolver(product, qty, price, _company=company,
                                  _fp=fiscal_position, _partner=partner):
                taxes = product.taxes_id.filtered_domain(
                    product.env['account.tax']._check_company_domain(_company))
                if not taxes:
                    return qty * price
                mapped_taxes = _fp.map_tax(taxes) if _fp else taxes
                return mapped_taxes.compute_all(
                    price, _company.currency_id, qty,
                    product=product, partner=_partner or False,
                )['total_included']

            cart_data = build_cart_data(cart_items, product_map, price_resolver,
                                        subtotal_resolver)

            # Validate any attached coupon codes first: a code-triggered program
            # only participates when its code was actually supplied.
            valid_coupons = {}
            invalid_codes = []
            for code in (coupon_codes or []):
                result = self.promotion_repo.validate_coupon_code(
                    pos_config_id, code, partner_id, pricelist_id)
                if result.get('valid'):
                    valid_coupons[result['program_id']] = result
                else:
                    invalid_codes.append({'code': code, 'message': result.get('message')})

            programs = self.promotion_repo.get_programs_for_pos_config(pos_config_id)

            matched_programs = []
            claimable_rewards = []
            for program in programs:
                coupon = valid_coupons.get(program.id)

                # Programs that need a code stay out until that code is supplied
                if program.trigger == 'with_code' and not coupon:
                    continue

                matched_rules = []
                claim_count = 0
                for rule in program.rule_ids:
                    rule_matches = match_rule(rule, cart_data)
                    matched_rules.extend(rule_matches)
                    for match in rule_matches:
                        claim_count = max(claim_count, compute_claim_count(rule, match['matched_qty']))

                if not matched_rules and program.rule_ids and not coupon:
                    continue

                matched_programs.append(serialize_program(program, matched_rules))

                points = coupon['points'] if coupon else 0.0
                coupon_id = coupon['coupon_id'] if coupon else None
                for reward in program.reward_ids:
                    if coupon and reward.required_points > points:
                        continue
                    # claim_count multiplies free products only. An order-level
                    # discount is claimed once no matter how many units qualify.
                    reward_claims = (claim_count or 1) if reward.reward_type == 'product' else 1
                    claimable_rewards.append(describe_reward(
                        reward, cart_data,
                        claim_count=reward_claims,
                        coupon_id=coupon_id,
                        points=points,
                        price_resolver=price_resolver,
                    ))

            return {
                "success": True,
                "data": {
                    "matched_programs": matched_programs,
                    "claimable_rewards": claimable_rewards,
                    "invalid_codes": invalid_codes,
                    "cart_subtotal": sum(item['subtotal'] for item in cart_data),
                },
            }
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
