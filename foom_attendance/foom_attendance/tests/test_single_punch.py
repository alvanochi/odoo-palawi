# -*- coding: utf-8 -*-
"""Batas satu absensi per hari kerja, dan status foto selfie."""

import base64
import json
from datetime import timedelta

import pytz

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from .common import HQ_LAT, HQ_LON, PIN_OK, FoomAttendanceCommon

JKT = pytz.timezone('Asia/Jakarta')

# JPEG 8x8 yang benar-benar valid. Harus valid sungguhan, bukan sekadar lolos
# magic byte: `fields.Image` menjalankan Pillow untuk me-resize, dan gambar
# rusak akan ditolak di sana.
TINY_JPEG = (
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikx'
    'MC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5aYVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01'
    'T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAAR'
    'CAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA'
    'AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK'
    'FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG'
    'h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl'
    '5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA'
    'AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk'
    'NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE'
    'hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk'
    '5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDDooor3zyj/9k='
)


@tagged('post_install', '-at_install')
class TestSinglePunchPerDay(FoomAttendanceCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self._set_param('min_punch_interval_sec', '0')
        self._set_param('single_clock_in_per_day', '1')
        self.env['foom.attendance.throttle'].search([]).unlink()

    # ------------------------------------------------------------------
    def _post(self, path, payload):
        self.env.flush_all()
        response = self.url_open(
            '/foom/attendance/api/%s' % path,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'})
        self.env.invalidate_all()
        return response.json()

    def _login(self):
        return self._post('login', {'code': 'ZZTEST001', 'pin': PIN_OK}).get('token')

    def _punch(self, token, action, **extra):
        payload = {'token': token, 'action': action, 'latitude': HQ_LAT,
                   'longitude': HQ_LON, 'accuracy': 10}
        payload.update(extra)
        return self._post('punch', payload)

    def _full_day(self, token):
        self.assertTrue(self._punch(token, 'in')['ok'])
        self.assertTrue(self._punch(token, 'out')['ok'])

    # == batas harian =====================================================
    def test_second_clock_in_blocked_after_completing_the_day(self):
        token = self._login()
        self._full_day(token)
        body = self._punch(token, 'in')
        self.assertFalse(body['ok'])
        self.assertEqual(body['error'], 'already_done_today')
        self.assertEqual(
            self.Attendance.search_count([('employee_id', '=', self.employee.id)]), 1)

    def test_state_reports_day_done(self):
        token = self._login()
        self.assertFalse(self._post('state', {'token': token})['day_done'])
        self._full_day(token)
        body = self._post('state', {'token': token})
        self.assertTrue(body['day_done'],
                        "halaman perlu tahu supaya tombol bisa dimatikan")
        self.assertEqual(body['state'], 'checked_out')

    def test_clock_out_still_allowed_while_checked_in(self):
        token = self._login()
        self.assertTrue(self._punch(token, 'in')['ok'])
        self.assertFalse(self._post('state', {'token': token})['day_done'],
                         "hari belum selesai selama masih clock in")
        self.assertTrue(self._punch(token, 'out')['ok'])

    def test_work_date_is_stamped(self):
        token = self._login()
        body = self._punch(token, 'in')
        att = self.Attendance.browse(body['attendance_id'])
        today_local = pytz.utc.localize(fields.Datetime.now()).astimezone(JKT).date()
        self.assertEqual(att.foom_work_date, today_local)

    def test_backend_created_attendance_also_counts(self):
        """Baris yang dibuat HR lewat backend tidak punya foom_work_date, tapi
        tetap harus menutup hari — kalau tidak, batasnya gampang dilewati."""
        now = fields.Datetime.now()
        self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': now - timedelta(hours=3),
            'check_out': now - timedelta(hours=1),
        })
        token = self._login()
        self.assertEqual(self._punch(token, 'in')['error'], 'already_done_today')

    def test_yesterday_does_not_block_today(self):
        now = fields.Datetime.now()
        self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': now - timedelta(days=1, hours=3),
            'check_out': now - timedelta(days=1, hours=1),
        })
        token = self._login()
        self.assertTrue(self._punch(token, 'in')['ok'])

    def test_disabled_setting_allows_second_round(self):
        self._set_param('single_clock_in_per_day', '0')
        token = self._login()
        self._full_day(token)
        self.assertTrue(self._punch(token, 'in')['ok'],
                        "kalau setting dimatikan, absen kedua harus boleh")

    def test_other_employee_is_unaffected(self):
        other = self.Employee.create({
            'name': 'Rekan', 'tz': 'Asia/Jakarta',
            'foom_att_code': 'ZZTEST003', 'foom_att_pin_set': '556677',
            'foom_att_shift_id': self.shift_day.id,
            'foom_att_location_id': self.hq.id})
        self._full_day(self._login())
        token2 = self._post('login', {'code': 'ZZTEST003', 'pin': '556677'})['token']
        self.assertTrue(self._punch(token2, 'in')['ok'])
        self.assertTrue(other.attendance_state, 'checked_in')

    def test_overnight_shift_counts_as_one_day(self):
        """Clock in 22:00 dan clock out 06:00 esok harinya adalah SATU hari
        kerja — clock in berikutnya pada pagi yang sama harus ditolak."""
        local_now = pytz.utc.localize(fields.Datetime.now()).astimezone(JKT)
        # shift malam yang jendelanya sedang berjalan sekarang
        start_hour = (local_now.hour - 2) % 24
        night = self.Shift.create({
            'name': 'Malam Berjalan',
            'time_from': start_hour,
            'time_to': (start_hour + 8) % 24,
            'early_in_window_minutes': 60, 'late_out_window_minutes': 60,
            'location_ids': [(6, 0, self.hq.ids)], 'default_location_id': self.hq.id})
        self.employee.foom_att_shift_id = night
        token = self._login()
        self._full_day(token)
        self.assertEqual(self._punch(token, 'in')['error'], 'already_done_today')


