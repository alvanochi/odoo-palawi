# -*- coding: utf-8 -*-
{
    'name': 'POS Customer Display Banner',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'CRUD banner untuk customer display POS + API per POS config',
    'description': """
POS Customer Display Banner
===========================
* CRUD banner (gambar, urutan, durasi, jadwal tayang) di menu Point of Sale > Configuration.
* Banner bisa dibatasi ke POS config tertentu (kosong = tampil di semua POS).
* API GET banner aktif berdasarkan pos_config_id untuk dipakai customer display.
    """,
    'author': 'Buitentech',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'security/pos_customer_display_banner_security.xml',
        'views/pos_customer_display_banner_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
