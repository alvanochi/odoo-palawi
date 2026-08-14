# -*- coding: utf-8 -*-
import re
from odoo import fields
from ..domain.entities.floor import FloorEntity
from ..domain.entities.table import TableEntity

class TableRepository:
    def __init__(self, env):
        self.env = env

    def _extract_table_number(self, name):
        if not name:
            return 0
        digits = re.findall(r'\d+', str(name))
        if digits:
            try:
                return int("".join(digits))
            except ValueError:
                pass
        return 0

    def find_layout_by_pos_config(self, pos_config_id):
        # 1. Browse POS Config
        pos_config = self.env['pos.config'].sudo().browse(pos_config_id)
        if not pos_config.exists():
            return []

        # 2. Get associated floors
        floors = pos_config.floor_ids
        floor_entities = []

        for floor in floors:
            table_entities = []
            for table in floor.table_ids:
                # Map Odoo table fields to TableEntity attributes
                # In Odoo 18:
                # position_h -> position_x
                # position_v -> position_y
                table_name = str(table.table_number)
                if table.identifier:
                    # If we have an identifier (e.g. customized label/uuid), we can use it or display name
                    # Let's use display name or table number
                    pass

                table_entities.append(TableEntity(
                    table_id=table.id,
                    name=table_name,
                    seats=table.seats,
                    shape=table.shape,
                    position_x=table.position_h,
                    position_y=table.position_v,
                    width=table.width,
                    height=table.height,
                    color=table.color,
                    floor_id=floor.id
                ))

            floor_entities.append(FloorEntity(
                floor_id=floor.id,
                name=floor.name,
                floor_type=getattr(floor, 'floor_type', 'indoor'),
                background_color=floor.background_color,
                tables=table_entities
            ))

        return floor_entities

    def create_floor(self, pos_config_id, name, floor_type, background_color):
        floor_rec = self.env['restaurant.floor'].sudo().create({
            'name': name,
            'floor_type': floor_type or 'indoor',
            'background_color': background_color or '#ffffff',
            'pos_config_ids': [(4, pos_config_id)]
        })
        return floor_rec.id

    def update_floor(self, floor_id, data):
        floor_rec = self.env['restaurant.floor'].sudo().browse(floor_id)
        if not floor_rec.exists():
            return False

        vals = {}
        if 'name' in data:
            vals['name'] = data['name']
        if 'floor_type' in data:
            vals['floor_type'] = data['floor_type']
        if 'background_color' in data:
            vals['background_color'] = data['background_color']

        if vals:
            floor_rec.write(vals)
        return True

    def delete_floor(self, floor_id):
        floor_rec = self.env['restaurant.floor'].sudo().browse(floor_id)
        if not floor_rec.exists():
            return False
        floor_rec.unlink()
        return True

    def floor_exists(self, floor_id):
        if not floor_id:
            return False
        floor_rec = self.env['restaurant.floor'].sudo().browse(floor_id)
        return floor_rec.exists()

    def create_table(self, floor_id, data):
        name = data.get('name')
        table_number = self._extract_table_number(name)

        table_rec = self.env['restaurant.table'].sudo().create({
            'floor_id': floor_id,
            'table_number': table_number,
            'seats': data.get('seats', 2),
            'shape': data.get('shape', 'square'),
            'position_h': data.get('position_x', 10.0),
            'position_v': data.get('position_y', 10.0),
            'width': data.get('width', 80.0),
            'height': data.get('height', 80.0),
            'color': data.get('color', '#35D374')
        })
        return table_rec.id

    def update_table(self, table_id, data):
        table_rec = self.env['restaurant.table'].sudo().browse(table_id)
        if not table_rec.exists():
            return False

        vals = {}
        if 'name' in data:
            vals['table_number'] = self._extract_table_number(data['name'])
        if 'seats' in data:
            vals['seats'] = int(data['seats'])
        if 'shape' in data:
            vals['shape'] = data['shape']
        if 'position_x' in data:
            vals['position_h'] = float(data['position_x'])
        if 'position_y' in data:
            vals['position_v'] = float(data['position_y'])
        if 'width' in data:
            vals['width'] = float(data['width'])
        if 'height' in data:
            vals['height'] = float(data['height'])
        if 'color' in data:
            vals['color'] = data['color']

        if vals:
            table_rec.write(vals)
        return True

    def delete_table(self, table_id):
        table_rec = self.env['restaurant.table'].sudo().browse(table_id)
        if not table_rec.exists():
            return False
        table_rec.unlink()
        return True
