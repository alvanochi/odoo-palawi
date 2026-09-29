# -*- coding: utf-8 -*-
{
    "name": "Contact Membership Type",
    "version": "18.0.1.0.0",
    "category": "Contacts",
    "summary": "Master Member Type dengan formula point & redeem, dipakai di Contacts",
    "depends": [
        "contacts",
        "point_of_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/membership_type_views.xml",
        "views/res_partner_views.xml"
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True
}
