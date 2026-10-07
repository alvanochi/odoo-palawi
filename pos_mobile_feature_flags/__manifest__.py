{
    'name': 'POS Mobile Feature Flags',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Dynamic per-POS feature flags for the external Android POS app',
    'description': """
Feature flags for the external Android POS app (POS Palawi).

* Catalog of modules (master flags) and features (unique keys), seeded from the
  default feature plan (Lite / Medium / Enterprise).
* Per POS configuration: choose a plan, then toggle any module/feature.
* REST API ``GET /api/pos/feature-flags/<pos_config_id>`` for the app.
""",
    'depends': ['point_of_sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/feature_data.xml',
        'views/pos_mobile_module_views.xml',
        'views/pos_mobile_feature_views.xml',
        'views/pos_mobile_config_flag_views.xml',
        'views/pos_config_views.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
