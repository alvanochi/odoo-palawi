from odoo import models, fields

class PosOrder(models.Model):
    _inherit = "pos.order"

    name_waiters = fields.Char("Waiters")
    change_amount = fields.Float("Change Amount", default=0.0, digits=0)