@tagged('post_install', '-at_install')
class TestSelfiePhoto(FoomAttendanceCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self._set_param('min_punch_interval_sec', '0')
        self._set_param('single_clock_in_per_day', '0')
        self._set_param('require_photo', '1')
        self.env['foom.attendance.throttle'].search([]).unlink()

    def _post(self, path, payload):
        self.env.flush_all()
        response = self.url_open(
            '/foom/attendance/api/%s' % path,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'})
        self.env.invalidate_all()
        return response.json()

    def _punch(self, token, action, **extra):
        payload = {'token': token, 'action': action, 'latitude': HQ_LAT,
                   'longitude': HQ_LON, 'accuracy': 10}
        payload.update(extra)
        return self._post('punch', payload)

    def _login(self):
        return self._post('login', {'code': 'ZZTEST001', 'pin': PIN_OK})['token']

    # ------------------------------------------------------------------
    def test_photo_is_stored_and_marked_captured(self):
        token = self._login()
        body = self._punch(token, 'in', photo='data:image/jpeg;base64,' + TINY_JPEG)
        self.assertTrue(body['ok'], body)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertTrue(att.foom_in_photo)
        self.assertEqual(att.foom_in_photo_status, 'captured')
        self.assertFalse(att.foom_photo_missing)

    def test_punch_allowed_without_photo_but_flagged(self):
        token = self._login()
        body = self._punch(token, 'in', photo_status='denied')
        self.assertTrue(body['ok'], "kebijakan: absensi tetap diterima")
        att = self.Attendance.browse(body['attendance_id'])
        self.assertFalse(att.foom_in_photo)
        self.assertEqual(att.foom_in_photo_status, 'denied')
        self.assertTrue(att.foom_photo_missing)

    def test_unknown_reason_falls_back_to_failed(self):
        token = self._login()
        body = self._punch(token, 'in', photo_status='alasan-karangan')
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.foom_in_photo_status, 'failed')
        self.assertTrue(att.foom_photo_missing)

    def test_client_cannot_claim_captured_without_sending_a_photo(self):
        """`captured` hanya boleh disimpulkan server dari foto yang benar-benar
        diterima, bukan dari klaim klien."""
        token = self._login()
        body = self._punch(token, 'in', photo_status='captured')
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.foom_in_photo_status, 'failed')
        self.assertTrue(att.foom_photo_missing)

    def test_non_image_payload_is_rejected(self):
        """Endpoint publik ini tidak boleh jadi tempat menitipkan blob apa pun."""
        token = self._login()
        junk = base64.b64encode(b'ini bukan gambar, cuma teks biasa').decode()
        body = self._punch(token, 'in', photo='data:image/jpeg;base64,' + junk)
        self.assertTrue(body['ok'])
        att = self.Attendance.browse(body['attendance_id'])
        self.assertFalse(att.foom_in_photo, "blob non-gambar tidak boleh tersimpan")
        self.assertTrue(att.foom_photo_missing)

    def test_oversized_photo_is_rejected(self):
        token = self._login()
        body = self._punch(token, 'in', photo='data:image/jpeg;base64,' + 'A' * (4 * 1024 * 1024))
        self.assertTrue(body['ok'])
        self.assertFalse(self.Attendance.browse(body['attendance_id']).foom_in_photo)

    def test_photo_on_clock_out_too(self):
        token = self._login()
        self._punch(token, 'in', photo='data:image/jpeg;base64,' + TINY_JPEG)
        body = self._punch(token, 'out', photo='data:image/jpeg;base64,' + TINY_JPEG)
        att = self.Attendance.browse(body['attendance_id'])
        self.assertTrue(att.foom_out_photo)
        self.assertEqual(att.foom_out_photo_status, 'captured')

    def test_status_is_not_required_when_photo_is_off(self):
        self._set_param('require_photo', '0')
        token = self._login()
        body = self._punch(token, 'in')
        att = self.Attendance.browse(body['attendance_id'])
        self.assertEqual(att.foom_in_photo_status, 'not_required')
        self.assertFalse(att.foom_photo_missing)

    def test_page_serves_camera_not_file_input(self):
        """Regresi. `<input type="file" capture>` cuma saran — di banyak browser
        employee tetap bisa memilih foto lama dari galeri."""
        html = self.url_open('/foom/attendance').text
        self.assertIn('id="fa-cam"', html)
        self.assertNotIn('type="file"', html)
