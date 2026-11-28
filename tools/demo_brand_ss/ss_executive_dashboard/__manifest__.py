{
    'name': 'SS Executive Dashboard (Demo)',
    'version': '18.0.1.0.0',
    'summary': 'Executive dashboard Brand SS: penjualan, keuangan, operasional, marketing, HR & alert keputusan',
    'category': 'Productivity',
    'author': 'Demo',
    'license': 'LGPL-3',
    'depends': ['web', 'sale_management', 'account', 'stock', 'purchase', 'mrp', 'hr_attendance', 'project'],
    'data': ['views/menu.xml'],
    'assets': {
        'web.assets_backend': [
            'ss_executive_dashboard/static/src/dashboard.scss',
            'ss_executive_dashboard/static/src/dashboard.js',
            'ss_executive_dashboard/static/src/dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
}
