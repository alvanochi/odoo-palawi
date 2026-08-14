# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    daily_sales_target = fields.Monetary(
        string='Target Penjualan Harian', currency_field='currency_id',
        help='Target penjualan per hari untuk outlet ini. Dipakai dashboard '
             'untuk menghitung persentase pencapaian pada periode terpilih '
             '(target periode = target harian x jumlah hari).')
