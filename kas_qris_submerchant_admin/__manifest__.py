# -*- coding: utf-8 -*-
{
    "name": "KAS QRIS Submerchant Admin",
    "version": "18.0.1.0.0",
    "category": "Accounting/Payment",
    "summary": "Admin-only CRUD & sync for QRIS submerchants (Winpay)",
    "author": "KAS IT",
    "license": "LGPL-3",
    "depends": [
    "base",
    "point_of_sale",
    "pos_restaurant",  
],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/merchant_type_extra.xml",
        "views/kas_qris_menus.xml",
        "views/kas_qris_master_views.xml",
        "views/kas_qris_submerchant_views.xml",
        "views/pos_floor_views.xml",
        "views/pos_config_merchant_id.xml",
    ],
    "installable": True,
    "application": False,
}
