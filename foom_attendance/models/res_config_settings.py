# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .foom_attendance_location import GEOFENCE_POLICY
from .utils import PARAM_PREFIX


def _p(name):
    return PARAM_PREFIX + name


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Catatan: default di bawah sengaja sama dengan `utils.DEFAULTS`, yaitu
    # keadaan yang berlaku saat parameter tidak ada di database. Odoo menghapus
    # parameter ketika checkbox dimatikan / angka diisi 0, jadi kalau default di
    # sini berbeda, tampilan setting akan berbohong soal perilaku sebenarnya.
    foom_att_public_enabled = fields.Boolean(
        string='Halaman Absensi Publik', config_parameter=_p('public_enabled'), default=False)
    foom_att_default_radius_m = fields.Integer(
        string='Radius Default (m)', config_parameter=_p('default_radius_m'), default=150)
    foom_att_default_geofence_policy = fields.Selection(
        GEOFENCE_POLICY, string='Kebijakan Geofence Default',
        config_parameter=_p('default_geofence_policy'), default='block')
    foom_att_max_gps_accuracy_m = fields.Integer(
        string='Akurasi GPS Maksimum (m)', config_parameter=_p('max_gps_accuracy_m'), default=0,
        help="Punch ditolak kalau perangkat melaporkan akurasi lebih buruk dari ini. "
             "Isi 0 untuk tidak mengecek.")
    foom_att_single_clock_in_per_day = fields.Boolean(
        string='Satu Absensi per Hari', config_parameter=_p('single_clock_in_per_day'),
        default=False,
        help="Setelah clock in dan clock out, employee tidak bisa clock in lagi di hari "
             "kerja yang sama. Untuk shift lintas hari, batasnya mengikuti jendela shift "
             "— bukan tengah malam.")
    foom_att_require_photo = fields.Boolean(
        string='Minta Foto Selfie', config_parameter=_p('require_photo'), default=False,
        help="Halaman absensi menyalakan kamera depan dan meminta employee memotret diri. "
             "Kalau kamera gagal dipakai, absensi TETAP diterima tapi barisnya ditandai "
             "'Foto Tidak Ada' beserta alasannya.")
    foom_att_require_reason_outside = fields.Boolean(
        string='Wajib Alasan di Luar Radius', config_parameter=_p('require_reason_outside'),
        default=False)
    foom_att_allow_without_roster = fields.Boolean(
        string='Izinkan Tanpa Roster', config_parameter=_p('allow_without_roster'), default=False,
        help="Kalau dimatikan, employee tanpa baris roster / shift default tidak bisa punch.")
    foom_att_session_minutes = fields.Integer(
        string='Umur Sesi (menit)', config_parameter=_p('session_minutes'), default=720)
    foom_att_pin_max_attempts = fields.Integer(
        string='Maks. Salah PIN', config_parameter=_p('pin_max_attempts'), default=5)
    foom_att_pin_lockout_minutes = fields.Integer(
        string='Lama Kunci (menit)', config_parameter=_p('pin_lockout_minutes'), default=15)
    foom_att_ip_max_attempts = fields.Integer(
        string='Maks. Percobaan per IP', config_parameter=_p('ip_max_attempts'), default=30)
    foom_att_ip_window_minutes = fields.Integer(
        string='Jendela IP (menit)', config_parameter=_p('ip_window_minutes'), default=15)
    foom_att_min_punch_interval_sec = fields.Integer(
        string='Jeda Antar Punch (detik)', config_parameter=_p('min_punch_interval_sec'),
        default=0, help="0 = tanpa jeda.")

    foom_att_public_url = fields.Char(string='URL Halaman', compute='_compute_public_url')

    @api.depends('foom_att_public_enabled')
    def _compute_public_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec.foom_att_public_url = '%s/foom/attendance' % (base or '')
