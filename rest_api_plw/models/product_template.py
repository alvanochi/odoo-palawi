# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Default True: tanpa ini, meng-upgrade modul akan membuat SELURUH produk
    # yang sudah ada hilang dari layar dapur sampai dicentang satu per satu.
    # Yang perlu dilakukan staf hanya MENGOSONGKAN checkbox pada produk yang
    # memang tidak perlu dapur -- air mineral kemasan, kopi sachet, barang
    # retail -- bukan menyalakannya kembali untuk semua yang lain.
    is_kitchen = fields.Boolean(
        string='Is Kitchen',
        default=True,
        help='Jika dicentang, pesanan produk ini muncul di layar dapur '
             '(Kitchen Display). Kosongkan untuk produk yang tidak perlu '
             'diproses dapur, misalnya air mineral kemasan atau barang '
             'retail -- baris seperti itu tidak akan pernah ditandai '
             'selesai oleh siapa pun, dan akan menahan tiket di layar dapur '
             'selamanya kalau tetap dihitung sebagai hidangan.')
