from datetime import timedelta
from hashlib import sha256

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class ProfitShareComputation(models.Model):
    _name = "profit.share.computation"
    _description = "Profit Sharing Computation Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _("New"), index=True)
    revision = fields.Integer(
        string="Revision",
        required=True,
        default=1,
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
        help="Revision number for the same company and calculation period. A cancelled batch is preserved and a correction is created as a new revision.",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    period_type = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("custom", "Custom"),
        ],
        required=True,
        default="monthly",
        index=True,
        tracking=True,
    )
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("approved", "Approved"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    approval_required = fields.Boolean(
        default=lambda self: self._default_approval_required(),
        readonly=True,
        help="Snapshot of the module approval setting when this batch was created.",
    )
    line_ids = fields.One2many("profit.share.line", "computation_id", string="Share Lines", copy=False)
    recipient_ids = fields.Many2many(
        "res.partner",
        compute="_compute_recipient_ids",
        string="Recipients",
    )
    total_share_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    paid_share_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    unpaid_share_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    line_count = fields.Integer(compute="_compute_totals")
    recipient_count = fields.Integer(compute="_compute_totals")
    confirmed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    confirmed_at = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    paid_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    paid_at = fields.Datetime(readonly=True, copy=False)
    last_computed_at = fields.Datetime(
        readonly=True,
        copy=False,
        help="Timestamp of the latest successful recomputation of this Draft batch.",
    )
    rule_set_token = fields.Char(
        readonly=True,
        copy=False,
        help="Internal fingerprint of the applicable sharing rules at the latest recomputation.",
    )

    _sql_constraints = [
        (
            "profit_share_batch_period_uniq",
            "unique(company_id, period_type, date_from, date_to, revision)",
            "A computation batch revision already exists for this company, period type, and date range.",
        ),
    ]

    @api.model
    def _default_approval_required(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "profit_sharing.approval_enabled", "False"
        )
        return str(value).lower() in ("1", "true", "yes")

    @api.depends("line_ids.recipient_id")
    def _compute_recipient_ids(self):
        for batch in self:
            batch.recipient_ids = batch.line_ids.mapped("recipient_id")

    @api.depends("line_ids.share_amount", "line_ids.payment_state", "line_ids.recipient_id")
    def _compute_totals(self):
        for batch in self:
            lines = batch.line_ids
            batch.total_share_amount = sum(lines.mapped("share_amount"))
            batch.paid_share_amount = sum(lines.filtered(lambda line: line.payment_state == "paid").mapped("share_amount"))
            batch.unpaid_share_amount = sum(lines.filtered(lambda line: line.payment_state == "unpaid").mapped("share_amount"))
            batch.line_count = len(lines)
            batch.recipient_count = len(lines.mapped("recipient_id"))

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for batch in self:
            if batch.date_from and batch.date_to and batch.date_to < batch.date_from:
                raise ValidationError(_("Period end date cannot be earlier than start date."))

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        reserved_keys = set()
        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            if not self.env.su and vals.get("state", "draft") != "draft":
                raise AccessError(_("Computation batches must be created in Draft state and advanced through workflow actions."))

            company_id = vals.get("company_id") or self.env.company.id
            period_type = vals.get("period_type") or "monthly"
            date_from = fields.Date.to_date(vals.get("date_from")) if vals.get("date_from") else False
            date_to = fields.Date.to_date(vals.get("date_to")) if vals.get("date_to") else False
            if date_from and date_to:
                key = (company_id, period_type, date_from, date_to)
                if key in reserved_keys:
                    raise ValidationError(_("Only one active computation batch can be created for the same company and period."))
                reserved_keys.add(key)

                period_domain = [
                    ("company_id", "=", company_id),
                    ("period_type", "=", period_type),
                    ("date_from", "=", date_from),
                    ("date_to", "=", date_to),
                ]
                active_batch = self.search(period_domain + [("state", "!=", "cancelled")], limit=1)
                if active_batch:
                    raise ValidationError(
                        _("An active computation batch already exists for this company and period: %s")
                        % active_batch.display_name
                    )
                previous_batch = self.search(period_domain, order="revision desc, id desc", limit=1)
                vals["revision"] = (previous_batch.revision + 1) if previous_batch else 1
            else:
                vals["revision"] = 1

            # Batch identity and approval policy are server-controlled snapshots.
            vals["name"] = self.env["ir.sequence"].next_by_code("profit.share.computation") or _("New")
            vals["approval_required"] = self._default_approval_required()
            prepared_vals_list.append(vals)
        return super().create(prepared_vals_list)

    def unlink(self):
        if not self.env.su and any(batch.state != "draft" for batch in self):
            raise UserError(_("Only Draft computation batches can be deleted. Cancel non-draft batches to preserve the audit trail."))
        return super().unlink()

    def write(self, vals):
        protected_period_fields = {"company_id", "period_type", "date_from", "date_to"}
        protected_workflow_fields = {
            "name",
            "revision",
            "state",
            "approval_required",
            "confirmed_by_id",
            "confirmed_at",
            "approved_by_id",
            "approved_at",
            "paid_by_id",
            "paid_at",
            "last_computed_at",
            "rule_set_token",
        }

        period_changed = bool(protected_period_fields.intersection(vals))
        if period_changed:
            if any(batch.state != "draft" for batch in self):
                raise UserError(_("Confirmed/Approved/Paid/Cancelled batches are immutable. Cancel and reset the batch to Draft before changing its period."))

        if protected_workflow_fields.intersection(vals) and not self.env.su:
            raise AccessError(_("Workflow state and audit fields can only be changed through Profit Sharing workflow actions."))

        result = super().write(vals)
        if period_changed and not self.env.context.get("profit_share_skip_period_invalidation"):
            # A Draft batch may be edited, but previously generated lines would then refer
            # to the old company/period. Clear them and force a fresh recomputation.
            for batch in self:
                had_lines = bool(batch.line_ids)
                if batch.line_ids:
                    batch.line_ids.sudo().unlink()
                batch.with_context(profit_share_skip_period_invalidation=True).sudo().write(
                    {"last_computed_at": False, "rule_set_token": False}
                )
                if had_lines:
                    batch.message_post(body=_("The computation period changed. Existing share lines were cleared; recompute the batch before confirming it."))
        return result

    def _applicable_rule_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("period_type", "=", self.period_type),
            ("state", "=", "confirmed"),
            ("date_start", "<=", self.date_to),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", self.date_from),
        ]

    def _get_applicable_rules(self):
        self.ensure_one()
        return self.env["profit.share.rule"].search(
            self._applicable_rule_domain(), order="priority desc, id asc"
        )

    def _current_rule_set_token(self):
        self.ensure_one()
        rules = self._get_applicable_rules()
        payload = "|".join(
            f"{rule.id}:{rule.write_date.isoformat() if rule.write_date else ''}"
            for rule in rules
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def action_recompute(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_user"):
            raise AccessError(_("You are not allowed to recompute profit-sharing batches."))
        for batch in self:
            if batch.state != "draft":
                raise UserError(_("Only Draft batches can be recomputed."))
            batch._recompute_lines()
        return True

    def _recompute_lines(self):
        self.ensure_one()
        self.line_ids.sudo().unlink()

        rules = self._get_applicable_rules()
        negative_policy = self.env["ir.config_parameter"].sudo().get_param(
            "profit_sharing.negative_share_policy", "allow"
        )

        handled_exact_scopes = set()
        values = []
        for rule in rules:
            effective_from, effective_to = rule._effective_dates(self.date_from, self.date_to)
            if effective_from > effective_to:
                continue

            # For an exactly identical recipient/source scope, priority selects one rule
            # for the batch. Partial scope overlap is intentionally not merged here because
            # the FSD treats it as a configuration condition that must be reviewed.
            scope_key = rule._scope_signature()
            if scope_key in handled_exact_scopes:
                continue
            handled_exact_scopes.add(scope_key)
            base_amount = rule._compute_base_amount(effective_from, effective_to)
            if rule.computation_type == "percentage":
                raw_share = base_amount * (rule.percentage / 100.0)
                rate_applied = rule.percentage
                flat_applied = 0.0
            else:
                raw_share = rule.flat_amount
                rate_applied = rule.flat_amount
                flat_applied = rule.flat_amount

            if (
                raw_share < 0
                and negative_policy == "floor_zero"
                and rule.source_type == "net_profit"
                and rule.computation_type == "percentage"
            ):
                raw_share = 0.0
            share_amount = self.currency_id.round(raw_share)
            base_amount = self.currency_id.round(base_amount)

            values.append(
                {
                    "computation_id": self.id,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "share_type_id": rule.share_type_id.id,
                    "share_type_name": rule.share_type_id.display_name,
                    "recipient_id": rule.recipient_id.id,
                    "recipient_name": rule.recipient_id.display_name,
                    "company_id": self.company_id.id,
                    "currency_id": self.currency_id.id,
                    "source_type": rule.source_type,
                    "base_amount": base_amount,
                    "computation_type": rule.computation_type,
                    "rate_applied": rate_applied,
                    "percentage_applied": rule.percentage if rule.computation_type == "percentage" else 0.0,
                    "flat_amount_applied": flat_applied,
                    "share_amount": share_amount,
                    "payment_state": "unpaid",
                    "effective_date_from": effective_from,
                    "effective_date_to": effective_to,
                    "priority_applied": rule.priority,
                }
            )
        if values:
            self.env["profit.share.line"].sudo().create(values)
        self.sudo().write(
            {
                "last_computed_at": fields.Datetime.now(),
                "rule_set_token": self._current_rule_set_token(),
            }
        )
        self.message_post(body=_("Computation recomputed. %s share line(s) generated.") % len(values))

    def action_confirm(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
            raise AccessError(_("Only Profit Sharing Managers can confirm a batch."))
        for batch in self:
            if batch.state != "draft":
                raise UserError(_("Only Draft batches can be confirmed."))
            if not batch.line_ids:
                raise UserError(_("Recompute the batch first; there are no share lines to confirm."))
            if not batch.rule_set_token or batch.rule_set_token != batch._current_rule_set_token():
                raise UserError(_("Sharing rules changed after this batch was computed. Recompute the batch and review the updated amounts before confirming."))
            batch.sudo().write(
                {
                    "state": "confirmed",
                    "confirmed_by_id": self.env.user.id,
                    "confirmed_at": fields.Datetime.now(),
                }
            )
        return True

    def action_approve(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_approver"):
            raise AccessError(_("You are not allowed to approve profit-sharing batches."))
        for batch in self:
            if not batch.approval_required:
                raise UserError(_("Approval is not enabled for this batch."))
            if batch.state != "confirmed":
                raise UserError(_("Only Confirmed batches can be approved."))
            batch.sudo().write(
                {
                    "state": "approved",
                    "approved_by_id": self.env.user.id,
                    "approved_at": fields.Datetime.now(),
                }
            )
        return True

    def action_mark_paid(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_payment"):
            raise AccessError(_("You are not allowed to mark profit-sharing batches as paid."))
        for batch in self:
            expected_state = "approved" if batch.approval_required else "confirmed"
            if batch.state != expected_state:
                raise UserError(
                    _("Batch %(batch)s must be in %(state)s state before it can be marked Paid.")
                    % {"batch": batch.display_name, "state": expected_state.title()}
                )
            batch.line_ids.with_context(profit_share_skip_batch_sync=True).sudo().write({"payment_state": "paid"})
            batch.sudo().write(
                {
                    "state": "paid",
                    "paid_by_id": self.env.user.id,
                    "paid_at": fields.Datetime.now(),
                }
            )
        return True

    def action_cancel(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
            raise AccessError(_("Only Profit Sharing Managers can cancel batches."))
        for batch in self:
            if batch.state == "paid" or any(line.payment_state == "paid" for line in batch.line_ids):
                raise UserError(_("A batch with paid share lines cannot be cancelled directly. Reopen all paid lines first if a correction is required."))
            if batch.state not in ("draft", "confirmed", "approved"):
                raise UserError(_("Only Draft, Confirmed, or Approved batches can be cancelled."))
            batch.sudo().write({"state": "cancelled"})
        return True

    def action_create_correction(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
            raise AccessError(_("Only Profit Sharing Managers can create a correction from a cancelled batch."))
        self.ensure_one()
        if self.state != "cancelled":
            raise UserError(_("A correction can only be created from a Cancelled batch."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Calculate Correction"),
            "res_model": "profit.share.compute.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_company_id": self.company_id.id,
                "default_period_type": self.period_type,
                "default_date_from": self.date_from,
                "default_date_to": self.date_to,
            },
        }

    def _sync_paid_state_from_lines(self):
        for batch in self:
            if batch.state == "cancelled" or not batch.line_ids:
                continue
            all_paid = all(line.payment_state == "paid" for line in batch.line_ids)
            if all_paid and batch.state in ("confirmed", "approved"):
                actor_id = self.env.context.get("profit_share_payment_actor_id") or self.env.user.id
                batch.sudo().write(
                    {"state": "paid", "paid_by_id": actor_id, "paid_at": fields.Datetime.now()}
                )
            elif not all_paid and batch.state == "paid":
                fallback = "approved" if batch.approval_required else "confirmed"
                batch.sudo().write({"state": fallback, "paid_by_id": False, "paid_at": False})

    @api.model
    def _cron_generate_batches(self):
        today = fields.Date.context_today(self)
        due_periods = []

        # Daily rules: yesterday is complete.
        yesterday = today - timedelta(days=1)
        due_periods.append(("daily", yesterday, yesterday))

        # Weekly rules use Monday-Sunday calendar weeks and are generated each Monday.
        if today.weekday() == 0:
            previous_week_end = today - timedelta(days=1)
            previous_week_start = previous_week_end - timedelta(days=6)
            due_periods.append(("weekly", previous_week_start, previous_week_end))

        # Monthly rules are generated on the first day of the next month.
        if today.day == 1:
            previous_month_end = today - timedelta(days=1)
            previous_month_start = previous_month_end.replace(day=1)
            due_periods.append(("monthly", previous_month_start, previous_month_end))

        Rule = self.env["profit.share.rule"].sudo()
        Batch = self.sudo()
        for period_type, date_from, date_to in due_periods:
            company_ids = Rule.search(
                [
                    ("state", "=", "confirmed"),
                    ("period_type", "=", period_type),
                    ("date_start", "<=", date_to),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", date_from),
                ]
            ).mapped("company_id").ids
            for company_id in company_ids:
                existing = Batch.search_count(
                    [
                        ("company_id", "=", company_id),
                        ("period_type", "=", period_type),
                        ("date_from", "=", date_from),
                        ("date_to", "=", date_to),
                    ]
                )
                if existing:
                    continue
                batch = Batch.create(
                    {
                        "company_id": company_id,
                        "period_type": period_type,
                        "date_from": date_from,
                        "date_to": date_to,
                    }
                )
                batch._recompute_lines()
        return True
