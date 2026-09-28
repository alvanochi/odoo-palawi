# -*- coding: utf-8 -*-
{
    'name': 'Company POS Configuration',
    'version': '1.0',
    'summary': 'Configure POS settings and preferences on res.company',
    'category': 'Point of Sale',
    'author': 'Antigravity Pair-Programmer',
    'depends': ['base', 'hr', 'loyalty'],
    'data': [
        'views/res_company_views.xml',
    ],
    'external_dependencies': {
        'python': ['jwt'],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
