from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProfitShareSettings(models.TransientModel):
    _name = "profit.share.settings"
    _description = "Profit Sharing Settings"

    approval_enabled = fields.Boolean(
        string="Enable Approval Step",
        help="When enabled, Confirmed computation batches must be Approved before they can be marked Paid.",
    )
    negative_policy = fields.Selection(
        [
            ("allow", "Allow Negative Share"),
            ("floor_zero", "Floor Negative Share to Zero"),
        ],
        string="Negative Net Profit Policy",
        required=True,
        default="allow",
        help="Controls percentage-based share results when the calculated accounting net profit is negative.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        params = self.env["ir.config_parameter"].sudo()
        if "approval_enabled" in fields_list:
            raw_approval = params.get_param("profit_sharing.approval_enabled", "False")
            values["approval_enabled"] = str(raw_approval).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if "negative_policy" in fields_list:
            policy = params.get_param("profit_sharing.negative_share_policy", "allow")
            values["negative_policy"] = policy if policy in {"allow", "floor_zero"} else "allow"
        return values

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
            raise AccessError(_("Only Profit Sharing Managers can change these settings."))

        params = self.env["ir.config_parameter"].sudo()
        params.set_param("profit_sharing.approval_enabled", "True" if self.approval_enabled else "False")
        params.set_param("profit_sharing.negative_share_policy", self.negative_policy or "allow")
        return {"type": "ir.actions.act_window_close"}
