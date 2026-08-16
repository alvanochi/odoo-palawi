from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .profit_share_rule import POS_FINAL_STATES, PNL_ACCOUNT_TYPES


REPORTABLE_BATCH_STATES = ("confirmed", "approved", "paid")


class ProfitShareDashboard(models.AbstractModel):
    _name = "profit.share.dashboard"
    _description = "Profit Sharing Dashboard Service"

    @api.model
    def get_dashboard_data(self, filters=None):
        if not self.env.user.has_group("profit_sharing.group_profit_share_user"):
            raise AccessError(_("You do not have access to the Profit Sharing dashboard."))

        filters = filters or {}
        today = fields.Date.context_today(self)
        default_start = today.replace(day=1)
        date_from = fields.Date.to_date(filters.get("date_from")) if filters.get("date_from") else default_start
        date_to = fields.Date.to_date(filters.get("date_to")) if filters.get("date_to") else today
        if date_to < date_from:
            raise ValidationError(_("Dashboard end date cannot be earlier than start date."))

        allowed_companies = self.env.companies
        requested_company_id = self._to_int(filters.get("company_id"), _("Company"))
        if requested_company_id:
            companies = allowed_companies.filtered(lambda company: company.id == requested_company_id)
            if not companies:
                raise AccessError(_("The selected company is not available to the current user."))
        else:
            companies = allowed_companies

        currency_ids = set(companies.mapped("currency_id").ids)
        if len(currency_ids) > 1:
            raise ValidationError(_("Cross-company currency conversion is outside phase 1. Select one company, or companies using the same currency."))

        share_type_id = self._to_int(filters.get("share_type_id"), _("Share Type"))
        recipient_id = self._to_int(filters.get("recipient_id"), _("Recipient"))
        payment_state = filters.get("payment_state") or "all"
        if payment_state not in ("all", "paid", "unpaid"):
            raise ValidationError(_("Invalid Payment filter value."))

        line_domain = [
            ("company_id", "in", companies.ids),
            ("computation_id.state", "in", REPORTABLE_BATCH_STATES),
            ("computation_id.date_from", "<=", date_to),
            ("computation_id.date_to", ">=", date_from),
        ]
        if share_type_id:
            line_domain.append(("share_type_id", "=", share_type_id))
        if recipient_id:
            line_domain.append(("recipient_id", "=", recipient_id))
        if payment_state in ("paid", "unpaid"):
            line_domain.append(("payment_state", "=", payment_state))

        lines = self.env["profit.share.line"].search(line_domain)
        total_share = sum(lines.mapped("share_amount"))
        paid_share = sum(lines.filtered(lambda line: line.payment_state == "paid").mapped("share_amount"))
        unpaid_share = sum(lines.filtered(lambda line: line.payment_state == "unpaid").mapped("share_amount"))

        total_pos_revenue = sum(self._company_pos_revenue(company, date_from, date_to) for company in companies)
        total_net_profit = sum(self._company_net_profit(company, date_from, date_to) for company in companies)

        rule_domain = [
            ("state", "=", "confirmed"),
            ("company_id", "in", companies.ids),
            ("date_start", "<=", date_to),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", date_from),
        ]
        option_rule_domain = list(rule_domain)
        if share_type_id:
            rule_domain.append(("share_type_id", "=", share_type_id))
            option_rule_domain.append(("share_type_id", "=", share_type_id))
        if recipient_id:
            rule_domain.append(("recipient_id", "=", recipient_id))
        active_rules = self.env["profit.share.rule"].search(rule_domain)
        active_recipients = active_rules.mapped("recipient_id")

        # Keep the recipient selector usable after a recipient has been selected: its
        # options honor company/date/share-type filters but not the current recipient.
        option_recipients = self.env["profit.share.rule"].search(option_rule_domain).mapped("recipient_id")
        selectable_recipients = (option_recipients | lines.mapped("recipient_id")).sorted("name")

        type_totals = {}
        recipient_totals = {}
        for line in lines:
            type_key = line.share_type_id.id
            type_totals.setdefault(
                type_key,
                {
                    "id": type_key,
                    "name": line.share_type_name or line.share_type_id.display_name,
                    "amount": 0.0,
                    "color": line.share_type_id.color,
                },
            )
            type_totals[type_key]["amount"] += line.share_amount

            recipient_key = line.recipient_id.id
            recipient_totals.setdefault(
                recipient_key,
                {
                    "id": recipient_key,
                    "name": line.recipient_name or line.recipient_id.display_name,
                    "share_types": set(),
                    "amount": 0.0,
                    "paid": 0.0,
                    "unpaid": 0.0,
                },
            )
            recipient_totals[recipient_key]["share_types"].add(
                line.share_type_name or line.share_type_id.display_name
            )
            recipient_totals[recipient_key]["amount"] += line.share_amount
            recipient_totals[recipient_key][line.payment_state] += line.share_amount

        for item in recipient_totals.values():
            item["share_type"] = ", ".join(sorted(item.pop("share_types")))

        top_recipients = sorted(recipient_totals.values(), key=lambda item: item["amount"], reverse=True)[:10]
        share_type_breakdown = sorted(type_totals.values(), key=lambda item: item["amount"], reverse=True)

        recent_domain = [
            ("company_id", "in", companies.ids),
            ("date_from", "<=", date_to),
            ("date_to", ">=", date_from),
            ("state", "!=", "cancelled"),
        ]
        if share_type_id:
            recent_domain.append(("line_ids.share_type_id", "=", share_type_id))
        if recipient_id:
            recent_domain.append(("line_ids.recipient_id", "=", recipient_id))
        if payment_state in ("paid", "unpaid"):
            recent_domain.append(("line_ids.payment_state", "=", payment_state))
        recent_batches = self.env["profit.share.computation"].search(
            recent_domain,
            order="date_from desc, id desc",
            limit=10,
        )

        trend = self._build_monthly_trend(companies, date_from, date_to, share_type_id, recipient_id, payment_state)

        currency = companies[:1].currency_id if len(companies) == 1 else self.env.company.currency_id
        return {
            "filters": {
                "date_from": fields.Date.to_string(date_from),
                "date_to": fields.Date.to_string(date_to),
                "company_id": requested_company_id or False,
                "share_type_id": share_type_id or False,
                "recipient_id": recipient_id or False,
                "payment_state": payment_state,
            },
            "currency": {
                "id": currency.id,
                "name": currency.name,
                "symbol": currency.symbol,
                "position": currency.position,
                "decimal_places": currency.decimal_places,
            },
            "kpis": {
                "pos_revenue": total_pos_revenue,
                "net_profit": total_net_profit,
                "total_share": total_share,
                "paid_share": paid_share,
                "unpaid_share": unpaid_share,
                "active_recipient_count": len(active_recipients),
            },
            "share_type_breakdown": share_type_breakdown,
            "top_recipients": top_recipients,
            "trend": trend,
            "recent_batches": [
                self._serialize_recent_batch(batch, share_type_id, recipient_id, payment_state)
                for batch in recent_batches
            ],
            "options": {
                "companies": [{"id": company.id, "name": company.display_name} for company in allowed_companies],
                "share_types": [
                    {"id": share_type.id, "name": share_type.display_name}
                    for share_type in self.env["profit.share.type"].search([])
                ],
                "recipients": [
                    {"id": recipient.id, "name": recipient.display_name}
                    for recipient in selectable_recipients
                ],
            },
        }

    @api.model
    def _serialize_recent_batch(self, batch, share_type_id=False, recipient_id=False, payment_state="all"):
        lines = batch.line_ids
        if share_type_id:
            lines = lines.filtered(lambda line: line.share_type_id.id == share_type_id)
        if recipient_id:
            lines = lines.filtered(lambda line: line.recipient_id.id == recipient_id)
        if payment_state in ("paid", "unpaid"):
            lines = lines.filtered(lambda line: line.payment_state == payment_state)
        return {
            "id": batch.id,
            "name": batch.name,
            "revision": batch.revision,
            "company": batch.company_id.display_name,
            "period_type": batch.period_type,
            "date_from": fields.Date.to_string(batch.date_from),
            "date_to": fields.Date.to_string(batch.date_to),
            "state": batch.state,
            "total_share": sum(lines.mapped("share_amount")),
            "unpaid_share": sum(lines.filtered(lambda line: line.payment_state == "unpaid").mapped("share_amount")),
            "recipient_count": len(lines.mapped("recipient_id")),
        }

    @api.model
    def _to_int(self, value, label):
        if value in (None, False, "", "0", 0):
            return False
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(_("Invalid dashboard filter value for %s.") % label) from exc

    @api.model
    def _company_pos_datetime_range(self, company, date_from, date_to):
        tz_name = company.partner_id.tz or "UTC"
        try:
            timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.UTC
        start_local = timezone.localize(datetime.combine(date_from, time.min))
        end_local = timezone.localize(datetime.combine(date_to + timedelta(days=1), time.min))
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            end_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @api.model
    def _company_pos_revenue(self, company, date_from, date_to):
        start_dt, end_dt = self._company_pos_datetime_range(company, date_from, date_to)
        orders = self.env["pos.order"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("state", "in", POS_FINAL_STATES),
                ("date_order", ">=", start_dt),
                ("date_order", "<", end_dt),
            ]
        )
        return sum(orders.mapped("amount_total"))

    @api.model
    def _company_net_profit(self, company, date_from, date_to):
        lines = self.env["account.move.line"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("move_id.state", "=", "posted"),
                ("account_id.account_type", "in", PNL_ACCOUNT_TYPES),
            ]
        )
        return -sum(lines.mapped("balance"))

    @api.model
    def _build_monthly_trend(self, companies, date_from, date_to, share_type_id, recipient_id, payment_state):
        # Limit very broad filters to the latest 12 monthly buckets for a responsive dashboard.
        month_start = date_from.replace(day=1)
        final_month = date_to.replace(day=1)
        buckets = []
        cursor = month_start
        while cursor <= final_month:
            buckets.append(cursor)
            cursor += relativedelta(months=1)
        buckets = buckets[-12:]

        result = []
        for start in buckets:
            next_month = start + relativedelta(months=1)
            end = min(next_month - timedelta(days=1), date_to)
            effective_start = max(start, date_from)
            line_domain = [
                ("company_id", "in", companies.ids),
                ("computation_id.state", "in", REPORTABLE_BATCH_STATES),
                ("computation_id.date_from", ">=", effective_start),
                ("computation_id.date_from", "<=", end),
            ]
            if share_type_id:
                line_domain.append(("share_type_id", "=", share_type_id))
            if recipient_id:
                line_domain.append(("recipient_id", "=", recipient_id))
            if payment_state in ("paid", "unpaid"):
                line_domain.append(("payment_state", "=", payment_state))
            lines = self.env["profit.share.line"].search(line_domain)
            result.append(
                {
                    "label": start.strftime("%b %Y"),
                    "pos_revenue": sum(self._company_pos_revenue(company, effective_start, end) for company in companies),
                    "net_profit": sum(self._company_net_profit(company, effective_start, end) for company in companies),
                    "share_amount": sum(lines.mapped("share_amount")),
                }
            )
        return result
