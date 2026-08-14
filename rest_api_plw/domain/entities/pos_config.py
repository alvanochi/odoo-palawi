# -*- coding: utf-8 -*-

class PosConfigEntity:
    def __init__(self, id, name, company_id, active, module_pos_restaurant,
                 use_pricelist, pricelist, available_pricelists, limit_categories,
                 available_categories, payment_methods, picking_type, currency,
                 current_session):
        self.id = id
        self.name = name
        self.company_id = company_id
        self.active = active
        self.module_pos_restaurant = module_pos_restaurant
        self.use_pricelist = use_pricelist
        self.pricelist = pricelist                      # dict {"id","name"} or None
        self.available_pricelists = available_pricelists  # list of dicts
        self.limit_categories = limit_categories
        self.available_categories = available_categories  # list of dicts
        self.payment_methods = payment_methods            # list of dicts
        self.picking_type = picking_type                  # dict or None
        self.currency = currency                          # dict or None
        self.current_session = current_session            # dict or None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "company_id": self.company_id,
            "active": self.active,
            "module_pos_restaurant": self.module_pos_restaurant,
            "use_pricelist": self.use_pricelist,
            "pricelist": self.pricelist,
            "available_pricelists": self.available_pricelists,
            "limit_categories": self.limit_categories,
            "available_categories": self.available_categories,
            "payment_methods": self.payment_methods,
            "picking_type": self.picking_type,
            "currency": self.currency,
            "current_session": self.current_session,
        }
