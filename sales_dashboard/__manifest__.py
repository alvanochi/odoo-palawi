# -*- coding: utf-8 -*-
{
    "name": "Sales Dashboard",
    "summary": "POS sales dashboard: hour x weekday heatmap, trends, KPI growth, sales tax, top products",
    "description": """
Sales Dashboard
===============

Sales analytics built on paid Point of Sale orders:

* KPI cards (revenue, sales tax, orders, average per order, customers, quantity,
  peak hour) each with growth against the preceding period of equal length
* Hour x weekday heatmap to see when the business is busy
* Revenue and order-count trend charts (hour / day / week / month / year)
* Hourly sales profile
* Sales tax broken down per tax type
* Rankings for products and customers
* Filter by company and outlet (POS config)
* List / pivot / graph views for ad-hoc analysis and export

Orders in state paid, done or invoiced are counted. The transaction timestamp is
the POS order date. All hour and weekday aggregation is converted to the user's
timezone.
    """,
    "author": "Palawi",
    "category": "Point of Sale",
    "version": "18.0.2.0.0",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "account",
        "point_of_sale",
    ],
    "data": [
        "security/sales_dashboard_security.xml",
        "security/ir.model.access.csv",
        "views/sales_report_views.xml",
        "views/sales_dashboard_menus.xml",
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
