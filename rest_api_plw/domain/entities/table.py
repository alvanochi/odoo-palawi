# -*- coding: utf-8 -*-

class TableEntity:
    def __init__(self, table_id, name, seats, shape, position_x, position_y, width, height, color=None, floor_id=None):
        self.table_id = table_id
        self.name = name
        self.seats = seats
        self.shape = shape  # 'square' or 'round'
        self.position_x = position_x
        self.position_y = position_y
        self.width = width
        self.height = height
        self.color = color
        self.floor_id = floor_id

    def to_dict(self):
        return {
            "table_id": self.table_id,
            "name": self.name,
            "seats": self.seats,
            "shape": self.shape,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "floor_id": self.floor_id
        }
