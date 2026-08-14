# -*- coding: utf-8 -*-
{
    'name': 'POS Product Schedule',
    'version': '18.0.2.0.0',
    'category': 'Point of Sale',
    'summary': 'Show products in the POS only during set hours and days, '
               'for example a breakfast menu from 09:00 to 12:00',
    'description': """
POS Product Schedule
====================
Drives product availability in the Point of Sale from a form instead of a
hand written scheduled action.

How it works
------------
Every schedule owns two scheduled actions, created automatically:
one fires daily at the start time and shows the products, the other
fires daily at the end time and hides them. Both are normal scheduled
actions, visible under Settings > Technical > Scheduled Actions, where
they can also be run manually.

Features:
- Pick products by name or barcode
- Set a start and an end time, including windows crossing midnight
- Pick the active days, Monday to Sunday
- Per schedule timezone
- Saving a schedule applies it immediately and refreshes its triggers
- "Apply Now" button for testing without waiting
- "Running Now" indicator, plus next show and next hide timestamps
- Hourly safety check in case a trigger is missed
""",
    'author': 'Alvano Hastagina',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/pos_product_schedule_cron.xml',
        'views/pos_product_schedule_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
