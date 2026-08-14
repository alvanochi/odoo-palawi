# -*- coding: utf-8 -*-
{
    'name': 'Product Estimated Time',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Estimated Time field (in minutes) on products for '
               'countdown in POS clients / external integrations',
    'description': """
Product Estimated Time
======================
Adds an integer "Estimated Time" field (in minutes) on product.template
(automatically available on product.product as well).

The field is also loaded into the Point of Sale data
(_load_pos_data_fields) so POS clients or third-party integrations can
read the preparation time estimate for countdowns, then move the order
state once the time runs out.
""",
    'author': 'Alvano Hastagina',
    'depends': ['point_of_sale'],
    'data': [
        'views/product_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
