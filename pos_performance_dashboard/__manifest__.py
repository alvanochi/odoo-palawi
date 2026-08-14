# -*- coding: utf-8 -*-
{
    'name': 'POS Performance Dashboard',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Dashboard performa Point of Sale: KPI penjualan, grafik tren, '
               'produk terlaris, metode pembayaran, target harian per outlet',
    'description': """
POS Performance Dashboard
=========================
Dashboard analitik untuk Point of Sale.

KPI:
- Total Penjualan, Jumlah Order, Rata-rata per Order
- Item Terjual, Pelanggan Dilayani, Retur
- Target Harian vs Realisasi (progress bar)
- Produk Habis Stok, Sesi Aktif

Grafik:
- Tren penjualan harian
- Penjualan per jam (mengetahui jam sibuk)
- Komposisi metode pembayaran
- Penjualan per outlet
- Penjualan per kategori produk

Tabel:
- Produk terlaris
- Pelanggan teratas
- Kasir / salesperson teratas
- Rincian metode pembayaran
- Sesi POS terakhir
- Produk habis stok

Fitur lain:
- Filter periode cepat (Hari Ini, Kemarin, Minggu Ini, Bulan Ini, Kuartal,
  Tahun Ini) dan rentang tanggal kustom
- Filter dan pencarian outlet berdasarkan nama toko / perusahaan
- Kartu per outlet dengan pencapaian target harian
- KPI dan tabel bisa diklik untuk membuka data detailnya
- Target penjualan harian diatur per POS di Point of Sale > Configuration
""",
    'author': 'Alvano Hastagina',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_performance_dashboard/static/src/scss/dashboard.scss',
            'pos_performance_dashboard/static/src/js/dashboard.js',
            'pos_performance_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
