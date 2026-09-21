# -*- coding: utf-8 -*-
"""Fixture bersama untuk test `foom_attendance`.

Semua test memakai zona waktu Asia/Jakarta (UTC+7, tanpa DST) supaya
perhitungan jendela shift bisa diperiksa dengan angka pasti.
"""

from odoo.tests.common import TransactionCase

from ..models.utils import PARAM_PREFIX

# Monas, Jakarta Pusat
HQ_LAT = -6.1753924
HQ_LON = 106.8271528

# Kota Tua — ~4,7 km dari Monas, dipakai sebagai titik "di luar radius"
FAR_LAT = -6.1351800
FAR_LON = 106.8133300

PIN_OK = '482913'


class FoomAttendanceCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env['foom.attendance.location']
        cls.Shift = cls.env['foom.attendance.shift']
        cls.Roster = cls.env['foom.attendance.roster']
        cls.Session = cls.env['foom.attendance.session']
        cls.Throttle = cls.env['foom.attendance.throttle']
        cls.Employee = cls.env['hr.employee']
        cls.Attendance = cls.env['hr.attendance']

        cls.hq = cls.Location.create({
            'name': 'Kantor Pusat',
            'code': 'HQ',
            'latitude': HQ_LAT,
            'longitude': HQ_LON,
            'radius_m': 150,
            'geofence_policy': 'block',
        })
        cls.branch = cls.Location.create({
            'name': 'Cabang Kota Tua',
            'code': 'KT',
            'latitude': FAR_LAT,
            'longitude': FAR_LON,
            'radius_m': 100,
            'geofence_policy': 'warn',
        })

        cls.shift_day = cls.Shift.create({
            'name': 'Pagi',
            'time_from': 8.0,
            'time_to': 17.0,
            'grace_in_minutes': 10,
            'grace_out_minutes': 5,
            'early_in_window_minutes': 60,
            'late_out_window_minutes': 240,
            'location_ids': [(6, 0, cls.hq.ids)],
            'default_location_id': cls.hq.id,
        })
        cls.shift_night = cls.Shift.create({
            'name': 'Malam',
            'time_from': 22.0,
            'time_to': 6.0,
            'grace_in_minutes': 10,
            'location_ids': [(6, 0, cls.hq.ids)],
            'default_location_id': cls.hq.id,
        })

        cls.employee = cls.Employee.create({
            'name': 'Budi Santoso',
            'tz': 'Asia/Jakarta',
            'foom_att_code': 'ZZTEST001',
            'foom_att_pin_set': PIN_OK,
            'foom_att_shift_id': cls.shift_day.id,
            'foom_att_location_id': cls.hq.id,
        })

    # ------------------------------------------------------------------
    @classmethod
    def _set_param(cls, name, value):
        cls.env['ir.config_parameter'].sudo().set_param(PARAM_PREFIX + name, value)

    def _relax_punch_limits(self):
        """Matikan jeda antar punch supaya test bisa clock in/out beruntun."""
        self._set_param('min_punch_interval_sec', '1')
