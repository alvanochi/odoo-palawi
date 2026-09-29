# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = "res.partner"

    member_type_id = fields.Many2one(
        "member.type",
        string="Member Type",
        help="Tipe membership untuk contact ini.",
    )
    member_points = fields.Float(
        string="Points",
        default=0.0,
        help="Saldo point membership (manual). Nanti bisa diintegrasikan ke POS/Order.",
    )
    member_active = fields.Boolean(
        string="Membership Active",
        default=True,
        help="Nonaktifkan membership tanpa menghapus contact.",
    )
