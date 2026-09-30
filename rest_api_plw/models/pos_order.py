# -*- coding: utf-8 -*-
from odoo import fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    evidence = fields.Binary(
        string='Payment Evidence',
        attachment=True,
        help='Photo or document evidence of payment uploaded from POS client.',
    )
