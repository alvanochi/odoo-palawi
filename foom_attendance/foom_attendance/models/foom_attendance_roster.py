# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FoomAttendanceRoster(models.Model):
    _name = 'foom.attendance.roster'
    _description = 'Roster / Jadwal Shift Harian'
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True, ondelete='cascade')
    date = fields.Date(string='Tanggal', required=True, index=True,
                       default=fields.Date.context_today)
    shift_id = fields.Many2one('foom.attendance.shift', string='Shift', index=True)
    location_id = fields.Many2one(
        'foom.attendance.location', string='Lokasi',
        help="Kosongkan untuk memakai lokasi bawaan shift, lalu lokasi bawaan employee.")
    day_off = fields.Boolean(string='Libur')
    note = fields.Char(string='Catatan')
    company_id = fields.Many2one(
        related='employee_id.company_id', store=True, index=True, readonly=True)
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True, readonly=True)

    _sql_constraints = [
        ('employee_date_uniq', 'unique(employee_id, date)',
         'Sudah ada baris roster untuk employee dan tanggal ini.'),
    ]

    # `employee_id` ikut dipantau bukan karena dipakai di dalam pemeriksaan,
    # tapi karena Odoo hanya menjalankan constrains untuk field yang benar-benar
    # ada di vals. Tanpa field wajib di daftar ini, `create()` yang tidak
    # menyebut shift_id maupun day_off lolos tanpa diperiksa sama sekali.
    @api.constrains('shift_id', 'day_off', 'employee_id')
    def _check_shift(self):
        for rec in self:
            if not rec.day_off and not rec.shift_id:
                raise ValidationError(_("Isi Shift, atau centang Libur."))

    @api.depends('employee_id', 'date', 'shift_id', 'day_off')
    def _compute_display_name(self):
        for rec in self:
            label = _('Libur') if rec.day_off else (rec.shift_id.display_name or '-')
            rec.display_name = '%s · %s · %s' % (
                rec.employee_id.name or '', rec.date or '', label)

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        if self.shift_id and not self.location_id:
            self.location_id = self.shift_id.default_location_id
