# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosKitchenOrder(models.Model):
    _name = "pos.kitchen.order"
    _description = "POS Kitchen Order"
    _order = "create_date desc"

    # Relasi wajib yang Anda panggil di view
    pos_order_line_id = fields.Many2one(
        "pos.order.line", string="POS Order Line",
        required=True, ondelete="cascade"
    )

    # Field yang dipanggil di view
    product_id = fields.Many2one(
        "product.product", string="Product",
        compute="_compute_from_line", store=True, readonly=True
    )
    qty = fields.Float(
        string="Qty",
        compute="_compute_from_line", store=True, readonly=True
    )
    note = fields.Char(string="Note")
    state = fields.Selection([
        ("new", "New"),
        ("cooking", "Cooking"),
        ("done", "Done"),
        ("cancel", "Canceled"),
    ], default="new", index=True, required=True)

    # Flag debug yang Anda tampilkan di tree
    is_latest_active = fields.Boolean(string="Latest Active", default=True)
    is_superseded = fields.Boolean(string="Superseded", default=False)

    @api.depends("pos_order_line_id", "pos_order_line_id.product_id", "pos_order_line_id.qty")
    def _compute_from_line(self):
        for rec in self:
            line = rec.pos_order_line_id
            rec.product_id = line.product_id.id if line else False
            rec.qty = line.qty if line else 0.0
