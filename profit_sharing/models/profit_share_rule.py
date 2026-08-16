from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


POS_FINAL_STATES = ("paid", "done", "invoiced")
PNL_ACCOUNT_TYPES = (
    "income",
    "income_other",
    "expense",
    "expense_depreciation",
    "expense_direct_cost",
)


class ProfitShareRule(models.Model):
    _name = "profit.share.rule"
    _description = "Profit Sharing Rule"
    _order = "priority desc, id"

    name = fields.Char(required=True, index=True)
    share_type_id = fields.Many2one(
        "profit.share.type",
        string="Share Type",
        required=True,
        ondelete="restrict",
    )
    recipient_id = fields.Many2one(
        "res.partner",
        string="Recipient",
        required=True,
        ondelete="restrict",
        index=True,
    )
    computation_type = fields.Selection(
        [("percentage", "Percentage"), ("flat", "Flat Amount")],
        required=True,
        default="percentage",
    )
    percentage = fields.Float(digits=(16, 4), default=0.0)
    flat_amount = fields.Monetary(currency_field="currency_id", default=0.0)
    source_type = fields.Selection(
        [("pos_revenue", "POS Revenue"), ("net_profit", "Net Profit")],
        required=True,
        default="pos_revenue",
    )
    pos_config_ids = fields.Many2many(
        "pos.config",
        "profit_share_rule_pos_config_rel",
        "rule_id",
        "pos_config_id",
        string="POS Configurations",
        help="Leave empty to include all POS configurations of the selected company.",
    )
    pos_category_ids = fields.Many2many(
        "pos.category",
        "profit_share_rule_pos_category_rel",
        "rule_id",
        "pos_category_id",
        string="POS Categories",
        help="Optional. When set, POS revenue is calculated from matching order lines using tax-included line totals.",
    )
    analytic_account_ids = fields.Many2many(
        "account.analytic.account",
        "profit_share_rule_analytic_rel",
        "rule_id",
        "analytic_account_id",
        string="Analytic Accounts",
    )
    journal_ids = fields.Many2many(
        "account.journal",
        "profit_share_rule_journal_rel",
        "rule_id",
        "journal_id",
        string="Journals",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
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
    )
    date_start = fields.Date(required=True, default=fields.Date.context_today)
    date_end = fields.Date()
    priority = fields.Integer(default=10)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("archived", "Archived")],
        required=True,
        default="draft",
        index=True,
    )
    notes = fields.Text()

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rule in self:
            if rule.date_end and rule.date_start and rule.date_end < rule.date_start:
                raise ValidationError(_("Rule end date cannot be earlier than start date."))

    @api.constrains("computation_type", "percentage", "flat_amount")
    def _check_computation_values(self):
        for rule in self:
            if rule.computation_type == "percentage" and rule.percentage < 0:
                raise ValidationError(_("Percentage cannot be negative."))
            if rule.computation_type == "flat" and rule.flat_amount < 0:
                raise ValidationError(_("Flat amount cannot be negative."))

    @api.constrains("company_id", "pos_config_ids", "journal_ids", "analytic_account_ids")
    def _check_scope_company(self):
        for rule in self:
            wrong_pos = rule.pos_config_ids.filtered(lambda rec: rec.company_id != rule.company_id)
            if wrong_pos:
                raise ValidationError(_("All POS configurations must belong to rule company %s.") % rule.company_id.display_name)
            wrong_journals = rule.journal_ids.filtered(lambda rec: rec.company_id != rule.company_id)
            if wrong_journals:
                raise ValidationError(_("All journals must belong to rule company %s.") % rule.company_id.display_name)
            wrong_analytic = rule.analytic_account_ids.filtered(
                lambda rec: rec.company_id and rec.company_id != rule.company_id
            )
            if wrong_analytic:
                raise ValidationError(_("All analytic accounts must be available for rule company %s.") % rule.company_id.display_name)

    @api.constrains("source_type", "pos_config_ids", "pos_category_ids", "analytic_account_ids", "journal_ids")
    def _check_source_scope(self):
        for rule in self:
            if rule.source_type == "pos_revenue" and (rule.analytic_account_ids or rule.journal_ids):
                raise ValidationError(_("POS Revenue rules cannot contain analytic account or journal filters."))
            if rule.source_type == "net_profit" and (rule.pos_config_ids or rule.pos_category_ids):
                raise ValidationError(_("Net Profit rules cannot contain POS configuration or POS category filters."))

    @api.onchange("source_type")
    def _onchange_source_type(self):
        if self.source_type == "pos_revenue":
            self.analytic_account_ids = [(5, 0, 0)]
            self.journal_ids = [(5, 0, 0)]
        elif self.source_type == "net_profit":
            self.pos_config_ids = [(5, 0, 0)]
            self.pos_category_ids = [(5, 0, 0)]

    @api.onchange(
        "recipient_id",
        "company_id",
        "source_type",
        "pos_config_ids",
        "pos_category_ids",
        "analytic_account_ids",
        "journal_ids",
        "date_start",
        "date_end",
    )
    def _onchange_overlap_warning(self):
        if not self.recipient_id or not self.company_id or not self.source_type:
            return
        domain = [
            ("id", "!=", self._origin.id or 0),
            ("recipient_id", "=", self.recipient_id.id),
            ("company_id", "=", self.company_id.id),
            ("source_type", "=", self.source_type),
            ("state", "!=", "archived"),
        ]
        candidates = self.search(domain, limit=100)
        overlaps = candidates.filtered(lambda other: self._date_range_overlaps(other) and self._scope_overlaps(other))
        if overlaps:
            names = ", ".join(overlaps.mapped("name")[:5])
            return {
                "warning": {
                    "title": _("Potential overlapping profit-sharing rule"),
                    "message": _(
                        "This rule overlaps the source scope of: %s. Review the scope and priority to avoid double calculation."
                    )
                    % names,
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                if vals.get("state", "draft") != "draft":
                    raise AccessError(_("Profit sharing rules must be created in Draft state and confirmed through the workflow action."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if "state" in vals:
                raise AccessError(_("Change a profit sharing rule state using its workflow action."))
            if not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
                if any(rule.state != "draft" for rule in self):
                    raise AccessError(_("Only Profit Sharing Managers can edit non-draft sharing rules."))
        return super().write(vals)

    def _ensure_manager(self):
        if not self.env.su and not self.env.user.has_group("profit_sharing.group_profit_share_manager"):
            raise AccessError(_("Only Profit Sharing Managers can perform this action."))

    def action_confirm(self):
        self._ensure_manager()
        for rule in self:
            if rule.state != "draft":
                raise UserError(_("Only Draft rules can be confirmed."))
            if rule.computation_type == "percentage" and rule.percentage == 0:
                raise UserError(_("Set a percentage greater than 0 before confirming the rule."))
            if rule.computation_type == "flat" and rule.flat_amount == 0:
                raise UserError(_("Set a flat amount greater than 0 before confirming the rule."))
        self.sudo().write({"state": "confirmed"})
        return True

    def action_set_draft(self):
        self._ensure_manager()
        for rule in self:
            if rule.state not in ("confirmed", "archived"):
                raise UserError(_("Only Confirmed or Archived rules can be returned to Draft."))
        self.sudo().write({"state": "draft"})
        return True

    def action_archive(self):
        self._ensure_manager()
        for rule in self:
            if rule.state not in ("draft", "confirmed"):
                raise UserError(_("Only Draft or Confirmed rules can be archived."))
        self.sudo().write({"state": "archived"})
        return True

    def unlink(self):
        if any(rule.state != "draft" for rule in self):
            raise UserError(_("Only Draft rules can be deleted. Archive confirmed rules to preserve auditability."))
        if self.env["profit.share.line"].sudo().search_count([("rule_id", "in", self.ids)], limit=1):
            raise UserError(_("A rule that has already produced computation lines cannot be deleted. Archive it instead."))
        return super().unlink()

    def _date_range_overlaps(self, other):
        self.ensure_one()
        left_start = self.date_start or fields.Date.from_string("1900-01-01")
        left_end = self.date_end or fields.Date.from_string("9999-12-31")
        right_start = other.date_start or fields.Date.from_string("1900-01-01")
        right_end = other.date_end or fields.Date.from_string("9999-12-31")
        return left_start <= right_end and right_start <= left_end

    @staticmethod
    def _set_scope_overlaps(left_ids, right_ids):
        left = set(left_ids)
        right = set(right_ids)
        if not left or not right:
            return True
        return bool(left.intersection(right))

    def _scope_overlaps(self, other):
        self.ensure_one()
        if self.source_type != other.source_type:
            return False
        if self.source_type == "pos_revenue":
            return self._set_scope_overlaps(self.pos_config_ids.ids, other.pos_config_ids.ids) and self._set_scope_overlaps(
                self.pos_category_ids.ids, other.pos_category_ids.ids
            )
        return self._set_scope_overlaps(self.journal_ids.ids, other.journal_ids.ids) and self._set_scope_overlaps(
            self.analytic_account_ids.ids, other.analytic_account_ids.ids
        )

    def _scope_signature(self):
        self.ensure_one()
        if self.source_type == "pos_revenue":
            return (
                self.recipient_id.id,
                self.company_id.id,
                self.source_type,
                tuple(sorted(self.pos_config_ids.ids)),
                tuple(sorted(self.pos_category_ids.ids)),
            )
        return (
            self.recipient_id.id,
            self.company_id.id,
            self.source_type,
            tuple(sorted(self.journal_ids.ids)),
            tuple(sorted(self.analytic_account_ids.ids)),
        )

    def _effective_dates(self, date_from, date_to):
        self.ensure_one()
        effective_from = max(date_from, self.date_start) if self.date_start else date_from
        effective_to = min(date_to, self.date_end) if self.date_end else date_to
        return effective_from, effective_to

    def _get_pos_datetime_range(self, date_from, date_to):
        self.ensure_one()
        tz_name = self.company_id.partner_id.tz or "UTC"
        try:
            timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.UTC
        start_local = timezone.localize(datetime.combine(date_from, time.min))
        end_local = timezone.localize(datetime.combine(date_to + timedelta(days=1), time.min))
        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return start_utc, end_utc

    def _compute_base_amount(self, date_from, date_to):
        self.ensure_one()
        if date_from > date_to:
            return 0.0
        if self.source_type == "pos_revenue":
            return self._compute_pos_revenue(date_from, date_to)
        return self._compute_net_profit(date_from, date_to)

    def _compute_pos_revenue(self, date_from, date_to):
        self.ensure_one()
        start_dt, end_dt = self._get_pos_datetime_range(date_from, date_to)
        order_domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "in", POS_FINAL_STATES),
            ("date_order", ">=", start_dt),
            ("date_order", "<", end_dt),
        ]
        if self.pos_config_ids:
            order_domain.append(("config_id", "in", self.pos_config_ids.ids))

        if not self.pos_category_ids:
            orders = self.env["pos.order"].sudo().search(order_domain)
            return sum(orders.mapped("amount_total"))

        line_domain = [
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.state", "in", POS_FINAL_STATES),
            ("order_id.date_order", ">=", start_dt),
            ("order_id.date_order", "<", end_dt),
            ("product_id.pos_categ_ids", "in", self.pos_category_ids.ids),
        ]
        if self.pos_config_ids:
            line_domain.append(("order_id.config_id", "in", self.pos_config_ids.ids))
        lines = self.env["pos.order.line"].sudo().search(line_domain)
        return sum(lines.mapped("price_subtotal_incl"))

    def _compute_net_profit(self, date_from, date_to):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("move_id.state", "=", "posted"),
            ("account_id.account_type", "in", PNL_ACCOUNT_TYPES),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.analytic_account_ids:
            # Odoo 18 analytic.mixin supports domains on analytic_distribution using analytic account IDs.
            domain.append(("analytic_distribution", "in", self.analytic_account_ids.ids))

        lines = self.env["account.move.line"].sudo().search(domain)
        if not self.analytic_account_ids:
            # Revenue accounts are normally credits (negative balance) and expense accounts are debits.
            # Negating the combined P&L balance yields revenue - expense.
            return -sum(lines.mapped("balance"))

        selected_ids = set(self.analytic_account_ids.ids)
        weighted_balance = 0.0
        for line in lines:
            matched_percentage = 0.0
            for key, percentage in (line.analytic_distribution or {}).items():
                key_ids = {int(value) for value in key.split(",") if value.isdigit()}
                if key_ids.intersection(selected_ids):
                    matched_percentage += percentage
            if matched_percentage:
                weighted_balance += line.balance * (matched_percentage / 100.0)
        return -weighted_balance
