from odoo import models, fields, api


class PoskasBillLine(models.Model):
    _name = "poskas.bill.line"
    _description = "POSKAS Bill Line"

    bill_id = fields.Many2one(
        "poskas.bill",
        required=True,
        ondelete="cascade",
        index=True
    )

    product_id = fields.Many2one(
        "product.product",
        required=True,
        index=True
    )

    qty = fields.Float(default=1.0)
    price_unit = fields.Float(default=0.0)
    note = fields.Char()

    discount_percent = fields.Float(
        string="Discount Percent",
        default=0.0
    )

    subtotal = fields.Float(
        compute="_compute_subtotal",
        store=True
    )

    @api.depends("qty", "price_unit", "discount_percent")
    def _compute_subtotal(self):
        for line in self:
            qty = line.qty or 0.0
            price_unit = line.price_unit or 0.0
            discount_percent = line.discount_percent or 0.0

            if discount_percent < 0.0:
                discount_percent = 0.0
            if discount_percent > 100.0:
                discount_percent = 100.0

            price_after_discount = price_unit - (price_unit * discount_percent / 100.0)
            if price_after_discount < 0.0:
                price_after_discount = 0.0

            line.subtotal = qty * price_after_discount