{
    'name': 'Scrap Attachment Required',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Scrap orders need at least one attachment before they can be validated',
    'description': """
Adds an Attachments field to Scrap Orders (Inventory and Manufacturing) and
blocks Validate until at least one file is attached, either in that field or
in the chatter.

Code that must validate scraps without a file can pass the context key
``skip_scrap_attachment_check=True``.
""",
    'author': 'Palawi',
    'depends': ['stock'],
    'data': [
        'views/stock_scrap_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
