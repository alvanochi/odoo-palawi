from odoo import fields, models

class PosConfig(models.Model):
    _inherit = "pos.config"

    qris_merchant_id = fields.Char("QRIS Merchant ID")
