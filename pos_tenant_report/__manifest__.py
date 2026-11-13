{
    'name': 'POS Tenant Transaction Report',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Per-transaction POS report with PB1 / PNBP breakdown, viewable in Odoo and downloadable as Excel',
    'description': """
POS Tenant Transaction Report
=============================

Point of Sale > Reporting > Laporan Transaksi Tenant.

One row per paid POS order with: klaster (parent company), lokasi (company),
tenant (POS config), kasir, customer, transaction number/date/time, payment
methods, gross, discount, handling fee, PB1, PNBP, total tax, revenue,
payment date, revenue minus PB1, and netto.

* PB1 and PNBP come from the Odoo taxes on each order line, classified by
  tax name: PBJT/PB1 -> PB1, PNBP -> PNBP.
* View the result in a list (filter, group by, totals) or download a
  formatted .xlsx.
""",
    'author': 'Palawi',
    'depends': ['point_of_sale', 'account'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'views/pos_tenant_report_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
