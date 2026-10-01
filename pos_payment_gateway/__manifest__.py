{
    "name": "POS Payment Gateway",
    "summary": "Kelola credential payment gateway (Paper.id, dll) per POS config + API get by pos_config_id",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "mail"],
    "data": [
        "security/pos_payment_gateway_security.xml",
        "security/ir.model.access.csv",
        "data/pos_payment_gateway_data.xml",
        "views/pos_payment_gateway_views.xml",
    ],
    "installable": True,
    "application": False,
}
