# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    contract_id = fields.Many2one(
        'partner.contract', string='Kontrak', copy=False, index=True)
