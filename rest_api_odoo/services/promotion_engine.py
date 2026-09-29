# -*- coding: utf-8 -*-
"""Mesin promo: mencocokkan keranjang ke program loyalty Odoo dan menghitung
nilainya dalam rupiah.

Mesin loyalty bawaan Odoo hidup di JavaScript POS, jadi tidak ada API server
yang bisa dipanggil untuk mengubah sebuah reward menjadi baris order. Berkas
ini menyediakan bagian yang dibutuhkan klien REST, dan sengaja bersandar pada
helper Odoo sendiri di mana pun tersedia -- `rule._get_valid_product_domain()`,
`reward.all_discount_product_ids`, `pos.config._get_program_ids()` -- supaya
hasilnya tidak pernah menyimpang dari yang dilakukan kasir POS.

Isinya fungsi murni: tidak ada state, tidak menyentuh request, dan setiap
record yang dipakai sudah diambil pemanggilnya. Ini yang membuat modul promo
bisa diuji tanpa menyalakan HTTP.
"""


# ---------------------------------------------------------------------------
# Keranjang
# ---------------------------------------------------------------------------

def resolve_products(env, product_ids, company):
    """{id yang diminta: product.product}.

    Klien mengirim id product.product ATAU id product.template (katalog
    memaparkan template), jadi keduanya diterima. Template diselesaikan ke
    varian default-nya. Id yang tidak ada dilewati.
    """
    if not product_ids:
        return {}

    company_id = company.id if hasattr(company, 'id') else company
    product_model = env["product.product"].sudo().with_company(company_id)
    template_model = env["product.template"].sudo().with_company(company_id)

    product_map = {}
    unresolved = []
    for product in product_model.browse(product_ids).exists():
        product_map[product.id] = product
    for pid in product_ids:
        if pid not in product_map:
            unresolved.append(pid)

    for template in template_model.browse(unresolved).exists():
        variant = template.product_variant_id
        if variant:
            product_map[template.id] = variant

    return product_map


