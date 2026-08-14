# -*- coding: utf-8 -*-

class CartItem:
    def __init__(self, product, qty, price, subtotal):
        self.product = product
        self.qty = qty
        self.price = price
        self.subtotal = subtotal

class PromotionProgram:
    def __init__(self, program_id, name, program_type, rules, rewards):
        self.id = program_id
        self.name = name
        self.program_type = program_type
        self.rules = rules
        self.rewards = rewards
