# -*- coding: utf-8 -*-
from odoo import models, fields

class MembershipType(models.Model):
    _name = "member.type"
    _description = "Member Type"
    _order = "sequence, name"
    _rec_name = "name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    note = fields.Text()

    earn_value = fields.Float(
        default=10000.0,
    )

    redeem_value = fields.Float(
        default=1000.0,
    )
