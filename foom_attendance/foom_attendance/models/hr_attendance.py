# -*- coding: utf-8 -*-
from odoo import api, fields, models

from . import utils

SOURCE = [
    ('backend', 'Backend'),
    ('public', 'Halaman Publik'),
]

#: Status foto selfie. Satu field menyimpan sekaligus alasan kegagalannya,
#: supaya HR bisa membedakan "izin kamera ditolak" (patut dipertanyakan) dari
#: "perangkat memang tidak punya kamera".
PHOTO_STATUS = [
    ('not_required', 'Tidak diminta'),
    ('captured', 'Terambil'),
    ('denied', 'Izin kamera ditolak'),
    ('no_camera', 'Perangkat tanpa kamera'),
    ('insecure', 'Bukan HTTPS'),
    ('failed', 'Gagal diambil'),
]

#: status yang berarti foto diminta tapi tidak didapat
PHOTO_MISSING = ('denied', 'no_camera', 'insecure', 'failed')


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    foom_source = fields.Selection(SOURCE, string='Sumber', default='backend', readonly=True)
    foom_shift_id = fields.Many2one('foom.attendance.shift', string='Shift', readonly=True)
    foom_roster_id = fields.Many2one('foom.attendance.roster', string='Roster', readonly=True)
    foom_work_date = fields.Date(
        string='Hari Kerja', readonly=True, index=True,
        help="Tanggal shift yang menaungi absensi ini. Untuk shift lintas hari, "
             "clock in 22:00 dan clock out 06:00 keesokan harinya memakai tanggal "
             "yang sama. Dipakai untuk membatasi satu absensi per hari.")

    foom_in_location_id = fields.Many2one(
        'foom.attendance.location', string='Lokasi Masuk', readonly=True)
    foom_out_location_id = fields.Many2one(
        'foom.attendance.location', string='Lokasi Pulang', readonly=True)
    foom_in_distance_m = fields.Float(
        string='Jarak Masuk (m)', digits=(10, 1), readonly=True, aggregator=None)
    foom_out_distance_m = fields.Float(
        string='Jarak Pulang (m)', digits=(10, 1), readonly=True, aggregator=None)
    foom_in_accuracy_m = fields.Float(
        string='Akurasi GPS Masuk (m)', digits=(10, 1), readonly=True, aggregator=None)
    foom_out_accuracy_m = fields.Float(
        string='Akurasi GPS Pulang (m)', digits=(10, 1), readonly=True, aggregator=None)
    foom_in_outside = fields.Boolean(string='Masuk di Luar Radius', readonly=True)
    foom_out_outside = fields.Boolean(string='Pulang di Luar Radius', readonly=True)
    # Tanpa penanda ini, jarak 0.0 pada baris yang geofence-nya dimatikan
    # tidak bisa dibedakan dari "benar-benar berdiri di titik lokasi".
    foom_in_geo_checked = fields.Boolean(string='Posisi Masuk Terukur', readonly=True)
    foom_out_geo_checked = fields.Boolean(string='Posisi Pulang Terukur', readonly=True)
    foom_outside = fields.Boolean(
        string='Di Luar Radius', compute='_compute_foom_outside', store=True)

    foom_planned_in = fields.Datetime(string='Jadwal Masuk', readonly=True)
    foom_planned_out = fields.Datetime(string='Jadwal Pulang', readonly=True)
    foom_late_minutes = fields.Integer(string='Telat (menit)', readonly=True, aggregator='sum')
    foom_early_leave_minutes = fields.Integer(
        string='Pulang Cepat (menit)', readonly=True, aggregator='sum')
    foom_off_schedule = fields.Boolean(string='Di Luar Jadwal', readonly=True)

    foom_in_note = fields.Char(string='Alasan Masuk', readonly=True)
    foom_out_note = fields.Char(string='Alasan Pulang', readonly=True)
    foom_in_photo = fields.Image(string='Foto Masuk', max_width=1024, max_height=1024,
                                 attachment=True, readonly=True)
    foom_out_photo = fields.Image(string='Foto Pulang', max_width=1024, max_height=1024,
                                  attachment=True, readonly=True)
    foom_in_photo_status = fields.Selection(
        PHOTO_STATUS, string='Status Foto Masuk', default='not_required', readonly=True)
    foom_out_photo_status = fields.Selection(
        PHOTO_STATUS, string='Status Foto Pulang', default='not_required', readonly=True)
    foom_photo_missing = fields.Boolean(
        string='Foto Tidak Ada', compute='_compute_foom_photo_missing', store=True,
        help="Foto diminta tapi tidak berhasil diambil. Dipakai HR untuk audit.")

    foom_in_map_url = fields.Char(compute='_compute_foom_map_urls')
    foom_out_map_url = fields.Char(compute='_compute_foom_map_urls')

    # ------------------------------------------------------------------
    @api.depends('foom_in_outside', 'foom_out_outside')
    def _compute_foom_outside(self):
        for rec in self:
            rec.foom_outside = rec.foom_in_outside or rec.foom_out_outside

    @api.depends('foom_in_photo_status', 'foom_out_photo_status')
    def _compute_foom_photo_missing(self):
        for rec in self:
            rec.foom_photo_missing = (rec.foom_in_photo_status in PHOTO_MISSING
                                      or rec.foom_out_photo_status in PHOTO_MISSING)

    @api.model
    def _foom_photo_status(self, has_photo, reported):
        """Petakan alasan yang dilaporkan klien ke salah satu nilai yang dikenal.

        Ini catatan audit, bukan penegakan: klien memang bisa mengarang alasan.
        Yang penting barisnya tetap ditandai 'foto tidak ada', bukan terlihat
        bersih seolah tidak pernah diminta."""
        if has_photo:
            return 'captured'
        known = {code for code, _label in PHOTO_STATUS}
        if reported in known and reported not in ('captured', 'not_required'):
            return reported
        return 'failed'

    @api.depends('in_latitude', 'in_longitude', 'out_latitude', 'out_longitude')
    def _compute_foom_map_urls(self):
        base = 'https://www.google.com/maps?q=%s,%s'
        for rec in self:
            rec.foom_in_map_url = (base % (rec.in_latitude, rec.in_longitude)) \
                if (rec.in_latitude or rec.in_longitude) else False
            rec.foom_out_map_url = (base % (rec.out_latitude, rec.out_longitude)) \
                if (rec.out_latitude or rec.out_longitude) else False

    def action_open_in_map(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.foom_in_map_url, 'target': 'new'}

    def action_open_out_map(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.foom_out_map_url, 'target': 'new'}

    # ------------------------------------------------------------------
    def _foom_write_native_geo(self, prefix, lat, lon, ip, browser):
        """Isi field geolokasi bawaan hr_attendance kalau memang tersedia."""
        vals = {
            '%s_latitude' % prefix: lat or 0.0,
            '%s_longitude' % prefix: lon or 0.0,
            '%s_ip_address' % prefix: (ip or '')[:64],
            '%s_browser' % prefix: (browser or '')[:64],
            '%s_mode' % prefix: 'kiosk',
        }
        return utils.filter_existing_vals(self, vals)

    @api.model
    def _foom_minutes_between(self, later, earlier):
        if not later or not earlier:
            return 0
        return max(0, int(round((later - earlier).total_seconds() / 60.0)))
