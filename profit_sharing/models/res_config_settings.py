from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    profit_share_approval_enabled = fields.Boolean(
        string="Enable Approval Step",
        config_parameter="profit_sharing.approval_enabled",
        help="When enabled, Confirmed computation batches must be Approved before they can be marked Paid.",
    )
    profit_share_negative_policy = fields.Selection(
        [("allow", "Allow Negative Share"), ("floor_zero", "Floor Negative Share to Zero")],
        string="Negative Net Profit Policy",
        default="allow",
        config_parameter="profit_sharing.negative_share_policy",
        help="Controls percentage-based share results when the calculated net profit is negative.",
    )
