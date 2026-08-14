# -*- coding: utf-8 -*-
"""Translate a loyalty.reward into a concrete money amount for a given cart.

Odoo's POS loyalty engine lives in JavaScript, so there is no server-side API
that turns a reward into order lines. These helpers reproduce the parts of that
engine the REST clients need, and are shared by the promo-matching endpoint and
by checkout so both always agree on the amount.
"""


def _discount_base(reward, cart_data):
    """Amount the discount percentage applies to, per discount_applicability."""
    applicability = reward.discount_applicability or 'order'

    if applicability == 'order':
        return sum(item['subtotal'] for item in cart_data)

    if applicability == 'cheapest':
        sellable = [item for item in cart_data if item['price'] > 0]
        if not sellable:
            return 0.0
        # Odoo discounts a single unit of the cheapest product
        return min(item['price'] for item in sellable)

    if applicability == 'specific':
        eligible_ids = reward.all_discount_product_ids.ids
        return sum(
            item['subtotal'] for item in cart_data
            if item['product'].id in eligible_ids
        )

    return 0.0


def compute_discount_amount(reward, cart_data, points=0.0):
    """Positive money amount this discount reward is worth on this cart."""
    if reward.reward_type != 'discount':
        return 0.0

    mode = reward.discount_mode or 'percent'

    if mode == 'percent':
        amount = _discount_base(reward, cart_data) * (reward.discount or 0.0) / 100.0
    elif mode == 'per_order':
        amount = reward.discount or 0.0
    elif mode == 'per_point':
        amount = (reward.discount or 0.0) * (points or 0.0)
    else:
        amount = 0.0

    # A discount can never exceed what is actually in the cart
    order_total = sum(item['subtotal'] for item in cart_data)
    amount = min(amount, order_total)

    if reward.discount_max_amount:
        amount = min(amount, reward.discount_max_amount)

    return max(amount, 0.0)


def compute_free_product_qty(reward, claim_count=1):
    """How many free units a 'product' reward hands out."""
    if reward.reward_type != 'product':
        return 0.0
    return (reward.reward_product_qty or 0.0) * max(claim_count, 1)


def _unit_price(product, qty, price_resolver):
    if price_resolver:
        return price_resolver(product, qty)
    return product.lst_price or product.list_price


def describe_reward(reward, cart_data, claim_count=1, coupon_id=None, points=0.0,
                    price_resolver=None):
    """A claimable reward, shaped so the client can post it back to checkout."""
    data = {
        'reward_id': reward.id,
        'program_id': reward.program_id.id,
        'program_name': reward.program_id.name,
        'program_type': reward.program_id.program_type,
        'reward_type': reward.reward_type,
        'description': reward.description or reward.display_name or '',
        'coupon_id': coupon_id,
        'claim_count': claim_count,
        'required_points': reward.required_points or 0.0,
    }

    if reward.reward_type == 'discount':
        data['estimated_discount'] = compute_discount_amount(reward, cart_data, points)
        data['discount_mode'] = reward.discount_mode or ''
        data['discount_applicability'] = reward.discount_applicability or ''
    else:
        qty = compute_free_product_qty(reward, claim_count)
        data['free_product_qty'] = qty
        # Prices go through the same resolver as the cart, so the value shown
        # here matches what checkout will actually deduct.
        data['reward_product_ids'] = [
            {
                'id': product.id,
                'name': product.display_name,
                'price': _unit_price(product, qty or 1, price_resolver),
            }
            for product in reward.reward_product_ids
        ]
        # Value handed out, useful for showing "you save X" in the UI
        first = reward.reward_product_ids[:1]
        unit_price = _unit_price(first, qty or 1, price_resolver) if first else 0.0
        data['estimated_discount'] = unit_price * qty

    return data
