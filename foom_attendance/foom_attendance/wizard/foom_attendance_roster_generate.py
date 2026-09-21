# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

class FoomAttendanceRosterGenerate(models.TransientModel):
    _name = 'foom.attendance.roster.generate'
    _description = 'Generate Roster Massal'

    employee_ids = fields.Many2many('hr.employee', string='Employee', required=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    shift_id = fields.Many2one('foom.attendance.shift', string='Shift', required=True)
    location_id = fields.Many2one('foom.attendance.location', string='Lokasi')
    weekday_ids = fields.Char(
        string='Hari Kerja', default='0,1,2,3,4',
        help="Indeks hari dipisah koma. 0 = Senin ... 6 = Minggu.")
    mark_rest_as_day_off = fields.Boolean(
        string='Tandai Hari Lain sebagai Libur', default=False)
    overwrite = fields.Boolean(
        string='Timpa Baris yang Sudah Ada', default=False,
        help="Kalau tidak dicentang, tanggal yang sudah punya roster dilewati.")

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        if self.shift_id and not self.location_id:
            self.location_id = self.shift_id.default_location_id

    @api.constrains('date_from', 'date_to')
    def _check_range(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise UserError(_("Tanggal akhir tidak boleh sebelum tanggal awal."))
            if (rec.date_to - rec.date_from).days > 366:
                raise UserError(_("Rentang maksimum 366 hari."))

    def _weekdays(self):
        self.ensure_one()
        raw = (self.weekday_ids or '').replace(' ', '')
        out = set()
        for chunk in raw.split(','):
            if chunk.isdigit() and 0 <= int(chunk) <= 6:
                out.add(int(chunk))
        return out

    def action_generate(self):
        self.ensure_one()
        weekdays = self._weekdays()
        if not weekdays and not self.mark_rest_as_day_off:
            raise UserError(_("Pilih minimal satu hari kerja."))

        Roster = self.env['foom.attendance.roster']
        days = []
        # JANGAN menamai variabel lokal ini `cr` atau `cursor`.
        # `odoo/tools/translate.py::_get_cr` menganggap lokal bernama `cr`/`cursor`
        # sebagai cursor database, lalu `_()` di akhir method ini meledak dengan
        # `AssertionError: isinstance(cr, BaseCursor)` — tanpa pesan yang berguna.
        day_cursor = self.date_from
        while day_cursor <= self.date_to:
            days.append(day_cursor)
            day_cursor += timedelta(days=1)

        existing = Roster.search([
            ('employee_id', 'in', self.employee_ids.ids),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        by_key = {(r.employee_id.id, r.date): r for r in existing}

        to_create, created, updated, skipped = [], 0, 0, 0
        for employee in self.employee_ids:
            for day in days:
                working = day.weekday() in weekdays
                if not working and not self.mark_rest_as_day_off:
                    continue
                vals = {
                    'employee_id': employee.id,
                    'date': day,
                    'day_off': not working,
                    'shift_id': self.shift_id.id if working else False,
                    'location_id': self.location_id.id if working else False,
                }
                current = by_key.get((employee.id, day))
                if current:
                    if self.overwrite:
                        current.write(vals)
                        updated += 1
                    else:
                        skipped += 1
                    continue
                to_create.append(vals)
        if to_create:
            Roster.create(to_create)
            created = len(to_create)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Roster dibuat'),
                'message': _('%(c)s baru, %(u)s diperbarui, %(s)s dilewati.',
                             c=created, u=updated, s=skipped),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
