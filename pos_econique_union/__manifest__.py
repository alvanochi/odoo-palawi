{
    "name": "POS Union Econique Integration",
    "summary": "Send paid POS orders to the Union Kuliner Econique API (configurable per POS config)",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "author": "Alvan",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "mail"],
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
