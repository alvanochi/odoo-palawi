from odoo import fields, models


class ProfitShareType(models.Model):
    _name = "profit.share.type"
    _description = "Profit Sharing Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("profit_share_type_name_uniq", "unique(name)", "Share Type name must be unique."),
        ("profit_share_type_code_uniq", "unique(code)", "Share Type code must be unique."),
    ]
