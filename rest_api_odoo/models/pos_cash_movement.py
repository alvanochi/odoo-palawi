# models/pos_cash_movement.py
from odoo import models, fields, api

class PosCashMovement(models.Model):
    _name = "pos.cash.movement"
    _description = "POS Cash Movement"
    _order = "id desc"

    name = fields.Char(required=True, index=True)  # cmId dari Android (CM-uuid)
    session_id = fields.Char(required=True, index=True)  # pos session id dari Android
    movement_type = fields.Selection(
        [("cash_in", "Cash In"), ("cash_out", "Cash Out")],
        required=True,
        index=True
    )
    amount = fields.Integer(required=True)
    reason = fields.Char()
    pos_name = fields.Char(index=True)  # optional: nama POS/terminal
    user_name = fields.Char()           # optional
    movement_time = fields.Datetime(default=fields.Datetime.now, index=True)

    _sql_constraints = [
        ("uniq_name", "unique(name)", "Cash movement ID must be unique."),
    ]
