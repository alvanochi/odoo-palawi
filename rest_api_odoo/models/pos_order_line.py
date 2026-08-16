from odoo import models, fields

class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    note = fields.Char(string="Item Note")
