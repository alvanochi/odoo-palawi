{
    'name': 'Menu Visibility',
    'version': '18.0.1.0.0',
    'category': 'Administration',
    'summary': 'Let administrators hide menus per user or group',
    'description': """
Administrators can create rules under Settings > Menu Visibility to hide any
menu (and its sub menus) for everyone, for selected groups, or for selected
users. Administrators (Settings group) are never affected by the rules, so
they cannot lock themselves out.

This hides the menu only; it is not an access-rights control. Use groups and
record rules to restrict data access.
""",
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu_visibility_rule_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
