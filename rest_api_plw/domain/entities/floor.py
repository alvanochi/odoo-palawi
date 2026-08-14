# -*- coding: utf-8 -*-

class FloorEntity:
    def __init__(self, floor_id, name, floor_type, background_color=None, tables=None):
        self.floor_id = floor_id
        self.name = name
        self.floor_type = floor_type  # 'indoor', 'outdoor', 'vip'
        self.background_color = background_color
        self.tables = tables or []

    def to_dict(self):
        return {
            "floor_id": self.floor_id,
            "name": self.name,
            "floor_type": self.floor_type,
            "background_color": self.background_color,
            "tables": [table.to_dict() for table in self.tables]
        }
