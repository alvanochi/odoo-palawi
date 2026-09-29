# -*- coding: utf-8 -*-
from odoo import api, fields, models

class RestaurantFloor(models.Model):
    _inherit = "restaurant.floor"

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("company_id", self.env.company.id)
        return super().create(vals_list)
