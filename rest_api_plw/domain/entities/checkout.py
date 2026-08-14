# -*- coding: utf-8 -*-

class CheckoutItemEntity:
    def __init__(self, product_id, qty, variant_id=None):
        self.product_id = product_id
        self.qty = qty
        self.variant_id = variant_id


class CheckoutResultEntity:
    def __init__(self, order_id, order_name, amount_total, table_number, customer_name, bill_id=None,
                 session_id=None, state=None, tracking_number=None, pricelist=None,
                 discount_total=0.0, rewards_applied=None):
        self.order_id = order_id
        self.order_name = order_name
        self.amount_total = amount_total
        self.table_number = table_number
        self.customer_name = customer_name
        self.bill_id = bill_id
        self.session_id = session_id
        self.state = state
        self.tracking_number = tracking_number
        self.pricelist = pricelist            # dict {"id","name"} or None
        self.discount_total = discount_total
        self.rewards_applied = rewards_applied or []

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "order_name": self.order_name,
            "amount_total": self.amount_total,
            "table_number": self.table_number,
            "customer_name": self.customer_name,
            "bill_id": self.bill_id,
            "session_id": self.session_id,
            "state": self.state,
            "tracking_number": self.tracking_number,
            "pricelist": self.pricelist,
            "discount_total": self.discount_total,
            "rewards_applied": self.rewards_applied,
        }
