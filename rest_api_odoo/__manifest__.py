{
    "name": "Odoo rest API",
    "version": "18.0.1.0.1",
    "category": "Tools",
    "summary": """This app helps to interact with odoo, backend with help of 
     rest api requests""",
    "description": """The odoo Rest API module allow us to connect to database 
     with the help of GET , POST , PUT and DELETE requests""",
    'author': 'KAS Prima',
    'company': 'PT Kas Prima',
    'maintainer': 'KAS Prima',
    'website': "https://www.kasprima.co.id",
    "depends": ['base', 'web', 'point_of_sale', 'pos_restaurant'],
    "data": [
        'security/poskas_bill_security.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/connection_api_views.xml',
        'views/poskas_bill_views.xml',
        'views/pos_cash_movement_views.xml',
    ],
    "assets": {
         'point_of_sale._assets_pos': [
                'rest_api_odoo/static/src/xml/pos_waiters.xml',
            ],
            "web.assets_backend": [
                "rest_api_odoo/static/src/bus_poskas_bill_listener.js",
            ],
    },
    'images': ['static/description/banner.jpg'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
