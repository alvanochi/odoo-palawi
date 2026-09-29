# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    addon_product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='pos_product_addon_rel',
        column1='product_id',
        column2='addon_id',
        string='Add-ons',
        domain="[('available_in_pos', '=', True), ('id', '!=', id)]",
        help='Select add-on products related to this product variant. '
             'Only products marked as "Available in POS" can be added.',
    )
