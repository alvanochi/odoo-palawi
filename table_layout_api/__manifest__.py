{
    'name': 'Table Layout API',
    'version': '18.0.1.1.1',
    'summary': 'Read-only REST API exposing the POS Table/Floor layout (geometry + live occupancy + SVG render)',
    'description': (
        "Lets an external application fetch the exact POS Floor Plan layout "
        "(floors, tables, geometry, live occupancy) over a plain, API-key-"
        "authenticated REST call -- instead of through Odoo's session-based "
        "JSON-RPC web client API. Also renders any one floor as a ready-to-"
        "display SVG image. See README.md."
    ),
    'author': 'Alvano Hastagina',
    'category': 'Point of Sale',
    'license': 'LGPL-3',
    'depends': ['base', 'point_of_sale', 'pos_restaurant'],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
