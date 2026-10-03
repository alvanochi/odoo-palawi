# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # Default True: kategori yang sudah ada tetap tampil di dapur sampai
    # dimatikan secara sengaja, bukan diam-diam hilang saat upgrade.
    is_kitchen = fields.Boolean(
        string='Is Kitchen',
        default=True,
        help='Jika dicentang, produk di kategori ini muncul di layar dapur '
             '(Kitchen Display). Matikan untuk kategori yang tidak perlu '
             'diproses dapur, misalnya minuman kemasan, barang retail, atau '
             'diskon/promo.')
