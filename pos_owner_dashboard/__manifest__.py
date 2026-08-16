{
    "name": "POS Owner Dashboard",
    "version": "1.0",
    "category": "Point of Sale",
    "summary": "Dashboard untuk Owner Restoran dengan metrik POS",
    "description": """
        Modul dashboard untuk owner restoran yang menampilkan:
        - Ringkasan penjualan harian
        - Metrik keuangan (margin, diskon)
        - Analisis produk terlaris
        - Analisis pelanggan
        - Metrik operasional (order per jam, per kasir)
    """,
    "author": "HKR",
    "depends": [
        "base",
        "point_of_sale",
        "pos_restaurant",
        "rest_api_odoo",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_owner_dashboard_views.xml",
    ],
    "assets": {},
    "application": True,
    "installable": True,
    "license": "LGPL-3",
}
