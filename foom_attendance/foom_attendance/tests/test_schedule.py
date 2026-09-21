# -*- coding: utf-8 -*-
"""Resolusi jadwal — bagian paling rawan salah di modul ini.

Semua waktu beku (`freeze_time`) diberikan dalam UTC; employee ber-zona
Asia/Jakarta (UTC+7), jadi 2026-09-01 01:30 UTC = 08:30 WIB.
"""

from datetime import date

from freezegun import freeze_time

from odoo.tests.common import tagged

from .common import FoomAttendanceCommon


@tagged('post_install', '-at_install')
class TestSchedule(FoomAttendanceCommon):

    # -- sumber shift ----------------------------------------------------
    @freeze_time('2026-09-01 01:30:00')
    def test_default_shift_used_without_roster(self):
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['shift'], self.shift_day)
        self.assertFalse(sched['roster'])
        self.assertEqual(sched['day'], date(2026, 9, 1))
        self.assertTrue(sched['in_window'])

    @freeze_time('2026-09-01 01:30:00')
    def test_roster_beats_default_shift(self):
        other = self.Shift.create({'name': 'Siang', 'time_from': 7.0, 'time_to': 16.0,
                                   'default_location_id': self.branch.id,
                                   'location_ids': [(6, 0, self.branch.ids)]})
        roster = self.Roster.create({
            'employee_id': self.employee.id, 'date': date(2026, 9, 1),
            'shift_id': other.id, 'location_id': self.branch.id})
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['shift'], other)
        self.assertEqual(sched['roster'], roster)
        self.assertEqual(self.employee.foom_candidate_locations(sched), self.branch)

    @freeze_time('2026-09-01 01:30:00')
    def test_day_off_roster_is_reported(self):
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 1),
                            'day_off': True})
        sched = self.employee.foom_resolve_schedule()
        self.assertTrue(sched['day_off'])
        self.assertFalse(sched['shift'])

    # -- shift lintas hari -------------------------------------------------
    @freeze_time('2026-09-01 19:00:00')  # 02:00 WIB tanggal 2
    def test_overnight_clock_out_belongs_to_yesterday(self):
        self.employee.foom_att_shift_id = self.shift_night
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 1),
                            'shift_id': self.shift_night.id})
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 1),
                         "pukul 02:00 masih milik shift malam yang mulai kemarin")
        self.assertTrue(sched['in_window'])
        self.assertEqual(sched['planned_out'].hour, 23)  # 06:00 WIB = 23:00 UTC

    @freeze_time('2026-09-01 16:40:00')  # 23:40 WIB tanggal 1
    def test_early_window_can_reach_into_tomorrow(self):
        """Shift 00:30 dengan toleransi masuk 60 menit sudah buka sejak 23:30."""
        dini = self.Shift.create({
            'name': 'Dini Hari', 'time_from': 0.5, 'time_to': 8.0,
            'early_in_window_minutes': 60,
            'location_ids': [(6, 0, self.hq.ids)], 'default_location_id': self.hq.id})
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 2),
                            'shift_id': dini.id})
        self.employee.foom_att_shift_id = False
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 2))
        self.assertEqual(sched['shift'], dini)
        self.assertTrue(sched['in_window'])

    # -- regresi: fallback tidak boleh mencomot hari lain --------------------
    @freeze_time('2026-09-01 03:00:00')  # 10:00 WIB tanggal 1
    def test_fallback_stays_on_today_when_only_tomorrow_has_roster(self):
        """Regresi. Kalau fallback memakai candidates[0] apa adanya, punch hari
        ini menempel ke jadwal besok dan menit pulang-cepat meledak ~1440."""
        self.employee.foom_att_shift_id = False
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 2),
                            'shift_id': self.shift_day.id})
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 1))
        self.assertFalse(sched['shift'], "jadwal besok tidak boleh dipakai hari ini")
        self.assertFalse(sched['in_window'])

    @freeze_time('2026-09-01 03:00:00')
    def test_fallback_stays_on_today_when_only_yesterday_has_roster(self):
        self.employee.foom_att_shift_id = False
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 8, 31),
                            'shift_id': self.shift_day.id})
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 1))
        self.assertFalse(sched['shift'])

    @freeze_time('2026-09-01 03:00:00')
    def test_day_off_tomorrow_does_not_block_today(self):
        """Regresi. Baris libur besok tidak boleh membuat hari ini ikut libur."""
        self.employee.foom_att_shift_id = False
        self.Roster.create({'employee_id': self.employee.id, 'date': date(2026, 9, 2),
                            'day_off': True})
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 1))
        self.assertFalse(sched['day_off'])

    # -- di luar jendela --------------------------------------------------
    @freeze_time('2026-09-01 08:00:00')  # 15:00 WIB — masih di dalam shift pagi
    def test_in_window_true_during_shift(self):
        self.assertTrue(self.employee.foom_resolve_schedule()['in_window'])

    @freeze_time('2026-08-31 21:00:00')  # 04:00 WIB — jauh sebelum shift pagi
    def test_in_window_false_outside_shift(self):
        sched = self.employee.foom_resolve_schedule()
        self.assertFalse(sched['in_window'])
        self.assertEqual(sched['shift'], self.shift_day,
                         "shift tetap dikenali, hanya ditandai di luar jendela")

    # -- zona waktu -------------------------------------------------------
    @freeze_time('2026-09-01 20:00:00')  # 03:00 WIB tanggal 2
    def test_local_date_uses_employee_timezone_not_utc(self):
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(sched['day'], date(2026, 9, 2),
                         "UTC masih tanggal 1, tapi employee sudah tanggal 2")

    def test_employee_without_tz_falls_back_gracefully(self):
        bare = self.Employee.create({'name': 'Tanpa TZ', 'tz': False})
        sched = bare.foom_resolve_schedule()
        self.assertTrue(sched['tz'])
