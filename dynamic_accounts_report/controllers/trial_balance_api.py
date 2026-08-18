import json

from odoo import http
from odoo.http import request


class TrialBalanceAPI(http.Controller):

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
        "/api/accounting/trial-balance",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def get_trial_balance(self, **kwargs):

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
                    "account.trial.balance"
                ]
                .sudo()
                .with_company(company)
                .with_context(
                    allowed_company_ids=[company.id],
                    company_id=company.id,
                )
            )

            print(
                "TB COMPANY",
                company.id,
                report.env.context.get(
                    "allowed_company_ids"
                )
            )

            data, totals = report.get_filter_values(
                start_date=start_date,
                end_date=end_date,
                comparison_number=body.get(
                    "comparison_number"
                ),
                comparison_type=body.get(
                    "comparison_type"
                ),
                journal_list=body.get(
                    "journal_ids",
                    []
                ),
                analytic=body.get(
                    "analytic_ids",
                    []
                ),
                options=body.get(
                    "options",
                    {}
                ),
                method=body.get(
                    "method",
                    {}
                )
            )

            accounts = []

            for row in data:

                accounts.append({
                    "account_id":
                        row.get("account_id"),

                    "account_name":
                        row.get("account"),

                    "initial_debit":
                        self.to_float(
                            row.get(
                                "initial_total_debit"
                            )
                        ),

                    "initial_credit":
                        self.to_float(
                            row.get(
                                "initial_total_credit"
                            )
                        ),

                    "period_debit":
                        self.to_float(
                            row.get(
                                "total_debit"
                            )
                        ),

                    "period_credit":
                        self.to_float(
                            row.get(
                                "total_credit"
                            )
                        ),

                    "ending_debit":
                        self.to_float(
                            row.get(
                                "end_total_debit"
                            )
                        ),

                    "ending_credit":
                        self.to_float(
                            row.get(
                                "end_total_credit"
                            )
                        )
                })

            normalized_totals = {}

            if isinstance(totals, dict):

                for key, value in totals.items():

                    normalized_totals[key] = (
                        self.to_float(value)
                        if isinstance(
                            value,
                            (str, int, float)
                        )
                        else value
                    )

            return request.make_json_response({
                "success": True,
                "filters": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "company_id": company.id,
                    "company_name": company.name,
                },
                "accounts": accounts,
                "totals": normalized_totals
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