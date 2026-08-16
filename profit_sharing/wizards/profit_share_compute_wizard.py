from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProfitShareComputeWizard(models.TransientModel):
    _name = "profit.share.compute.wizard"
    _description = "Create Profit Sharing Computation"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    period_type = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("custom", "Custom")],
        required=True,
        default="monthly",
    )
    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    def action_compute(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise ValidationError(_("Period end date cannot be earlier than start date."))
        Batch = self.env["profit.share.computation"]
        period_domain = [
            ("company_id", "=", self.company_id.id),
            ("period_type", "=", self.period_type),
            ("date_from", "=", self.date_from),
            ("date_to", "=", self.date_to),
        ]
        batch = Batch.search(period_domain + [("state", "!=", "cancelled")], limit=1)
        if batch:
            if batch.state != "draft":
                raise UserError(
                    _("An active computation batch already exists for this company and period and is not in Draft state: %s")
                    % batch.display_name
                )
        else:
            # Cancelled batches are immutable audit records. Creating the same period again
            # produces a new revision instead of deleting the historical calculation.
            batch = Batch.create(
                {
                    "company_id": self.company_id.id,
                    "period_type": self.period_type,
                    "date_from": self.date_from,
                    "date_to": self.date_to,
                }
            )
        batch.action_recompute()
        return {
            "type": "ir.actions.act_window",
            "name": _("Profit Sharing Computation"),
            "res_model": "profit.share.computation",
            "res_id": batch.id,
            "view_mode": "form",
            "target": "current",
        }
