{
    "name": "POS Product Add-ons",
    "summary": "Add-on products related to Product Variants for Point of Sale.",
    "description": """
        Allows you to define add-on products (e.g. toppings, extras)
        that are related to each product variant. Only products marked
        as 'Available in POS' can be selected as add-ons.
        Provides an API endpoint for external consumption.
    """,
    "version": "18.0.1.0.0",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "author": "Bayu Faturahman",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
