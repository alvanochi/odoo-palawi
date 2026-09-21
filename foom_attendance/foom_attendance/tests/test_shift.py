# -*- coding: utf-8 -*-
from datetime import date, datetime

import pytz

from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from ..models import utils
from .common import FoomAttendanceCommon

JKT = pytz.timezone('Asia/Jakarta')


@tagged('post_install', '-at_install')
class TestShift(FoomAttendanceCommon):

    def test_overnight_detection_and_duration(self):
        self.assertFalse(self.shift_day.is_overnight)
        self.assertAlmostEqual(self.shift_day.duration_hours, 9.0)

        self.assertTrue(self.shift_night.is_overnight)
        self.assertAlmostEqual(self.shift_night.duration_hours, 8.0,
                               msg="22:00->06:00 harus 8 jam, bukan -16")

    def test_shift_ending_exactly_at_start_is_overnight(self):
        full = self.Shift.create({'name': '24h', 'time_from': 6.0, 'time_to': 6.0})
        self.assertTrue(full.is_overnight)
        self.assertAlmostEqual(full.duration_hours, 24.0)

    def test_window_utc_converts_from_employee_timezone(self):
        start, end = self.shift_day.window_utc(date(2026, 9, 1), JKT)
        # 08:00 WIB = 01:00 UTC, 17:00 WIB = 10:00 UTC
        self.assertEqual(start, datetime(2026, 9, 1, 1, 0))
        self.assertEqual(end, datetime(2026, 9, 1, 10, 0))

    def test_window_utc_overnight_ends_next_day(self):
        start, end = self.shift_night.window_utc(date(2026, 9, 1), JKT)
        # 22:00 WIB 1 Sep = 15:00 UTC 1 Sep; 06:00 WIB 2 Sep = 23:00 UTC 1 Sep
        self.assertEqual(start, datetime(2026, 9, 1, 15, 0))
        self.assertEqual(end, datetime(2026, 9, 1, 23, 0))
        self.assertGreater(end, start)

    def test_punch_window_applies_margins(self):
        start, end = self.shift_day.window_utc(date(2026, 9, 1), JKT)
        p_start, p_end = self.shift_day.punch_window_utc(date(2026, 9, 1), JKT)
        self.assertEqual((start - p_start).total_seconds() / 60, 60)
        self.assertEqual((p_end - end).total_seconds() / 60, 240)

    def test_half_hour_shift_times(self):
        half = self.Shift.create({'name': 'Setengah', 'time_from': 8.5, 'time_to': 16.25})
        start, end = half.window_utc(date(2026, 9, 1), JKT)
        self.assertEqual(start, datetime(2026, 9, 1, 1, 30))   # 08:30 WIB
        self.assertEqual(end, datetime(2026, 9, 1, 9, 15))     # 16:15 WIB

    def test_time_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            self.Shift.create({'name': 'X', 'time_from': 24.0, 'time_to': 8.0})
        with self.assertRaises(ValidationError):
            self.Shift.create({'name': 'X', 'time_from': -1.0, 'time_to': 8.0})

    def test_default_location_must_be_allowed(self):
        with self.assertRaises(ValidationError):
            self.Shift.create({
                'name': 'X', 'time_from': 8.0, 'time_to': 17.0,
                'location_ids': [(6, 0, self.hq.ids)],
                'default_location_id': self.branch.id,
            })

    def test_float_to_hm_rounding(self):
        self.assertEqual(utils.float_to_hm(8.0), (8, 0))
        self.assertEqual(utils.float_to_hm(8.5), (8, 30))
        self.assertEqual(utils.float_to_hm(8.99), (8, 59))
        self.assertEqual(utils.float_to_hm(23.999), (24, 0))

    def test_local_naive_to_utc_handles_hour_overflow(self):
        """float_hour >= 24 harus menggeser tanggal, bukan melempar error."""
        got = utils.local_naive_to_utc(date(2026, 9, 1), 25.0, JKT)
        self.assertEqual(got, datetime(2026, 9, 1, 18, 0))  # 01:00 WIB 2 Sep

    def test_display_name_shows_hours(self):
        self.assertEqual(self.shift_day.display_name, 'Pagi (08:00–17:00)')
