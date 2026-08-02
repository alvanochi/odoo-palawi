# -*- coding: utf-8 -*-
{
    'name': 'Kontrak Mitra / Tenant',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Pendaftaran kontrak mitra/tenant dengan biaya flat atau '
               'persentase, penagihan bulanan atau tahunan',
    'description': """
Manajemen Kontrak Mitra / Tenant
================================
- Pendaftaran kontrak untuk mitra atau tenant
- Biaya kontrak: Flat (nominal tetap) atau Persentase (dari omzet/dasar perhitungan)
- Periode penagihan: Bulanan atau Tahunan
- Pembuatan tagihan (customer invoice) manual lewat tombol atau otomatis via cron harian
- Daftar kontrak terdaftar dengan status pembayaran (Lunas / Belum Lunas / Belum Ada Tagihan)
- Daftar tagihan kontrak dengan status pembayarannya
""",
    'author': 'Alvano Hastagina',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/contract_sequence.xml',
        'data/contract_product.xml',
        'data/contract_cron.xml',
        'views/partner_contract_views.xml',
        'views/account_move_views.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
