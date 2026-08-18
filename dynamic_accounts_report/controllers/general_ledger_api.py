import json

from odoo import http
from odoo.http import request


class GeneralLedgerAPI(http.Controller):

    API_KEY = "foomreportkey2026"

    def to_float(self, value):
        if value is None:
            return 0.0

        if isinstance(value, (int, float)):
            return float(value)

        try:
            return float(
                str(value)
                .replace(",", "")
                .strip()
            )
        except Exception:
            return 0.0

    @http.route(
        "/api/accounting/general-ledger",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def get_general_ledger(self, **kwargs):

        try:

            api_key = request.httprequest.headers.get(
                "X-API-KEY"
            )

            if api_key != self.API_KEY:
                return request.make_json_response(
                    {
                        "success": False,
                        "message": "Invalid API Key"
                    },
                    status=401
                )

            body = {}

            if request.httprequest.data:
                body = json.loads(
                    request.httprequest.data.decode("utf-8")
                )

            start_date = body.get("start_date")
            end_date = body.get("end_date")

            company_id = body.get("company_id")

            if company_id:
                company_id = int(company_id)
            else:
                company_id = request.env.company.id

            company = request.env[
                "res.company"
            ].sudo().browse(company_id)

            report = (
                request.env[
                    "account.general.ledger"
                ]
                .sudo()
                .with_company(company)
                .with_context(
                    allowed_company_ids=[company.id],
                    company_id=company.id,
                )
            )

            print(
                "GL COMPANY",
                company.id,
                report.env.context.get(
                    "allowed_company_ids"
                )
            )

            result = report.get_filter_values(
                journal_id=body.get(
                    "journal_ids",
                    []
                ),
                date_range={
                    "start_date": start_date,
                    "end_date": end_date,
                },
                options=body.get(
                    "options",
                    {}
                ),
                analytic=body.get(
                    "analytic_ids",
                    []
                ),
                method=body.get(
                    "method",
                    {}
                )
            )

            totals = result.pop(
                "account_totals",
                {}
            )

            result.pop(
                "journal_ids",
                None
            )

            result.pop(
                "analytic_ids",
                None
            )

            accounts = []

            for account_name, lines in result.items():

                account_total = totals.get(
                    account_name,
                    {}
                )

                running_balance = 0
                formatted_lines = []

                for row in lines:

                    move = (
                        row[0]
                        if isinstance(row, list)
                        else row
                    )

                    debit = self.to_float(
                        move.get("debit")
                    )

                    credit = self.to_float(
                        move.get("credit")
                    )

                    running_balance += (
                        debit - credit
                    )

                    formatted_lines.append({
                        "id":
                            move.get("id"),

                        "date":
                            move.get("date"),

                        "move_name":
                            move.get("move_name"),

                        "communication":
                            move.get("name"),

                        "partner":
                            move["partner_id"][1]
                            if move.get("partner_id")
                            else None,

                        "journal":
                            move["journal_id"][1]
                            if move.get("journal_id")
                            else None,

                        "debit":
                            debit,

                        "credit":
                            credit,

                        "balance":
                            running_balance,
                    })

                accounts.append({
                    "account_id":
                        account_total.get(
                            "account_id"
                        ),

                    "account_name":
                        account_name,

                    "currency":
                        account_total.get(
                            "currency_id"
                        ),

                    "total_debit":
                        self.to_float(
                            account_total.get(
                                "total_debit"
                            )
                        ),

                    "total_credit":
                        self.to_float(
                            account_total.get(
                                "total_credit"
                            )
                        ),

                    "balance":
                        self.to_float(
                            account_total.get(
                                "total_debit"
                            )
                        )
                        -
                        self.to_float(
                            account_total.get(
                                "total_credit"
                            )
                        ),

                    "lines":
                        formatted_lines
                })

            return request.make_json_response({
                "success": True,
                "filters": {
                    "start_date":
                        start_date,
                    "end_date":
                        end_date,
                    "company_id":
                        company.id,
                    "company_name":
                        company.name,
                },
                "accounts": accounts
            })

        except Exception as e:

            import traceback

            return request.make_json_response(
                {
                    "success": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                },
                status=500
            )