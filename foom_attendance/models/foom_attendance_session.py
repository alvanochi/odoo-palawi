# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

from . import utils


class FoomAttendanceSession(models.Model):
    """Sesi bertoken untuk halaman absensi publik.

    Token asli hanya pernah ada di respons HTTP pertama; database hanya
    menyimpan SHA-256-nya, jadi bocornya dump tabel tidak langsung memberi
    akses ke akun absensi siapa pun.
    """
    _name = 'foom.attendance.session'
    _description = 'Sesi Absensi Publik'
    _order = 'create_date desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='employee_id.company_id', store=True, readonly=True)
    token_hash = fields.Char(required=True, index=True, groups='hr.group_hr_user')
    expire_at = fields.Datetime(string='Kedaluwarsa', required=True, index=True)
    revoked = fields.Boolean(default=False)
    last_seen = fields.Datetime()
    ip = fields.Char(string='IP')
    user_agent = fields.Char(string='User Agent')
    punch_count = fields.Integer(default=0)
    state = fields.Selection(
        [('active', 'Aktif'), ('expired', 'Kedaluwarsa'), ('revoked', 'Dicabut')],
        compute='_compute_state', search='_search_state')

    @api.depends('expire_at', 'revoked')
    def _compute_state(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.revoked:
                rec.state = 'revoked'
            elif rec.expire_at and rec.expire_at <= now:
                rec.state = 'expired'
            else:
                rec.state = 'active'

    def _search_state(self, operator, value):
        now = fields.Datetime.now()
        if operator not in ('=', '!='):
            return [(0, '=', 1)]
        domains = {
            'active': ['&', ('revoked', '=', False), ('expire_at', '>', now)],
            'expired': ['&', ('revoked', '=', False), ('expire_at', '<=', now)],
            'revoked': [('revoked', '=', True)],
        }
        domain = domains.get(value, [(0, '=', 1)])
        return domain if operator == '=' else ['!'] + domain

    # ------------------------------------------------------------------
    @api.model
    def _issue(self, employee, ip=None, user_agent=None):
        """Buat sesi baru, kembalikan (record, token_plaintext)."""
        minutes = utils.get_int_param(self.env, 'session_minutes')
        token = utils.new_token()
        session = self.sudo().create({
            'employee_id': employee.id,
            'token_hash': utils.hash_token(token),
            'expire_at': fields.Datetime.now() + timedelta(minutes=max(5, minutes)),
            'ip': (ip or '')[:64],
            'user_agent': (user_agent or '')[:256],
            'last_seen': fields.Datetime.now(),
        })
        return session, token

    @api.model
    def _resolve(self, token):
        """Kembalikan sesi aktif untuk token, atau recordset kosong."""
        if not token or len(token) > 128:
            return self.sudo().browse()
        session = self.sudo().search([
            ('token_hash', '=', utils.hash_token(token)),
            ('revoked', '=', False),
            ('expire_at', '>', fields.Datetime.now()),
            # employee yang diarsipkan otomatis di-check-out oleh hr_attendance;
            # tanpa filter ini token lamanya masih bisa membuat absensi baru
            ('employee_id.active', '=', True),
        ], limit=1)
        if session:
            session.last_seen = fields.Datetime.now()
        return session

    def action_revoke(self):
        self.write({'revoked': True})

    @api.model
    def _gc_sessions(self, days=7):
        """Cron: buang sesi mati yang sudah lewat masa simpan."""
        limit = fields.Datetime.now() - timedelta(days=days)
        stale = self.sudo().search(['|', ('revoked', '=', True), ('expire_at', '<', limit)])
        stale.unlink()
        self.env['foom.attendance.throttle'].sudo()._gc()
        return True


class FoomAttendanceThrottle(models.Model):
    """Penghitung percobaan login gagal, per employee dan per IP."""
    _name = 'foom.attendance.throttle'
    _description = 'Throttle Login Absensi'
    _order = 'write_date desc'
    _rec_name = 'key'

    key = fields.Char(required=True, index=True)
    counter = fields.Integer(default=0)
    window_start = fields.Datetime(default=fields.Datetime.now)
    blocked_until = fields.Datetime()

    _sql_constraints = [('key_uniq', 'unique(key)', 'Kunci throttle harus unik.')]

    @api.model
    def _get(self, key):
        rec = self.sudo().search([('key', '=', key)], limit=1)
        if not rec:
            rec = self.sudo().create({'key': key})
        return rec

    @api.model
    def _is_blocked(self, key):
        rec = self.sudo().search([('key', '=', key)], limit=1)
        if rec and rec.blocked_until and rec.blocked_until > fields.Datetime.now():
            return rec.blocked_until
        return False

    @api.model
    def _register_failure(self, key, max_attempts, window_minutes, block_minutes):
        now = fields.Datetime.now()
        rec = self._get(key)
        if not rec.window_start or rec.window_start + timedelta(minutes=window_minutes) < now:
            rec.write({'window_start': now, 'counter': 1})
        else:
            rec.counter += 1
        if rec.counter >= max_attempts:
            rec.write({'blocked_until': now + timedelta(minutes=block_minutes),
                       'counter': 0, 'window_start': now})
            return rec.blocked_until
        return False

    @api.model
    def _register_success(self, key):
        rec = self.sudo().search([('key', '=', key)], limit=1)
        if rec:
            rec.write({'counter': 0, 'blocked_until': False,
                       'window_start': fields.Datetime.now()})

    @api.model
    def _gc(self, days=2):
        limit = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([
            ('write_date', '<', limit),
            '|', ('blocked_until', '=', False), ('blocked_until', '<', fields.Datetime.now()),
        ]).unlink()
