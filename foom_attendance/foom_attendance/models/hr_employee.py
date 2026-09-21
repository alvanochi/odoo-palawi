# -*- coding: utf-8 -*-
import re
from datetime import timedelta
from random import SystemRandom

from werkzeug.security import check_password_hash, generate_password_hash

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import utils
from .foom_attendance_location import GEOFENCE_POLICY

_random = SystemRandom()

HR_USER = 'hr.group_hr_user'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    foom_att_enabled = fields.Boolean(
        string='Absensi Publik Aktif', default=True, groups=HR_USER, copy=False,
        help="Kalau dimatikan, employee ini tidak bisa clock in/out lewat halaman publik.")
    foom_att_code = fields.Char(
        string='Kode Absensi', groups=HR_USER, copy=False, index=True,
        help="Dipakai untuk login di halaman absensi publik. Kalau kosong, "
             "employee bisa memakai Badge ID (barcode).")
    foom_att_pin_hash = fields.Char(string='PIN Hash', groups=HR_USER, copy=False)
    foom_att_pin_set = fields.Char(
        string='Set PIN Baru', groups=HR_USER, store=False,
        compute='_compute_foom_att_pin_set', inverse='_inverse_foom_att_pin_set',
        help="Ketik PIN baru lalu simpan. Nilainya di-hash dan tidak pernah "
             "disimpan apa adanya.")
    foom_att_pin_isset = fields.Boolean(
        string='PIN Sudah Diatur', compute='_compute_foom_att_pin_isset', groups=HR_USER)
    foom_att_locked_until = fields.Datetime(
        string='Terkunci Sampai', groups=HR_USER, copy=False, readonly=True)

    foom_att_shift_id = fields.Many2one(
        'foom.attendance.shift', string='Shift Default', groups=HR_USER,
        help="Dipakai kalau tidak ada baris roster untuk tanggal tersebut.")
    foom_att_location_id = fields.Many2one(
        'foom.attendance.location', string='Lokasi Default', groups=HR_USER)
    foom_att_geofence_policy = fields.Selection(
        GEOFENCE_POLICY + [], string='Override Geofence', groups=HR_USER,
        help="Kosongkan untuk memakai kebijakan dari lokasi. Isi 'Tidak dicek' "
             "untuk employee lapangan yang memang tidak terikat lokasi.")
    foom_att_roster_ids = fields.One2many(
        'foom.attendance.roster', 'employee_id', string='Roster', groups=HR_USER)
    foom_att_session_ids = fields.One2many(
        'foom.attendance.session', 'employee_id', string='Sesi Absensi', groups=HR_USER)

    _sql_constraints = [
        ('foom_att_code_uniq', 'unique(foom_att_code)',
         'Kode Absensi harus unik — kode ini sudah dipakai employee lain.'),
    ]

    # ------------------------------------------------------------------
    # PIN
    # ------------------------------------------------------------------
    def _compute_foom_att_pin_set(self):
        for emp in self:
            emp.foom_att_pin_set = False

    def _inverse_foom_att_pin_set(self):
        for emp in self:
            raw = (emp.foom_att_pin_set or '').strip()
            if not raw:
                continue
            emp._foom_check_pin_format(raw)
            emp.sudo().write({
                'foom_att_pin_hash': generate_password_hash(raw),
                'foom_att_locked_until': False,
            })

    @api.depends('foom_att_pin_hash')
    def _compute_foom_att_pin_isset(self):
        for emp in self:
            emp.foom_att_pin_isset = bool(emp.foom_att_pin_hash)

    @api.model
    def _foom_check_pin_format(self, raw):
        min_len = 4
        if not re.fullmatch(r'\d{%d,12}' % min_len, raw):
            raise ValidationError(
                _("PIN harus berupa angka saja, %s sampai 12 digit.", min_len))
        if len(set(raw)) == 1 or raw in ('1234', '123456', '0000', '1111'):
            raise ValidationError(_("PIN terlalu mudah ditebak. Pakai kombinasi lain."))

    def foom_verify_pin(self, raw):
        """True kalau PIN cocok. Fallback ke field `pin` bawaan Odoo kalau
        employee belum pernah mengatur PIN modul ini."""
        self.ensure_one()
        emp = self.sudo()
        raw = (raw or '').strip()
        if not raw:
            return False
        if emp.foom_att_pin_hash:
            try:
                return check_password_hash(emp.foom_att_pin_hash, raw)
            except ValueError:
                return False
        if emp.pin:
            # migrasi lembut: PIN kiosk lama diterima sekali, lalu di-hash
            if utils.constant_time_equals(emp.pin, raw):
                emp.write({'foom_att_pin_hash': generate_password_hash(raw)})
                return True
        return False

    def action_foom_reset_lock(self):
        self.sudo().write({'foom_att_locked_until': False})
        for emp in self.sudo():
            self.env['foom.attendance.throttle']._register_success('emp:%s' % emp.id)

    def action_foom_generate_code(self):
        for emp in self.sudo():
            if emp.foom_att_code:
                continue
            for _try in range(20):
                code = 'F%s' % ''.join(str(_random.randint(0, 9)) for _ in range(6))
                if not self.sudo().search_count([('foom_att_code', '=', code)]):
                    emp.foom_att_code = code
                    break

    def action_foom_revoke_sessions(self):
        self.env['foom.attendance.session'].sudo().search([
            ('employee_id', 'in', self.ids), ('revoked', '=', False),
        ]).action_revoke()

    # ------------------------------------------------------------------
    # login lookup
    # ------------------------------------------------------------------
    @api.model
    def _foom_find_by_code(self, code):
        code = (code or '').strip()
        if not code or len(code) > 32:
            return self.sudo().browse()
        Employee = self.sudo().with_context(active_test=True)
        # `=ilike` diteruskan apa adanya ke SQL ILIKE. Tanpa escape, penyerang
        # bisa mengirim `%` atau `_` untuk mencocokkan employee mana pun dan
        # meng-enumerasi kode karyawan satu per satu.
        pattern = code.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')
        emp = Employee.search([('foom_att_code', '=ilike', pattern)], limit=2)
        if len(emp) == 1:
            return emp
        if len(emp) > 1:
            return Employee.browse()
        emp = Employee.search([('barcode', '=', code)], limit=2)
        return emp if len(emp) == 1 else Employee.browse()

    # ------------------------------------------------------------------
    # penyelesaian jadwal
    # ------------------------------------------------------------------
    def _foom_candidate_days(self, when_utc):
        """Tanggal lokal yang mungkin menaungi `when_utc`.

        Kemarin ikut diuji untuk shift lintas hari (clock out jam 02:00).
        Besok ikut diuji karena `early_in_window_minutes` bisa membuka jendela
        punch sebelum tengah malam lokal — mis. shift 00:30 dengan toleransi
        60 menit sudah menerima clock in sejak 23:30 hari sebelumnya.
        Hari ini tetap kandidat pertama supaya fallback tidak berubah.
        """
        tz = utils.employee_tz(self)
        local = utils.to_local(when_utc, tz)
        today = local.date()
        return tz, [today, today - timedelta(days=1), today + timedelta(days=1)]

    def foom_resolve_schedule(self, when_utc=None):
        """Tentukan roster/shift/lokasi/jadwal yang berlaku pada `when_utc`.

        Urutan: baris roster tanggal tsb -> shift default employee.
        Kandidat hari ini dan kemarin diuji; yang jendela punch-nya memuat
        `when_utc` menang. Kalau tidak ada yang memuat, kandidat hari ini dipakai
        dan ditandai `in_window=False`.
        """
        self.ensure_one()
        emp = self.sudo()
        when_utc = when_utc or fields.Datetime.now()
        tz, days = emp._foom_candidate_days(when_utc)
        Roster = self.env['foom.attendance.roster'].sudo()

        candidates = []
        for day in days:
            roster = Roster.search(
                [('employee_id', '=', emp.id), ('date', '=', day)], limit=1)
            if roster and roster.day_off:
                candidates.append({'day': day, 'roster': roster, 'shift': roster.shift_id.browse(),
                                   'day_off': True})
                continue
            shift = roster.shift_id if roster else emp.foom_att_shift_id
            if not shift:
                continue
            candidates.append({'day': day, 'roster': roster, 'shift': shift, 'day_off': False})

        chosen = None
        for cand in candidates:
            if cand['day_off'] or not cand['shift']:
                continue
            start, end = cand['shift'].punch_window_utc(cand['day'], tz)
            if start <= when_utc <= end:
                cand['in_window'] = True
                chosen = cand
                break
        if chosen is None:
            # Fallback WAJIB hari ini. `candidates` bisa saja hanya berisi
            # kemarin atau besok (hari tanpa shift tidak ikut di-append), dan
            # memakai candidates[0] apa adanya membuat punch hari ini menempel
            # ke jadwal hari lain — telat/pulang cepat jadi ngawur, dan roster
            # libur besok bisa memblokir absensi hari ini.
            chosen = next((c for c in candidates if c['day'] == days[0]), None) or {
                'day': days[0], 'roster': Roster.browse(),
                'shift': self.env['foom.attendance.shift'].sudo().browse(), 'day_off': False}
            chosen['in_window'] = False

        shift = chosen['shift']
        roster = chosen.get('roster') or Roster.browse()
        planned_in = planned_out = False
        if shift:
            planned_in, planned_out = shift.window_utc(chosen['day'], tz)

        return {
            'tz': tz,
            'day': chosen['day'],
            'roster': roster,
            'shift': shift,
            'day_off': chosen.get('day_off', False),
            'in_window': chosen.get('in_window', False),
            'planned_in': planned_in,
            'planned_out': planned_out,
        }

    def foom_candidate_locations(self, schedule):
        """Lokasi yang berlaku, terurut prioritas. Bisa kosong."""
        self.ensure_one()
        emp = self.sudo()
        roster = schedule.get('roster')
        if roster and roster.location_id:
            return roster.location_id
        shift = schedule.get('shift')
        if shift:
            allowed = shift.allowed_locations()
            if allowed:
                return allowed
        if emp.foom_att_location_id:
            return emp.foom_att_location_id
        return self.env['foom.attendance.location'].sudo().browse()

    def foom_day_window(self, schedule):
        """(tanggal_kerja, mulai_utc, selesai_utc) — rentang yang dihitung
        sebagai SATU hari absensi.

        Untuk shift lintas hari, rentangnya mengikuti jendela shift, bukan
        tengah malam kalender. Jadi clock in 22:00 dan clock out 06:00 esok
        harinya tetap satu hari kerja yang sama.
        """
        self.ensure_one()
        tz = schedule['tz']
        day = schedule['day']
        shift = schedule['shift']
        if shift:
            start, end = shift.punch_window_utc(day, tz)
        else:
            start = utils.local_naive_to_utc(day, 0.0, tz)
            end = utils.local_naive_to_utc(day + timedelta(days=1), 0.0, tz)
        return day, start, end

    def foom_completed_attendance(self, schedule):
        """Absensi yang sudah menutup hari kerja ini, kalau ada.

        Sengaja mencari lewat DUA jalur: `foom_work_date` (diisi modul ini) dan
        rentang waktu `check_in`. Jalur kedua membuat baris yang dibuat lewat
        backend, systray, atau impor ikut terhitung — kalau tidak, employee bisa
        absen dua kali hanya karena baris pertamanya tidak lewat halaman publik.
        """
        self.ensure_one()
        work_date, start, end = self.foom_day_window(schedule)
        return self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', self.id),
            '|', ('foom_work_date', '=', work_date),
            '&', ('check_in', '>=', start), ('check_in', '<', end),
        ], order='check_in desc', limit=1)

    def foom_effective_policy(self, location):
        """Kebijakan geofence yang berlaku: override employee > lokasi > default global."""
        self.ensure_one()
        override = self.sudo().foom_att_geofence_policy
        if override:
            return override
        if location:
            return location.geofence_policy
        return utils.get_param(self.env, 'default_geofence_policy') or 'block'
