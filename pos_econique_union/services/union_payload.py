# -*- coding: utf-8 -*-
"""Builds the POST /api/kuliner/transaction payload (Union Kuliner Econique).

This module deliberately does not import odoo: every input is a plain dict,
so the calculation rules can be tested without an Odoo server.

Formulas (from the table and example in the Econique documentation, see README):

    bruto            = sum(unit_price * qty) over all item lines
    discount_nominal = per-line percent discount + discount/reward lines
    discount         = discount_nominal / bruto * 100   (percent, max 100)
    service_fee      = (bruto - discount_nominal) * service_fee_percent / 100
    ppn              = order tax (rupiah)
    netto            = bruto - discount_nominal - service_fee - ppn
"""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value):
    return Decimal(str(value if value is not None else 0))


def quantize(value):
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money(value):
    """Amount as a 2-decimal string, per 'decimal 2 digit after (,)'."""
    return "%.2f" % quantize(value)


def build_items(lines):
    """-> (items, bruto, line_discount, reward_discount)

    lines: list of dicts with keys product_code, product_name, price_code,
    price_name, qty, unit_price, discount_percent, is_discount_line.
    Lines with is_discount_line=True (discount/reward, negative value) do not
    become items; their value is counted as an order discount.
    """
    items = []
    bruto = Decimal(0)
    line_discount = Decimal(0)
    reward_discount = Decimal(0)

    for line in lines:
        qty = to_decimal(line["qty"])
        unit = to_decimal(line["unit_price"])
        gross = unit * qty

        if line.get("is_discount_line"):
            reward_discount += -gross
            continue

        pct = to_decimal(line.get("discount_percent") or 0)
        discount_nominal = gross * pct / 100

        # 'amount' in the API is an Int. A fractional qty (e.g. 0.5 kg) is sent as
        # 1 item worth the whole line, so total_price stays correct.
        if qty == qty.to_integral_value():
            amount = int(qty)
            item_unit = unit
        else:
            amount = 1
            item_unit = gross

        items.append({
            "product_code": str(line["product_code"]),
            "product_name": line["product_name"],
            "price_code": str(line["price_code"]),
            "price_name": line["price_name"],
            "unit_price": money(item_unit),
            "discount_percent": money(pct),
            "discount_nominal": money(discount_nominal),
            "amount": amount,
            "total_price": money(item_unit * amount),
        })
        bruto += gross
        line_discount += discount_nominal

    return items, bruto, line_discount, reward_discount


def build_payload(order, cfg):
    """order/cfg: dicts (keys below) -> dict ready to POST.

    order: invoice_number, transaction_date, voucher_code, ppn, lines[],
           payment{issuer, transaction_id, type, provider, status, date}
    cfg:   version, tenant_code, tenant_name, service_fee_percent,
           send_payment_vendor
    """
    items, bruto, line_discount, reward_discount = build_items(order["lines"])
    if not items:
        raise ValueError("The order has no item lines.")

    discount_nominal = line_discount + reward_discount
    discount_percent = Decimal(0)
    if bruto > 0:
        discount_percent = min(Decimal(100), discount_nominal / bruto * 100)

    service_fee = (bruto - discount_nominal) * to_decimal(cfg.get("service_fee_percent")) / 100
    ppn = to_decimal(order.get("ppn"))
    netto = bruto - quantize(discount_nominal) - quantize(service_fee) - quantize(ppn)

    pay = order["payment"]
    payload = {
        "version": cfg.get("version") or "1.0.0",
        "invoice_number": order["invoice_number"],
        "tenant_code": cfg["tenant_code"],
        "tenant_name": cfg["tenant_name"],
        "voucher_code": order.get("voucher_code") or None,
        "transaction_date": order["transaction_date"],
        "bruto": money(bruto),
        "discount": money(discount_percent),
        "service_fee": money(service_fee),
        "ppn": money(ppn),
        "netto": money(netto),
        "payment_issuer": pay["issuer"],
        "payment_transactions_id": pay["transaction_id"],
        "payment_type": pay["type"],
        "payment_provider": pay["provider"],
        "payment_status": pay.get("status") or "success",
        "payment_date": pay["date"],
        "items": items,
    }
    if cfg.get("send_payment_vendor"):
        # The example request in the documentation uses 'payment_vendor' while the
        # field table uses 'payment_issuer'. Both are sent.
        payload["payment_vendor"] = pay["issuer"]
    return payload
