# -*- coding: utf-8 -*-

class PosOrderLineEntity:
    def __init__(self, id, product_id, product_tmpl_id, product_name, full_product_name,
                 qty, price_unit, discount, price_subtotal, price_subtotal_incl,
                 estimated_time, attributes, customer_note, note,
                 is_reward_line, reward_id, coupon_id,
                 kitchen_state=None, cooking_started_at=None,
                 ready_at=None, ready_source=None):
        self.id = id
        self.product_id = product_id
        self.product_tmpl_id = product_tmpl_id
        self.product_name = product_name
        self.full_product_name = full_product_name
        self.qty = qty
        self.price_unit = price_unit
        self.discount = discount
        self.price_subtotal = price_subtotal
        self.price_subtotal_incl = price_subtotal_incl
        self.estimated_time = estimated_time   # minutes, from product_estimated_time
        self.attributes = attributes           # list of strings
        self.customer_note = customer_note
        self.note = note
        self.is_reward_line = is_reward_line
        self.reward_id = reward_id
        self.coupon_id = coupon_id
        # Status memasak per hidangan; None bila modul dapur belum terpasang
        self.kitchen_state = kitchen_state
        self.cooking_started_at = cooking_started_at
        self.ready_at = ready_at
        self.ready_source = ready_source

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_tmpl_id": self.product_tmpl_id,
            "product_name": self.product_name,
            "full_product_name": self.full_product_name,
            "qty": self.qty,
            "price_unit": self.price_unit,
            "discount": self.discount,
            "price_subtotal": self.price_subtotal,
            "price_subtotal_incl": self.price_subtotal_incl,
            "estimated_time": self.estimated_time,
            "attributes": self.attributes,
            "customer_note": self.customer_note,
            "note": self.note,
            "is_reward_line": self.is_reward_line,
            "reward_id": self.reward_id,
            "coupon_id": self.coupon_id,
            "kitchen_state": self.kitchen_state,
            "cooking_started_at": self.cooking_started_at,
            "ready_at": self.ready_at,
            "ready_source": self.ready_source,
        }


class PosOrderEntity:
    def __init__(self, id, name, pos_reference, tracking_number, state, state_label,
                 date_order, processing_started_at, estimated_ready_at,
                 estimated_time_max, estimated_time_total,
                 amount_total, amount_tax, amount_paid, company_id,
                 session, config, partner, table, pricelist, general_note, lines,
                 kitchen_state=None):
        self.id = id
        self.name = name
        self.pos_reference = pos_reference
        self.tracking_number = tracking_number
        self.state = state
        self.state_label = state_label
        self.date_order = date_order
        self.processing_started_at = processing_started_at
        self.estimated_ready_at = estimated_ready_at
        # Kitchen cooks in parallel, so 'max' is the order-ready estimate;
        # 'total' is exposed for kitchens that work one dish at a time.
        self.estimated_time_max = estimated_time_max
        self.estimated_time_total = estimated_time_total
        self.amount_total = amount_total
        self.amount_tax = amount_tax
        self.amount_paid = amount_paid
        self.company_id = company_id
        self.session = session
        self.config = config
        self.partner = partner
        self.table = table
        self.pricelist = pricelist
        self.general_note = general_note
        # Diturunkan dari baris, bukan disimpan terpisah oleh API
        self.kitchen_state = kitchen_state
        self.lines = lines   # list of PosOrderLineEntity

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "pos_reference": self.pos_reference,
            "tracking_number": self.tracking_number,
            "state": self.state,
            "state_label": self.state_label,
            "date_order": self.date_order,
            "processing_started_at": self.processing_started_at,
            "estimated_ready_at": self.estimated_ready_at,
            "estimated_time_max": self.estimated_time_max,
            "estimated_time_total": self.estimated_time_total,
            "amount_total": self.amount_total,
            "amount_tax": self.amount_tax,
            "amount_paid": self.amount_paid,
            "company_id": self.company_id,
            "session": self.session,
            "config": self.config,
            "partner": self.partner,
            "table": self.table,
            "pricelist": self.pricelist,
            "general_note": self.general_note,
            "kitchen_state": self.kitchen_state,
            "lines": [line.to_dict() for line in self.lines],
        }
