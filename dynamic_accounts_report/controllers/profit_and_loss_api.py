import json
import traceback

from odoo import http
from odoo.http import request


class ProfitLossAPI(http.Controller):

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

    def normalize_accounts(self, accounts):
        result = []

        for row in accounts:
            result.append({
                "name": row.get("name"),
                "amount": self.to_float(
                    row.get("amount")
                )
            })

        return result

    @http.route(
        "/api/accounting/profit-loss",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def profit_loss(self, **kwargs):

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

            company = request.env["res.company"].sudo().browse(
                company_id
            )

            if not company.exists():
                return request.make_json_response(
                    {
                        "success": False,
                        "message": "Company not found"
                    },
                    status=404
                )

            report_env = (
                request.env["dynamic.balance.sheet.report"]
                .sudo()
                .with_company(company)
                .with_context(
                    allowed_company_ids=[company.id],
                    company_id=company.id,
                )
            )

            report = report_env.create({
                "target_move": "posted",
                "company_id": company.id,
            })

            vals = {}

            if start_date:
                vals["date_from"] = start_date

            if end_date:
                vals["date_to"] = end_date

            if vals:
                report.write(vals)

            data, _, _ = report.view_report(
                report.id,
                False,
                False
            )
            
            
            print(
                "INCOME SAMPLE =",
                data.get("income", [])[0][:3]
                if data.get("income")
                else []
            )
            

            return request.make_json_response({
                "success": True,
                "filters": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "company_id": company.id,
                    "company_name": company.name,
                },
                "summary": {
                    "net_profit": self.to_float(
                        data.get("total")
                    ),
                    "total_income": self.to_float(
                        data.get("total_income")
                    ),
                    "total_expense": self.to_float(
                        data.get("total_expense")
                    ),
                },
                "sections": {
                    "operating_income": self.normalize_accounts(
                        data.get("income", [])[0]
                        if data.get("income")
                        else []
                    ),
                    "cost_of_revenue": self.normalize_accounts(
                        data.get("expense_direct_cost", [])[0]
                        if data.get("expense_direct_cost")
                        else []
                    ),
                    "other_income": self.normalize_accounts(
                        data.get("income_other", [])[0]
                        if data.get("income_other")
                        else []
                    ),
                    "expense": self.normalize_accounts(
                        data.get("expense", [])[0]
                        if data.get("expense")
                        else []
                    ),
                    "depreciation": self.normalize_accounts(
                        data.get("expense_depreciation", [])[0]
                        if data.get("expense_depreciation")
                        else []
                    ),
                }
            })

        except Exception as e:

            return request.make_json_response(
                {
                    "success": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
                status=500,
            )