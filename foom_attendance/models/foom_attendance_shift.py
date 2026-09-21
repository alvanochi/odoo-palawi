# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import utils


class FoomAttendanceShift(models.Model):
    _name = 'foom.attendance.shift'
    _description = 'Shift Absensi'
    _order = 'sequence, time_from, name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(help="Kode singkat, mis. P1, P2, MALAM.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)

    time_from = fields.Float(
        string='Jam Masuk', required=True, default=8.0,
        help="Jam lokal employee, format desimal (8.5 = 08:30).")
    time_to = fields.Float(
        string='Jam Pulang', required=True, default=17.0,
        help="Jam lokal employee. Kalau lebih kecil / sama dengan jam masuk, "
             "shift dianggap lintas hari.")
    is_overnight = fields.Boolean(
        string='Lintas Hari', compute='_compute_is_overnight', store=True)
    duration_hours = fields.Float(
        string='Durasi', compute='_compute_is_overnight', store=True)

    grace_in_minutes = fields.Integer(
        string='Toleransi Telat (menit)', default=10,
        help="Clock in dalam rentang toleransi ini tidak dihitung telat.")
    grace_out_minutes = fields.Integer(
        string='Toleransi Pulang Cepat (menit)', default=0)
    early_in_window_minutes = fields.Integer(
        string='Boleh Clock In Sebelum (menit)', default=60,
        help="Seberapa awal sebelum jam masuk halaman absensi mau menerima clock in.")
    late_out_window_minutes = fields.Integer(
        string='Boleh Clock Out Sampai (menit)', default=240,
        help="Seberapa lama setelah jam pulang halaman absensi masih menerima clock out.")
    enforce_window = fields.Boolean(
        string='Tolak di Luar Jendela', default=False,
        help="Kalau aktif, punch di luar jendela waktu shift ditolak. Kalau tidak, "
             "punch tetap dicatat tapi ditandai di luar jadwal.")

    location_ids = fields.Many2many(
        'foom.attendance.location', 'foom_att_shift_location_rel', 'shift_id', 'location_id',
        string='Lokasi yang Diizinkan',
        help="Kalau diisi lebih dari satu, sistem memakai lokasi terdekat dari posisi employee.")
    default_location_id = fields.Many2one(
        'foom.attendance.location', string='Lokasi Utama',
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]")
    roster_ids = fields.One2many('foom.attendance.roster', 'shift_id', string='Roster')

    # ------------------------------------------------------------------
    @api.depends('time_from', 'time_to')
    def _compute_is_overnight(self):
        for rec in self:
            rec.is_overnight = rec.time_to <= rec.time_from
            span = rec.time_to - rec.time_from
            rec.duration_hours = span + 24.0 if span <= 0 else span

    @api.constrains('time_from', 'time_to')
    def _check_times(self):
        for rec in self:
            for value in (rec.time_from, rec.time_to):
                if not (0.0 <= value < 24.0):
                    raise ValidationError(
                        _("Jam shift harus di antara 0.0 dan 23.99 (waktu lokal employee)."))

    @api.constrains('default_location_id', 'location_ids')
    def _check_default_location(self):
        for rec in self:
            if rec.default_location_id and rec.location_ids \
                    and rec.default_location_id not in rec.location_ids:
                raise ValidationError(
                    _("Lokasi Utama harus termasuk dalam daftar Lokasi yang Diizinkan."))

    @api.depends('name', 'time_from', 'time_to')
    def _compute_display_name(self):
        for rec in self:
            h1, m1 = utils.float_to_hm(rec.time_from)
            h2, m2 = utils.float_to_hm(rec.time_to)
            rec.display_name = '%s (%02d:%02d–%02d:%02d)' % (rec.name or '', h1, m1, h2, m2)

    # ------------------------------------------------------------------
    def allowed_locations(self):
        """Lokasi yang boleh dipakai shift ini (bisa kosong)."""
        self.ensure_one()
        return self.location_ids or self.default_location_id

    def window_utc(self, day, tz):
        """(planned_in, planned_out) sebagai datetime UTC naive untuk tanggal lokal `day`."""
        self.ensure_one()
        start = utils.local_naive_to_utc(day, self.time_from, tz)
        end_day = day + timedelta(days=1) if self.is_overnight else day
        end = utils.local_naive_to_utc(end_day, self.time_to, tz)
        if end <= start:
            end += timedelta(days=1)
        return start, end

    def punch_window_utc(self, day, tz):
        """Jendela yang lebih longgar: kapan halaman absensi menerima punch."""
        self.ensure_one()
        start, end = self.window_utc(day, tz)
        return (start - timedelta(minutes=self.early_in_window_minutes or 0),
                end + timedelta(minutes=self.late_out_window_minutes or 0))
