from odoo import models, fields, api, exceptions, _

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_marketing_order = fields.Boolean(string='Marketing Order Picking')
    internal_non_staging = fields.Boolean(string='Internal Without Staging', help="Allow Operation Without Warehouse Transfer")

