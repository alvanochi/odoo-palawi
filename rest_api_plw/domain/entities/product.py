# -*- coding: utf-8 -*-

class ProductEntity:
    def __init__(self, id, name, type, is_storable, list_price, standard_price, company_id, stock_qty, image_url, category, pos_categories, attributes, variants):
        self.id = id
        self.name = name
        self.type = type
        self.is_storable = is_storable
        self.list_price = list_price
        self.standard_price = standard_price
        self.company_id = company_id
        self.stock_qty = stock_qty
        self.image_url = image_url
        self.category = category  # dict: {"id": x, "name": y} or None
        self.pos_categories = pos_categories  # list of dicts: [{"id": x, "name": y}]
        self.attributes = attributes  # list of dicts: [{"name": x, "values": [...]}]
        self.variants = variants  # list of dicts: [{"id": x, "display_name": y, "price": z, "stock_qty": w}]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "is_storable": self.is_storable,
            "list_price": self.list_price,
            "standard_price": self.standard_price,
            "company_id": self.company_id,
            "stock_qty": self.stock_qty,
            "image_url": self.image_url,
            "category": self.category,
            "pos_categories": self.pos_categories,
            "attributes": self.attributes,
            "variants": self.variants
        }
