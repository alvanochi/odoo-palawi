# -*- coding: utf-8 -*-
{
    'name': 'REST API Palawi (PLW)',
    'version': '1.2.0',
    'summary': 'Palawi Odoo REST API using Clean Architecture',
    'description': """
        Clean Architecture implementation of Odoo REST APIs for the Palawi Project.
        Endpoints:
        - POST /api/auth/login        -> login using email (SSO)
        - POST /api/employee/login    -> standard employee login
        - GET /api/company/pos_config  -> POS configuration context
        - POST /api/loyalty/promotions -> Loyalty program matches
        - POST /api/auth/otp/request   -> Request OTP for employee
        - POST /api/auth/otp/verify    -> Verify OTP and complete login
        - POST /api/pos/order/refund    -> Refund a paid POS order with selected payment method
    """,
    'category': 'Technical',
    'author': 'HKR',
    # pos_order_extra_states sengaja TIDAK didaftarkan di sini. Modul itu hanya
    # menambah fitur dapur: setiap pemakaiannya sudah dijaga getattr/hasattr,
    # dan filter kitchen_state otomatis dilewati bila fieldnya tidak ada.
    #
    # Dengan dependensi, mencabut modul dapur akan ikut mencabut seluruh API
    # ini -- yang sudah terjadi sekali dan mematikan semua endpoint sekaligus.
    'depends': [
        'base', 'hr', 'bus', 'point_of_sale', 'pos_restaurant', 'pos_category_company', 'loyalty', 'pos_loyalty', 'product_estimated_time',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/res_company_views.xml',
        'views/restaurant_floor_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