def build_cart_data(cart_items, product_map, price_resolver=None, subtotal_resolver=None):
    """Normalkan payload keranjang menjadi [{product, qty, price, subtotal}].

    ``price_resolver(product, qty)`` memasang pricelist; tanpa itu harga dari
    klien yang dipakai, dan bila kosong jatuh ke list_price.

    ``subtotal_resolver(product, qty, price)`` menjalankan mesin pajak supaya
    ambang dan diskon dievaluasi pada jumlah yang benar-benar dibayar
    pelanggan. Tanpa itu subtotal hanyalah qty * price, yang berbeda dari
    jumlah tertagih setiap kali produknya kena pajak.

    Item dengan produk tak dikenal atau qty tidak positif dibuang.
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


# ---------------------------------------------------------------------------
# Pencocokan aturan
# ---------------------------------------------------------------------------

def rule_matches_product(rule, product):
    """Apakah loyalty.rule ini berlaku untuk product.product ini?

    Diserahkan ke loyalty.rule._get_valid_product_domain() supaya API selalu
    sepakat dengan POS: domain itu mencakup product_ids, kategori child_of,
    tag produk, dan product_domain bebas -- dan domain kosong berarti "produk
    apa pun".
    """
    return bool(product.filtered_domain(rule._get_valid_product_domain()))


def match_rule(rule, cart_data):
    """Baris keranjang yang memenuhi aturan ini, setelah ambang diterapkan."""
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
    """Berapa kali reward Buy X Get Y boleh diklaim.

    Membeli 5 item pada aturan "beli 2" memberi reward dua kali, bukan lima.
    """
    minimum_qty = rule.minimum_qty or 1
    if minimum_qty <= 0:
        return 1
    return int(matched_qty // minimum_qty)


# ---------------------------------------------------------------------------
# Nilai reward
# ---------------------------------------------------------------------------

def _discount_base(reward, cart_data):
    """Jumlah yang dikenai persentase diskon, sesuai discount_applicability."""
    applicability = reward.discount_applicability or 'order'

    if applicability == 'order':
        return sum(item['subtotal'] for item in cart_data)

    if applicability == 'cheapest':
        sellable = [item for item in cart_data if item['price'] > 0]
        if not sellable:
            return 0.0
        # Odoo mendiskon satu unit dari produk termurah
        return min(item['price'] for item in sellable)

    if applicability == 'specific':
        eligible_ids = reward.all_discount_product_ids.ids
        return sum(
            item['subtotal'] for item in cart_data
            if item['product'].id in eligible_ids
        )

    return 0.0


def compute_discount_amount(reward, cart_data, points=0.0):
    """Nilai rupiah positif dari reward diskon ini pada keranjang ini."""
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

    # Diskon tidak pernah boleh melebihi isi keranjang
    order_total = sum(item['subtotal'] for item in cart_data)
    amount = min(amount, order_total)

    if reward.discount_max_amount:
        amount = min(amount, reward.discount_max_amount)

    return max(amount, 0.0)


def compute_free_product_qty(reward, claim_count=1):
    """Berapa unit gratis yang diberikan reward bertipe 'product'."""
    if reward.reward_type != 'product':
        return 0.0
    return (reward.reward_product_qty or 0.0) * max(claim_count, 1)


def _unit_price(product, qty, price_resolver):
    if price_resolver:
        return price_resolver(product, qty)
    return product.lst_price or product.list_price


def describe_reward(reward, cart_data, claim_count=1, coupon_id=None, points=0.0,
                    price_resolver=None):
    """Satu reward yang bisa diklaim, siap dikirim balik klien saat membuat order."""
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
        # Produk teknis untuk BARIS reward-nya. Klien memakainya saat
        # POST /api/pos/order dengan price_unit negatif, persis seperti kasir.
        'discount_line_product_id': (
            reward.discount_line_product_id.id
            if reward.discount_line_product_id else False),
    }

    if reward.reward_type == 'discount':
        data['estimated_discount'] = compute_discount_amount(reward, cart_data, points)
        data['discount_mode'] = reward.discount_mode or ''
        data['discount_applicability'] = reward.discount_applicability or ''
    else:
        qty = compute_free_product_qty(reward, claim_count)
        data['free_product_qty'] = qty
        # Harga melewati resolver yang sama dengan keranjang, jadi nilai yang
        # ditampilkan sama dengan yang nanti dipotong saat order dibuat.
        data['reward_product_ids'] = [
            {
                'id': product.id,
                'name': product.display_name,
                'price': _unit_price(product, qty or 1, price_resolver),
            }
            for product in reward.reward_product_ids
        ]
        # Nilai yang diberikan, untuk menampilkan "Anda hemat X"
        first = reward.reward_product_ids[:1]
        unit_price = _unit_price(first, qty or 1, price_resolver) if first else 0.0
        data['estimated_discount'] = unit_price * qty

    return data


# ---------------------------------------------------------------------------
# Serialisasi
# ---------------------------------------------------------------------------

def serialize_rule(rule):
    return {
        'rule_id': rule.id,
        'mode': rule.mode,
        'code': rule.code or '',
        'minimum_qty': rule.minimum_qty,
        'minimum_amount': rule.minimum_amount,
        'reward_point_amount': rule.reward_point_amount,
        'reward_point_mode': rule.reward_point_mode,
        # Tanpa batasan produk sama sekali berarti aturannya berlaku untuk apa pun
        'any_product': not rule._get_valid_product_domain(),
        'product_ids': rule.product_ids.ids,
        'product_category_id': rule.product_category_id.id or False,
        'product_tag_id': rule.product_tag_id.id or False,
    }


def serialize_reward(reward):
    """Catatan: Odoo 18 memakai m2m reward_product_ids; reward_product_id hanya
    compute untuk kasus satu produk, jadi keduanya dipaparkan."""
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
        # Produk teknis yang dipakai POS Odoo untuk BARIS reward-nya, baik
        # untuk diskon maupun produk gratis. Klien yang mencatat promo lewat
        # /api/pos/order harus memakai produk ini pada baris reward, dengan
        # price_unit negatif -- persis seperti kasir POS.
        'discount_line_product_id': (
            reward.discount_line_product_id.id
            if reward.discount_line_product_id else False),
        'discount_line_product_name': (
            reward.discount_line_product_id.display_name
            if reward.discount_line_product_id else ''),
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
