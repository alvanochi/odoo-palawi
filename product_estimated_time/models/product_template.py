# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    estimated_time = fields.Integer(
        string='Estimated Time',
        help='Estimated time until this product is ready.')

    @api.model
    def _load_pos_data_fields(self, config_id):
        pos_fields = super()._load_pos_data_fields(config_id)
        if 'estimated_time' not in pos_fields:
            pos_fields.append('estimated_time')
        return pos_fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        pos_fields = super()._load_pos_data_fields(config_id)
        if 'estimated_time' not in pos_fields:
            pos_fields.append('estimated_time')
        return pos_fields
