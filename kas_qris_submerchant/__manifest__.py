{
    "name": "KAS QRIS Submerchant",
    "version": "18.0.1.0.0",
    "summary": "Integrasi QRIS Submerchant Winpay",
    "description": "Module QRIS Submerchant + master data Winpay (province, city, merchant type, etc).",
    "author": "Bayu / KAS IT",
    "website": "https://kasprima.co.id",
    "category": "Accounting",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/kas_qris_views.xml",
    ],
    "installable": True,
    "application": False,
}
