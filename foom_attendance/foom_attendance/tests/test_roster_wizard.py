# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import FoomAttendanceCommon


@tagged('post_install', '-at_install')
class TestRosterWizard(FoomAttendanceCommon):

    def _wizard(self, **overrides):
        vals = {
            'employee_ids': [(6, 0, self.employee.ids)],
            'date_from': date(2026, 9, 1),   # Selasa
            'date_to': date(2026, 9, 14),    # Senin
            'shift_id': self.shift_day.id,
            'location_id': self.hq.id,
            'weekday_ids': '0,1,2,3,4',
        }
        vals.update(overrides)
        return self.env['foom.attendance.roster.generate'].create(vals)

    def _rosters(self):
        return self.Roster.search([
            ('employee_id', '=', self.employee.id),
            ('date', '>=', date(2026, 9, 1)), ('date', '<=', date(2026, 9, 14))])

    def test_generates_weekdays_only(self):
        self._wizard().action_generate()
        rosters = self._rosters()
        self.assertEqual(len(rosters), 10, "1-14 Sep 2026 berisi 10 hari kerja")
        self.assertTrue(all(r.date.weekday() < 5 for r in rosters))
        self.assertTrue(all(r.shift_id == self.shift_day for r in rosters))
        self.assertTrue(all(r.location_id == self.hq for r in rosters))

    def test_mark_rest_as_day_off(self):
        self._wizard(mark_rest_as_day_off=True).action_generate()
        rosters = self._rosters()
        self.assertEqual(len(rosters), 14)
        self.assertEqual(len(rosters.filtered('day_off')), 4)
        self.assertTrue(all(not r.shift_id for r in rosters.filtered('day_off')))

    def test_second_run_skips_existing(self):
        self._wizard().action_generate()
        self._wizard().action_generate()
        self.assertEqual(len(self._rosters()), 10, "tidak boleh menggandakan baris")

    def test_overwrite_updates_existing(self):
        self._wizard().action_generate()
        night = self.shift_night
        self._wizard(shift_id=night.id, location_id=self.hq.id,
                     overwrite=True).action_generate()
        self.assertTrue(all(r.shift_id == night for r in self._rosters()))

    def test_weekend_only_schedule(self):
        self._wizard(weekday_ids='5,6').action_generate()
        rosters = self._rosters()
        self.assertEqual(len(rosters), 4)
        self.assertTrue(all(r.date.weekday() >= 5 for r in rosters))

    def test_garbage_weekday_input_ignored(self):
        self._wizard(weekday_ids='0, 1, x, 9, -2').action_generate()
        self.assertTrue(all(r.date.weekday() in (0, 1) for r in self._rosters()))

    def test_no_weekday_selected_raises(self):
        with self.assertRaises(UserError):
            self._wizard(weekday_ids='').action_generate()

    def test_reversed_range_rejected(self):
        with self.assertRaises(UserError):
            self._wizard(date_from=date(2026, 9, 14), date_to=date(2026, 9, 1))

    def test_range_cap(self):
        with self.assertRaises(UserError):
            self._wizard(date_from=date(2026, 1, 1), date_to=date(2028, 1, 1))

    @mute_logger('odoo.sql_db')
    def test_roster_unique_per_employee_and_date(self):
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 1),
                            'shift_id': self.shift_day.id})
        with self.assertRaises(Exception):
            self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 1),
                                'shift_id': self.shift_night.id})
            self.env.flush_all()

    def test_roster_requires_shift_unless_day_off(self):
        with self.assertRaises(ValidationError):
            self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 3)})
