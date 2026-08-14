# -*- coding: utf-8 -*-
"""Pure rule-matching helpers shared by the JWT and api-key promotion endpoints.

Nothing here touches the ORM beyond reading fields off records that were
already fetched by a repository, so both use cases can reuse the same logic.
"""


def build_cart_data(cart_items, product_map, price_resolver=None, subtotal_resolver=None):
    """Normalise raw cart payload into [{product, qty, price, subtotal}].

    ``price_resolver(product, qty)`` lets the caller plug in a pricelist; when
    omitted the client price is used, falling back to the product list price.

    ``subtotal_resolver(product, qty, price)`` lets the caller run the tax
    engine so thresholds and discounts are evaluated on the amount the customer
    actually pays. Without it the subtotal is a plain qty * price, which differs
    from the charged amount whenever the product carries tax.

    Items with an unknown product or a non-positive qty are dropped.
    """
    cart_data = []
    for item in cart_items:
        pid = item.get('product_id')
        if not pid:
            continue
        try:
            qty = float(item.get('qty', 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        product = product_map.get(int(pid))
        if not product:
            continue

        price = item.get('price')
        if price in (None, "", False):
            if price_resolver:
                price = price_resolver(product, qty)
            else:
                price = product.list_price or 0.0
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = product.list_price or 0.0

        if subtotal_resolver:
            subtotal = subtotal_resolver(product, qty, price)
        else:
            subtotal = qty * price

        cart_data.append({
            'product': product,
            'qty': qty,
            'price': price,
            'subtotal': subtotal,
        })
    return cart_data


def rule_matches_product(rule, product):
    """Does this loyalty.rule apply to this product.product?

    Delegates to loyalty.rule._get_valid_product_domain() so the API always
    agrees with the POS: it covers product_ids, category child_of, product tags
    and the free-form product_domain, and an empty domain means "any product".
    """
    return bool(product.filtered_domain(rule._get_valid_product_domain()))


def match_rule(rule, cart_data):
    """Cart lines that satisfy this rule, with the qty/amount thresholds applied."""
    matches = []
    for cart_item in cart_data:
        product = cart_item['product']
        if not rule_matches_product(rule, product):
            continue
        if cart_item['qty'] < rule.minimum_qty:
            continue
        if cart_item['subtotal'] < rule.minimum_amount:
            continue
        matches.append({
            'rule_id': rule.id,
            'minimum_qty': rule.minimum_qty,
            'minimum_amount': rule.minimum_amount,
            'reward_point_amount': rule.reward_point_amount,
            'reward_point_mode': rule.reward_point_mode,
            'matched_product_id': product.id,
            'matched_qty': cart_item['qty'],
            'matched_subtotal': cart_item['subtotal'],
        })
    return matches


def compute_claim_count(rule, matched_qty):
    """How many times a Buy X Get Y reward may be claimed.

    Buying 5 items on a "buy 2" rule earns the reward twice, not five times.
    """
    minimum_qty = rule.minimum_qty or 1
    if minimum_qty <= 0:
        return 1
    return int(matched_qty // minimum_qty)


def serialize_rule(rule):
    return {
        'rule_id': rule.id,
        'mode': rule.mode,
        'code': rule.code or '',
        'minimum_qty': rule.minimum_qty,
        'minimum_amount': rule.minimum_amount,
        'reward_point_amount': rule.reward_point_amount,
        'reward_point_mode': rule.reward_point_mode,
        # No product restriction at all means the rule applies to any product
        'any_product': not rule._get_valid_product_domain(),
        'product_ids': rule.product_ids.ids,
        'product_category_id': rule.product_category_id.id or False,
        'product_tag_id': rule.product_tag_id.id or False,
    }


def serialize_reward(reward):
    """Note: Odoo 18 uses the m2m reward_product_ids; reward_product_id is only
    a convenience compute for the single-product case, so both are exposed."""
    return {
        'reward_id': reward.id,
        'reward_type': reward.reward_type or '',
        'description': reward.description or reward.display_name or '',
        'required_points': reward.required_points or 0.0,
        'discount': reward.discount or 0.0,
        'discount_mode': reward.discount_mode or '',
        'discount_applicability': reward.discount_applicability or '',
        'discount_max_amount': reward.discount_max_amount or 0.0,
        'reward_product_id': reward.reward_product_id.id if reward.reward_product_id else False,
        'reward_product_name': reward.reward_product_id.display_name if reward.reward_product_id else '',
        'reward_product_qty': reward.reward_product_qty or 0.0,
        'reward_product_ids': [
            {
                'id': product.id,
                'name': product.display_name,
                'price': product.lst_price or product.list_price,
            }
            for product in reward.reward_product_ids
        ],
    }


def serialize_program(program, matched_rules=None):
    data = {
        'program_id': program.id,
        'program_name': program.name,
        'program_type': program.program_type or '',
        'trigger': program.trigger or '',
        'applies_on': program.applies_on or '',
        'date_from': program.date_from.isoformat() if program.date_from else False,
        'date_to': program.date_to.isoformat() if program.date_to else False,
        'portal_point_name': program.portal_point_name or '',
        'pricelist_ids': program.pricelist_ids.ids,
        'rewards': [serialize_reward(reward) for reward in program.reward_ids],
    }
    if matched_rules is None:
        data['rules'] = [serialize_rule(rule) for rule in program.rule_ids]
    else:
        data['rules'] = matched_rules
    return data


def match_programs(programs, cart_data):
    """Programs whose rules are satisfied by the cart (or that have no rules)."""
    matched_programs = []
    for program in programs:
        matched_rules = []
        for rule in program.rule_ids:
            matched_rules.extend(match_rule(rule, cart_data))

        if matched_rules or not program.rule_ids:
            matched_programs.append(serialize_program(program, matched_rules))
    return matched_programs
