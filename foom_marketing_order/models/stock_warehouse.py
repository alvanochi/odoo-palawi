from odoo import models, fields, api, exceptions, _

class StockPickingType(models.Model):

    @api.onchange('is_marketing_order')
    def onchange_is_marketing_order(self):
        for this in self:
            this.out_type_id.write({'is_marketing_order': this.is_marketing_order})

    _inherit = 'stock.warehouse'

    is_marketing_order = fields.Boolean(string='Marketing Order')

