from datetime import date

from odoo import fields, http, _
from odoo.http import request
from odoo.tools.misc import format_amount
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class ProfitSharingPortal(CustomerPortal):
    def _profit_share_portal_domain(self):
        return [
            ("recipient_id", "=", request.env.user.partner_id.id),
            ("computation_id.state", "in", ("confirmed", "approved", "paid")),
        ]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "profit_share_count" in counters:
            values["profit_share_count"] = request.env["profit.share.line"].search_count(
                self._profit_share_portal_domain()
            )
        return values

    @staticmethod
    def _totals_by_currency(lines):
        totals = {}
        for line in lines:
            currency = line.currency_id
            totals.setdefault(currency.id, {"currency": currency, "amount": 0.0})
            totals[currency.id]["amount"] += line.share_amount
        return list(totals.values())

    @http.route(["/my/profit-sharing", "/my/profit-sharing/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_profit_sharing(self, page=1, sortby="date", **kw):
        Line = request.env["profit.share.line"]
        domain = self._profit_share_portal_domain()
        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "effective_date_from desc, id desc"},
            "amount": {"label": _("Amount"), "order": "share_amount desc, id desc"},
        }
        sortby = sortby if sortby in searchbar_sortings else "date"
        order = searchbar_sortings[sortby]["order"]
        total = Line.search_count(domain)
        pager = portal_pager(url="/my/profit-sharing", total=total, page=page, step=20, url_args={"sortby": sortby})
        lines = Line.search(domain, order=order, limit=20, offset=pager["offset"])

        today = fields.Date.context_today(Line)
        month_start = today.replace(day=1)
        year_start = date(today.year, 1, 1)
        month_lines = Line.search(
            domain
            + [
                ("effective_date_from", "<=", today),
                ("effective_date_to", ">=", month_start),
            ]
        )
        year_lines = Line.search(
            domain
            + [
                ("effective_date_from", "<=", today),
                ("effective_date_to", ">=", year_start),
            ]
        )
        latest = Line.search(domain, order="effective_date_to desc, id desc", limit=1)

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "profit_sharing",
                "lines": lines,
                "pager": pager,
                "sortby": sortby,
                "searchbar_sortings": searchbar_sortings,
                "default_url": "/my/profit-sharing",
                "month_totals": self._totals_by_currency(month_lines),
                "year_totals": self._totals_by_currency(year_lines),
                "latest_line": latest,
                "format_amount": lambda amount, currency: format_amount(request.env, amount, currency),
            }
        )
        return request.render("profit_sharing.portal_my_profit_sharing", values)
