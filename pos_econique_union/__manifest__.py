{
    "name": "POS Union Econique Integration",
    "summary": "Kirim transaksi POS lunas ke API Union Kuliner Econique (credential per POS, bisa dikonfigurasi)",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "author": "Alvan",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "pos_payment_gateway"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/pos_econique_security.xml",
        "security/ir.model.access.csv",
        "data/pos_econique_data.xml",
        "views/pos_econique_views.xml",
    ],
    "installable": True,
    "application": False,
}
