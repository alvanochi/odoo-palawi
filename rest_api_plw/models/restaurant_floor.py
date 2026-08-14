# -*- coding: utf-8 -*-
from odoo import models, fields

class RestaurantFloor(models.Model):
    _inherit = 'restaurant.floor'

    floor_type = fields.Selection([
        ('indoor', 'Indoor'),
        ('outdoor', 'Outdoor'),
        ('vip', 'VIP')
    ], string='Floor Type', default='indoor', required=True)
