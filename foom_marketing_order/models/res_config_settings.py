# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Disimpan ke ir.config_parameter dengan key yang SAMA seperti sebelumnya,
    # jadi kode lama yang membaca parameter ini tidak perlu diubah.
    mkt_sample_location_id = fields.Many2one(
        'stock.location',
        string='Lokasi Sample',
        domain="[('usage', 'in', ['inventory', 'internal'])]",
        config_parameter='foom_marketing_order.sample_location_id',
        help="Lokasi tujuan untuk pengeluaran barang Marketing Order. "
             "Biasanya lokasi Inventory Loss bernama 'Sample'. "
             "Lokasi ini yang dipakai sebagai Destination Location pada "
             "Delivery Order yang dibuat saat Marketing Order di-Confirm.")

    mkt_sample_location_kmi_id = fields.Many2one(
        'stock.location',
        string='Lokasi Sample (KMI)',
        domain="[('usage', 'in', ['inventory', 'internal'])]",
        config_parameter='foom_marketing_order.sample_location_id_kmi',
        help="Cadangan untuk company KMI. Saat ini belum dipakai oleh proses "
             "Confirm, disediakan supaya nilainya bisa dikelola dari sini.")

    @api.constrains('mkt_sample_location_id')
    def _check_mkt_sample_location(self):
        for rec in self:
            loc = rec.mkt_sample_location_id
            if loc and not loc.exists():
                raise ValidationError("Lokasi Sample yang dipilih sudah tidak ada.")
