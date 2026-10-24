# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosCustomerDisplayBanner(models.Model):
    _name = 'pos.customer.display.banner'
    _description = 'POS Customer Display Banner'
    _order = 'sequence, id'

    name = fields.Char(string='Nama Banner', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string='Urutan', default=10)
    image = fields.Image(
        string='Gambar Banner', required=True, attachment=True,
        max_width=1920, max_height=1080,
    )
    duration = fields.Integer(
        string='Durasi (detik)', default=5,
        help='Lama banner ditampilkan sebelum pindah ke banner berikutnya.',
    )
    pos_config_ids = fields.Many2many(
        'pos.config',
        'pos_customer_display_banner_pos_config_rel',
        'banner_id', 'pos_config_id',
        string='POS',
        help='Kosongkan untuk menampilkan banner ini di semua POS.',
    )
    date_start = fields.Datetime(string='Mulai Tayang')
    date_end = fields.Datetime(string='Selesai Tayang')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('duration_positive', 'CHECK(duration > 0)',
         'Durasi harus lebih dari 0 detik.'),
    ]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(
                    _('Tanggal selesai tayang tidak boleh sebelum tanggal mulai.'))

    @api.model
    def _get_active_banners(self, pos_config):
        """Banner yang sedang tayang untuk sebuah pos.config.

        Aturan:
        - active = True
        - jadwal: date_start kosong / <= sekarang, date_end kosong / >= sekarang
        - POS: pos_config_ids kosong (semua POS) atau berisi pos_config tsb
        - company: company banner kosong atau sama dengan company POS
        """
        now = fields.Datetime.now()
        domain = [
            ('active', '=', True),
            '|', ('date_start', '=', False), ('date_start', '<=', now),
            '|', ('date_end', '=', False), ('date_end', '>=', now),
            '|', ('pos_config_ids', '=', False),
                 ('pos_config_ids', 'in', pos_config.id),
            '|', ('company_id', '=', False),
                 ('company_id', '=', pos_config.company_id.id),
        ]
        return self.search(domain)
