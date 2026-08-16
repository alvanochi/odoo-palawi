{
    "name": "Profit Sharing",
    "summary": "Profit and fee sharing rules, periodic computation, audit trail, and dashboards",
    "description": """
Profit Sharing provides configurable sharing rules for partners and staff,
periodic calculation from POS revenue or accounting net profit, immutable audit
snapshots, approval/payment workflows, management dashboards, and recipient portal access.
""",
    "version": "18.0.1.0.9",
    "category": "Accounting/Accounting",
    "author": "Alvano Hastagina",
    "license": "LGPL-3",
    "depends": [
        "base_setup",
        "mail",
        "portal",
        "point_of_sale",
        "account",
        "web",
    ],
    "data": [
        "security/profit_sharing_groups.xml",
        "security/ir.model.access.csv",
        "security/profit_sharing_security.xml",
        "data/profit_share_type_data.xml",
        "data/ir_sequence.xml",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/profit_share_type_views.xml",
        "views/profit_share_rule_views.xml",
        "views/profit_share_line_views.xml",
        "views/profit_share_computation_views.xml",
        "views/profit_share_compute_wizard_views.xml",
        "views/profit_share_dashboard_action.xml",
        "views/portal_templates.xml",
        "views/profit_share_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "profit_sharing/static/src/scss/dashboard.scss",
            "profit_sharing/static/src/js/dashboard.js",
            "profit_sharing/static/src/xml/dashboard.xml",
        ],
    },
    "application": True,
    "installable": True,
}
