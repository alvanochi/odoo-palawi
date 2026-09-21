# -*- coding: utf-8 -*-
"""Test end-to-end endpoint publik lewat HTTP sungguhan."""

import json
from datetime import timedelta

import pytz

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from .common import FAR_LAT, FAR_LON, HQ_LAT, HQ_LON, PIN_OK, FoomAttendanceCommon

BASE = '/foom/attendance'
JKT = pytz.timezone('Asia/Jakarta')


@tagged('post_install', '-at_install')
class TestPublicApi(FoomAttendanceCommon, HttpCase):

    def setUp(self):
        super().setUp()
        # jeda antar punch dimatikan supaya urutan clock in/out bisa diuji
        self._set_param('min_punch_interval_sec', '0')
        self.env['foom.attendance.throttle'].search([]).unlink()

    # ------------------------------------------------------------------
    def _post(self, path, payload):
        self.env.flush_all()
        response = self.url_open(
            '%s/api/%s' % (BASE, path),
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'})
        self.env.invalidate_all()
        return response, response.json()

    def _local_now(self):
        return pytz.utc.localize(fields.Datetime.now()).astimezone(JKT)

    def _login(self, code='ZZTEST001', pin=PIN_OK):
        _r, body = self._post('login', {'code': code, 'pin': pin})
        return body.get('token')

    def _punch(self, token, action, lat=HQ_LAT, lon=HQ_LON, accuracy=10, **extra):
        payload = {'token': token, 'action': action, 'accuracy': accuracy}
        if lat is not None:
            payload['latitude'] = lat
            payload['longitude'] = lon
        payload.update(extra)
        return self._post('punch', payload)[1]

    # == halaman ========================================================
    def test_page_renders(self):
        response = self.url_open(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertIn('fa-login-form', response.text)
        self.assertIn('<!DOCTYPE html>', response.text,
                      "doctype harus keluar mentah, bukan ter-escape")

    def test_page_hidden_when_disabled(self):
        self._set_param('public_enabled', '0')
        self.env.flush_all()
        response = self.url_open(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('fa-login-form', response.text)

    # == login ==========================================================
    def test_login_success(self):
        response, body = self._post('login', {'code': 'ZZTEST001', 'pin': PIN_OK})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['ok'])
        self.assertTrue(body['token'])
        self.assertEqual(body['employee']['name'], 'Budi Santoso')
        self.assertEqual(body['state'], 'checked_out')
        self.assertTrue(body['employee']['avatar'].startswith('data:image/'),
                        "avatar dikirim inline supaya token tidak perlu masuk URL")

    def test_login_is_case_insensitive_on_code(self):
        self.assertTrue(self._login(code='zztest001'))

    def test_wrong_pin_rejected(self):
        response, body = self._post('login', {'code': 'ZZTEST001', 'pin': '000000'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body['error'], 'invalid')
        self.assertNotIn('token', body)

    def test_unknown_code_looks_identical_to_wrong_pin(self):
        """Regresi. Respons yang berbeda membocorkan kode karyawan mana yang nyata."""
        r1, b1 = self._post('login', {'code': 'ZZTEST001', 'pin': '000000'})
        r2, b2 = self._post('login', {'code': 'TIDAKADA', 'pin': '000000'})
        self.assertEqual((r1.status_code, b1), (r2.status_code, b2))

    def test_disabled_employee_looks_identical_too(self):
        self.employee.foom_att_enabled = False
        r1, b1 = self._post('login', {'code': 'ZZTEST001', 'pin': PIN_OK})
        r2, b2 = self._post('login', {'code': 'TIDAKADA', 'pin': PIN_OK})
        self.assertEqual((r1.status_code, b1), (r2.status_code, b2))

    def test_wildcard_code_cannot_match_anyone(self):
        for probe in ('%', '_______', 'F%'):
            _r, body = self._post('login', {'code': probe, 'pin': PIN_OK})
            self.assertEqual(body['error'], 'invalid', 'pola %r tembus' % probe)

    def test_missing_fields(self):
        self.assertEqual(self._post('login', {})[1]['error'], 'missing')
        self.assertEqual(self._post('login', {'code': 'ZZTEST001'})[1]['error'], 'missing')

    def test_throttle_after_repeated_failures(self):
        self._set_param('pin_max_attempts', '3')
        self.env.flush_all()
        for _i in range(3):
            self.assertEqual(
                self._post('login', {'code': 'ZZTEST001', 'pin': '000000'})[1]['error'],
                'invalid')
        response, body = self._post('login', {'code': 'ZZTEST001', 'pin': '000000'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body['error'], 'throttled')
        # PIN yang benar pun ditolak selama masih terkunci
        self.assertEqual(self._post('login', {'code': 'ZZTEST001', 'pin': PIN_OK})[1]['error'],
                         'throttled')

    def test_unknown_code_also_reaches_throttle(self):
        """Kalau hanya kode yang nyata yang bisa memicu 429, selisih 401-vs-429
        itu sendiri sudah jadi alat enumerasi."""
        self._set_param('pin_max_attempts', '3')
        self.env.flush_all()
        for _i in range(3):
            self._post('login', {'code': 'HANTU99', 'pin': '000000'})
        self.assertEqual(
            self._post('login', {'code': 'HANTU99', 'pin': '000000'})[1]['error'],
            'throttled')

    # == sesi ============================================================
    def test_state_requires_valid_token(self):
        response, body = self._post('state', {'token': 'x' * 40})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body['error'], 'unauthorized')

    def test_logout_kills_token(self):
        token = self._login()
        self._post('logout', {'token': token})
        self.assertEqual(self._post('state', {'token': token})[1]['error'], 'unauthorized')

    def test_state_payload_shape(self):
        token = self._login()
        _r, body = self._post('state', {'token': token})
        self.assertTrue(body['ok'])
        self.assertEqual(body['timezone'], 'Asia/Jakarta')
        self.assertEqual(body['geofence']['locations'][0]['name'], 'Kantor Pusat')
        self.assertEqual(body['geofence']['locations'][0]['policy'], 'block')
        self.assertIn('shift_name', body['schedule'])
        self.assertEqual(body['today'], [])

    # == punch ===========================================================
    def test_clock_in_inside_radius(self):
        token = self._login()
        body = self._punch(token, 'in')
        self.assertTrue(body['ok'], body)
        self.assertEqual(body['action'], 'in')
        self.assertEqual(body['state'], 'checked_in')
        self.assertFalse(body['outside_geofence'])
        self.assertLess(body['distance_m'], 5)

        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.employee_id, self.employee)
        self.assertEqual(att.foom_source, 'public')
        self.assertEqual(att.foom_in_location_id, self.hq)
        self.assertTrue(att.foom_in_geo_checked)
        self.assertFalse(att.foom_in_outside)
        self.assertEqual(att.in_mode, 'kiosk', "field bawaan Odoo ikut terisi")
        self.assertAlmostEqual(att.in_latitude, HQ_LAT, places=4)

    def test_clock_out_closes_the_same_record(self):
        token = self._login()
        opened = self._punch(token, 'in')['attendance_id']
        body = self._punch(token, 'out')
        self.assertTrue(body['ok'], body)
        self.assertEqual(body['state'], 'checked_out')
        att = self.Attendance.browse(opened)
        self.assertTrue(att.check_out)
        self.assertEqual(att.foom_out_location_id, self.hq)
        self.assertTrue(att.foom_out_geo_checked)
        self.assertEqual(att.out_mode, 'kiosk')

    def test_outside_radius_is_blocked(self):
        token = self._login()
        body = self._punch(token, 'in', lat=FAR_LAT, lon=FAR_LON)
        self.assertFalse(body['ok'])
        self.assertEqual(body['error'], 'outside_geofence')
        self.assertGreater(body['distance'], 4000)
        self.assertEqual(body['radius'], 150)
        self.assertFalse(self.Attendance.search([('employee_id', '=', self.employee.id)]),
                         "punch yang ditolak tidak boleh meninggalkan baris absensi")

    def test_missing_accuracy_is_rejected(self):
        """Regresi. Tanpa cek ini, ambang akurasi bisa dilewati cukup dengan
        tidak mengirim field-nya."""
        token = self._login()
        _r, body = self._post('punch', {'token': token, 'action': 'in',
                                        'latitude': HQ_LAT, 'longitude': HQ_LON})
        self.assertEqual(body['error'], 'bad_accuracy')

    def test_poor_accuracy_is_rejected(self):
        token = self._login()
        body = self._punch(token, 'in', accuracy=5000)
        self.assertEqual(body['error'], 'bad_accuracy')

    def test_missing_coordinates_rejected_when_geofenced(self):
        token = self._login()
        body = self._punch(token, 'in', lat=None)
        self.assertEqual(body['error'], 'no_location')

    def test_null_island_rejected(self):
        token = self._login()
        body = self._punch(token, 'in', lat=0.0, lon=0.0)
        self.assertEqual(body['error'], 'no_location')

    def test_warn_policy_records_but_flags(self):
        self.hq.geofence_policy = 'warn'
        self._set_param('require_reason_outside', '0')
        token = self._login()
        body = self._punch(token, 'in', lat=FAR_LAT, lon=FAR_LON)
        self.assertTrue(body['ok'], body)
        self.assertTrue(body['outside_geofence'])
        att = self.Attendance.browse(body['attendance_id'])
        self.assertTrue(att.foom_in_outside)
        self.assertTrue(att.foom_outside)

    def test_warn_policy_requires_reason(self):
        self.hq.geofence_policy = 'warn'
        token = self._login()
        body = self._punch(token, 'in', lat=FAR_LAT, lon=FAR_LON)
        self.assertEqual(body['error'], 'reason_required')
        self.assertTrue(body['need_reason'])

        body = self._punch(token, 'in', lat=FAR_LAT, lon=FAR_LON,
                           note='kunjungan klien di Kota Tua')
        self.assertTrue(body['ok'], body)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.foom_in_note, 'kunjungan klien di Kota Tua')

    def test_policy_off_accepts_punch_without_coordinates(self):
        self.employee.foom_att_geofence_policy = 'off'
        token = self._login()
        _r, body = self._post('punch', {'token': token, 'action': 'in'})
        self.assertTrue(body['ok'], body)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertFalse(att.foom_in_geo_checked,
                         "jarak tidak pernah diukur — jangan tercatat seolah 0 meter")

    def test_fail_closed_when_no_location_configured(self):
        """Regresi. Employee tanpa roster/shift/lokasi default tidak boleh bisa
        absen dari mana saja hanya karena tidak ada lokasi yang bisa dicek."""
        bare = self.Employee.create({
            'name': 'Siti Lapangan', 'tz': 'Asia/Jakarta',
            'foom_att_code': 'ZZTEST002', 'foom_att_pin_set': '735182'})
        self.assertFalse(bare.foom_att_location_id)
        token = self._login(code='ZZTEST002', pin='735182')
        body = self._punch(token, 'in')
        self.assertEqual(body['error'], 'no_location_configured')

    def test_state_mismatch_when_client_is_stale(self):
        token = self._login()
        self._punch(token, 'in')
        body = self._punch(token, 'in')
        self.assertEqual(body['error'], 'state_mismatch')
        self.assertEqual(body['state'], 'checked_in',
                         "respons ikut membawa state terbaru supaya layar bisa disegarkan")

    def test_server_decides_action_when_client_omits_it(self):
        token = self._login()
        _r, body = self._post('punch', {'token': token, 'latitude': HQ_LAT,
                                        'longitude': HQ_LON, 'accuracy': 10})
        self.assertEqual(body['action'], 'in')
        _r, body = self._post('punch', {'token': token, 'latitude': HQ_LAT,
                                        'longitude': HQ_LON, 'accuracy': 10})
        self.assertEqual(body['action'], 'out')

    def test_cooldown_between_punches(self):
        self._set_param('min_punch_interval_sec', '3600')
        token = self._login()
        self._punch(token, 'in')
        self.assertEqual(self._punch(token, 'out')['error'], 'too_soon')

    def test_cannot_punch_for_someone_else(self):
        """Tidak ada endpoint yang menerima employee_id — identitas hanya dari token."""
        victim = self.Employee.create({
            'name': 'Korban', 'tz': 'Asia/Jakarta',
            'foom_att_code': 'ZZTEST009', 'foom_att_pin_set': '918273',
            'foom_att_location_id': self.hq.id})
        token = self._login()
        body = self._punch(token, 'in', employee_id=victim.id)
        self.assertTrue(body['ok'], body)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.employee_id, self.employee)
        self.assertFalse(self.Attendance.search([('employee_id', '=', victim.id)]))

    def test_late_minutes_recorded(self):
        """Shift dibuat relatif terhadap jam sekarang supaya test tidak bergantung
        pada kapan ia dijalankan."""
        started = self._local_now() - timedelta(minutes=40)
        shift = self.Shift.create({
            'name': 'Tes Telat',
            'time_from': started.hour + started.minute / 60.0,
            'time_to': (started.hour + 8) % 24 + started.minute / 60.0,
            'grace_in_minutes': 10,
            'early_in_window_minutes': 120,
            'late_out_window_minutes': 120,
            'location_ids': [(6, 0, self.hq.ids)], 'default_location_id': self.hq.id})
        self.Roster.create({'employee_id': self.employee.id,
                            'date': started.date(), 'shift_id': shift.id})
        token = self._login()
        body = self._punch(token, 'in')
        self.assertTrue(body['ok'], body)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.foom_shift_id, shift)
        self.assertTrue(att.foom_roster_id)
        self.assertAlmostEqual(att.foom_late_minutes, 30, delta=2,
                               msg="telat 40 menit dikurangi toleransi 10 menit")
