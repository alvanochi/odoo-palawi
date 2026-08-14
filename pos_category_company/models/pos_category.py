from odoo import models, fields

class PosCategory(models.Model):
    _inherit = "pos.category"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True
    )

    pos_ids = fields.Many2many(
        "pos.config",
        "pos_category_config_rel",
        "category_id",
        "config_id",
        string="Allowed POS",
        domain="[('company_id', '=', company_id)]",
        help="Allowed POS configurations for this category"
    )
