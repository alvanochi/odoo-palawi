# -*- coding: utf-8 -*-
{
    "name": "FOOM Sales Dashboard",
    "summary": "Sales dashboard: hour x weekday heatmap, trends, KPI growth, top products & outlets",
    "description": """
FOOM Sales Dashboard
====================

Sales analytics built on posted customer invoices and credit notes:

* KPI cards (revenue, orders, average per order, customers, quantity, peak hour)
  each with growth against the preceding period of equal length
* Hour x weekday heatmap to see when the business is busy
* Revenue and order-count trend charts (hour / day / week / month / year)
* Hourly sales profile
* Rankings for products, sales teams (outlets) and customers
* List / pivot / graph views for ad-hoc analysis and export

The transaction timestamp comes from the Sales Order date (date_order) when the
invoice line is linked to an SO, and falls back to the invoice creation time
otherwise. All hour and weekday aggregation is converted to the user's timezone.
    """,
    "author": "FOOM",
    "website": "https://www.foom.id",
    "category": "Sales/Sales",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "account",
        "sale",
        # sale_stock menyediakan `stock.move.sale_line_id`, rantai yang dipakai
        # SQL view untuk mengambil warehouse & location pengiriman sebenarnya.
        "sale_stock",
    ],
    "data": [
        "security/foom_security.xml",
        "security/ir.model.access.csv",
        "views/foom_sales_report_views.xml",
        "views/foom_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sales_dashboard/static/lib/chartjs/chart.umd.js",
            "sales_dashboard/static/src/scss/dashboard.scss",
            "sales_dashboard/static/src/js/dashboard.js",
            "sales_dashboard/static/src/xml/dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
