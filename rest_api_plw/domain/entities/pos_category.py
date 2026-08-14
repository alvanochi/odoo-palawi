# -*- coding: utf-8 -*-

class PosCategoryEntity:
    def __init__(self, id, name, parent, company_id, allowed_pos, image_url):
        self.id = id
        self.name = name
        self.parent = parent  # dict: {"id": x, "name": y} or None
        self.company_id = company_id
        self.allowed_pos = allowed_pos  # list of dicts: [{"id": x, "name": y}]
        self.image_url = image_url

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "parent": self.parent,
            "company_id": self.company_id,
            "allowed_pos": self.allowed_pos,
            "image_url": self.image_url
        }
