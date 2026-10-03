# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Diturunkan dari kategori produk (product.category.is_kitchen), bukan
    # diatur per produk. Nama field tetap sama supaya pemakaian di repository
    # kitchen dan domain antrean tidak perlu diubah.
    is_kitchen = fields.Boolean(
        string='Is Kitchen',
        compute='_compute_is_kitchen',
        store=True,
        readonly=True,
        help='Mengikuti pengaturan "Is Kitchen" pada kategori produk. '
             'Produk tanpa kategori dianggap tampil di dapur.')

    @api.depends('categ_id.is_kitchen')
    def _compute_is_kitchen(self):
        for template in self:
            template.is_kitchen = (
                template.categ_id.is_kitchen if template.categ_id else True)
