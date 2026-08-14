# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    head_user_id = fields.Many2one(
        'res.users',
        string='Head User / Atasan',
        domain="[('company_ids', 'in', id)]",
        help="The single user designated as head/approver for this company."
    )
