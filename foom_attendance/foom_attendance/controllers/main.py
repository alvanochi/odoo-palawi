# -*- coding: utf-8 -*-
"""Endpoint publik untuk absensi mandiri.

Semua route berjalan sebagai user publik dan mengakses data lewat ``sudo()``.
Batas keamanannya ada di dua tempat:

1. kode karyawan + PIN (di-hash) untuk mendapatkan token sesi;
2. token sesi berumur pendek yang wajib dikirim di tiap panggilan berikutnya.

Tidak ada endpoint yang menerima ``employee_id`` dari klien — identitas selalu
diambil dari token, jadi klien tidak bisa mengabsenkan orang lain.
"""

import base64
import binascii
import json
import logging
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools.image import image_data_uri

from ..models import utils

_logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_NOTE_LEN = 250

#: Hash pembanding untuk jalur login yang gagal. Tanpa ini, permintaan dengan
#: kode karyawan yang tidak ada langsung kembali dalam hitungan milidetik
#: sementara kode yang benar menunggu pbkdf2 selesai — selisih waktunya cukup
#: untuk memetakan kode mana yang nyata.
_DUMMY_PIN_HASH = generate_password_hash('0' * 12)


def _json_response(payload, status=200):
    return request.make_json_response(payload, status=status)


def _error(code, message, status=200, **extra):
    payload = {'ok': False, 'error': code, 'message': message}
    payload.update(extra)
    return _json_response(payload, status=status)


def _body():
    try:
        raw = request.httprequest.get_data(as_text=True) or '{}'
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _client_ip():
    return request.httprequest.remote_addr or '0.0.0.0'


def _user_agent():
    return request.httprequest.headers.get('User-Agent', '')[:256]


def _clean_text(value, limit=MAX_NOTE_LEN):
    if not isinstance(value, str):
        return ''
    return value.strip()[:limit]


def _to_float(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


#: magic byte awal JPEG dan PNG — satu-satunya format yang dikirim halaman ini
_IMAGE_MAGIC = (b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n')


def _decode_photo(value):
    """Terima data URL atau base64 polos, kembalikan bytes base64 siap simpan.

    Isinya diperiksa sampai magic byte: tanpa itu, endpoint publik ini bisa
    dipakai menitipkan blob apa pun ke `ir.attachment`.
    """
    if not value or not isinstance(value, str):
        return None
    if value.startswith('data:'):
        _head, _sep, value = value.partition(',')
        if not _sep:
            return None
    value = value.strip()
    if len(value) > MAX_PHOTO_BYTES:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw.startswith(_IMAGE_MAGIC):
        return None
    return value.encode('ascii')


class FoomAttendancePublic(http.Controller):

    # ==================================================================
    # halaman
    # ==================================================================
    @http.route('/foom/attendance', type='http', auth='public', methods=['GET'])
    def page(self, **kw):
        env = request.env
        if not utils.get_bool_param(env, 'public_enabled'):
            return request.render('foom_attendance.public_disabled', {})
        company = env.company
        values = {
            'company_name': company.name if company else 'Odoo',
            'require_photo': utils.get_bool_param(env, 'require_photo'),
            'max_accuracy': utils.get_int_param(env, 'max_gps_accuracy_m'),
        }
        response = request.render('foom_attendance.public_page', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    # ==================================================================
    # login
    # ==================================================================
    @http.route('/foom/attendance/api/login', type='http', auth='public',
                methods=['POST'], csrf=False)
    def api_login(self, **kw):
        env = request.env
        if not utils.get_bool_param(env, 'public_enabled'):
            return _error('disabled', _("Halaman absensi sedang dinonaktifkan."))

        data = _body()
        code = _clean_text(data.get('code'), 32)
        pin = _clean_text(data.get('pin'), 12)
        if not code or not pin:
            return _error('missing', _("Kode karyawan dan PIN wajib diisi."))

        Throttle = env['foom.attendance.throttle'].sudo()
        ip_key = 'ip:%s' % _client_ip()
        if Throttle._is_blocked(ip_key):
            return _error('throttled', _("Terlalu banyak percobaan dari perangkat ini. "
                                         "Coba lagi nanti."), status=429)

        employee = env['hr.employee'].sudo()._foom_find_by_code(code)
        max_attempts = utils.get_int_param(env, 'pin_max_attempts')
        lockout = utils.get_int_param(env, 'pin_lockout_minutes')
        # Kunci ketat per (kode yang dicoba, IP) — sengaja memakai kode mentah,
        # BUKAN id employee. Kalau memakai id, kode yang tidak ada tidak pernah
        # memicu 429, dan perbedaan 401-vs-429 itu sendiri sudah cukup untuk
        # memetakan kode karyawan mana yang nyata.
        pair_key = 'code:%s@%s' % (code.lower(), _client_ip())
        emp_key = 'emp:%s' % employee.id if employee else None

        def _fail():
            """Satu-satunya jalan keluar untuk semua kegagalan login.

            Kode karyawan salah, employee dinonaktifkan, dan akun terkunci
            memberi jawaban yang persis sama — kalau tidak, respons yang
            berbeda membocorkan kode karyawan mana yang benar-benar ada.
            """
            check_password_hash(_DUMMY_PIN_HASH, pin)  # samakan waktu respons
            Throttle._register_failure(
                ip_key, utils.get_int_param(env, 'ip_max_attempts'),
                utils.get_int_param(env, 'ip_window_minutes'), lockout)
            Throttle._register_failure(pair_key, max_attempts, lockout, lockout)
            if employee:
                # Rem kedua, jauh lebih longgar, membatasi laju tebakan
                # terdistribusi. Ini memang bisa dipakai untuk mengganggu satu
                # employee — lihat catatan DoS di README.
                until = Throttle._register_failure(
                    emp_key, max(max_attempts * 4, 8), 60, lockout)
                if until:
                    employee.write({'foom_att_locked_until': until})
            return _error('invalid', _("Kode karyawan atau PIN salah."), status=401)

        if Throttle._is_blocked(pair_key):
            # Kombinasi ini sudah gagal berkali-kali dari perangkat yang sama,
            # jadi tidak ada informasi baru yang bocor kalau alasannya disebut.
            return _error('throttled', _("Terlalu banyak percobaan dari perangkat ini. "
                                         "Coba lagi nanti."), status=429)
        if not employee:
            return _fail()
        if not employee.foom_att_enabled:
            return _fail()
        if employee.foom_att_locked_until and employee.foom_att_locked_until > fields.Datetime.now():
            return _fail()
        if not employee.foom_verify_pin(pin):
            return _fail()

        Throttle._register_success(ip_key)
        Throttle._register_success(pair_key)
        Throttle._register_success(emp_key)
        if employee.foom_att_locked_until:
            employee.write({'foom_att_locked_until': False})

        session, token = env['foom.attendance.session'].sudo()._issue(
            employee, ip=_client_ip(), user_agent=_user_agent())
        payload = {'ok': True, 'token': token, 'expire_at': str(session.expire_at)}
        payload.update(self._state_payload(employee))
        return _json_response(payload)

    @http.route('/foom/attendance/api/logout', type='http', auth='public',
                methods=['POST'], csrf=False)
    def api_logout(self, **kw):
        session = request.env['foom.attendance.session'].sudo()._resolve(
            _clean_text(_body().get('token'), 128))
        if session:
            session.action_revoke()
        return _json_response({'ok': True})

    # ==================================================================
    # state
    # ==================================================================
    @http.route('/foom/attendance/api/state', type='http', auth='public',
                methods=['POST'], csrf=False)
    def api_state(self, **kw):
        session = request.env['foom.attendance.session'].sudo()._resolve(
            _clean_text(_body().get('token'), 128))
        if not session:
            return _error('unauthorized', _("Sesi berakhir. Silakan masuk lagi."), status=401)
        employee = session.employee_id.sudo()
        if not employee.foom_att_enabled:
            session.action_revoke()
            return _error('disabled_employee',
                          _("Absensi publik untuk karyawan ini dinonaktifkan."), status=403)
        payload = {'ok': True}
        payload.update(self._state_payload(employee))
        return _json_response(payload)

    # ==================================================================
    # punch
    # ==================================================================
    @http.route('/foom/attendance/api/punch', type='http', auth='public',
                methods=['POST'], csrf=False)
    def api_punch(self, **kw):
        env = request.env
        if not utils.get_bool_param(env, 'public_enabled'):
            return _error('disabled', _("Halaman absensi sedang dinonaktifkan."))

        data = _body()
        session = env['foom.attendance.session'].sudo()._resolve(
            _clean_text(data.get('token'), 128))
        if not session:
            return _error('unauthorized', _("Sesi berakhir. Silakan masuk lagi."), status=401)

        employee = session.employee_id.sudo()
        if not employee.foom_att_enabled:
            session.action_revoke()
            return _error('disabled_employee',
                          _("Absensi publik untuk karyawan ini dinonaktifkan."), status=403)

        try:
            return self._do_punch(session, employee, data)
        except (ValidationError, UserError) as exc:
            # mis. constraint tumpang tindih check in/out dari hr_attendance
            request.env.cr.rollback()
            return _error('rejected', exc.args[0] if exc.args else _("Absensi ditolak."))
        except Exception:  # noqa: BLE001 — jangan sampai traceback bocor ke publik
            _logger.exception("foom_attendance: punch gagal untuk employee %s", employee.id)
            request.env.cr.rollback()
            return _error('server_error',
                          _("Terjadi kesalahan di server. Coba lagi sebentar."), status=500)

    # ------------------------------------------------------------------
    def _do_punch(self, session, employee, data):
        env = request.env
        now = fields.Datetime.now()

        requested = data.get('action')
        if requested not in (None, '', 'in', 'out'):
            return _error('bad_action', _("Aksi tidak dikenal."))

        state = employee.attendance_state
        server_action = 'out' if state == 'checked_in' else 'in'
        if requested and requested != server_action:
            payload = {'ok': False, 'error': 'state_mismatch',
                       'message': _("Status absensi sudah berubah. Layar disegarkan.")}
            payload.update(self._state_payload(employee))
            return _json_response(payload)
        action = server_action

        # -- jeda antar punch ------------------------------------------
        interval = utils.get_int_param(env, 'min_punch_interval_sec')
        last = employee.last_attendance_id
        last_ts = (last.check_out or last.check_in) if last else False
        if interval > 0 and last_ts and (now - last_ts).total_seconds() < interval:
            return _error('too_soon', _("Tunggu sebentar sebelum menekan tombol lagi."))

        # -- jadwal ----------------------------------------------------
        schedule = employee.foom_resolve_schedule(now)
        shift = schedule['shift']
        allow_without_roster = utils.get_bool_param(env, 'allow_without_roster')
        if not shift and not allow_without_roster:
            return _error('no_schedule',
                          _("Belum ada jadwal shift untuk hari ini. Hubungi HR."))
        if schedule['day_off'] and not allow_without_roster:
            return _error('day_off', _("Hari ini dijadwalkan libur."))
        if shift and shift.enforce_window and not schedule['in_window']:
            return _error('outside_window',
                          _("Di luar jendela waktu shift %s.", shift.display_name))

        # -- satu absensi per hari kerja --------------------------------
        if action == 'in' and utils.get_bool_param(env, 'single_clock_in_per_day'):
            done = employee.foom_completed_attendance(schedule)
            if done:
                payload = {
                    'ok': False, 'error': 'already_done_today',
                    'message': _("Absensi hari ini sudah selesai (masuk %(i)s, pulang %(o)s). "
                                 "Hubungi HR kalau perlu koreksi.",
                                 i=self._fmt_local(employee, done.check_in) or '-',
                                 o=self._fmt_local(employee, done.check_out) or '-'),
                }
                payload.update(self._state_payload(employee))
                return _json_response(payload)

        # -- posisi ----------------------------------------------------
        lat = _to_float(data.get('latitude'))
        lon = _to_float(data.get('longitude'))
        accuracy = _to_float(data.get('accuracy'))
        note = _clean_text(data.get('note'))
        photo = _decode_photo(data.get('photo'))

        locations = employee.foom_candidate_locations(schedule)
        location, distance = (locations.nearest_to(lat, lon) if locations
                              else (locations, None))
        policy = employee.foom_effective_policy(location)

        outside = False
        geo_checked = False
        if policy != 'off':
            if not utils.valid_coords(lat, lon):
                return _error('no_location',
                              _("Lokasi belum terbaca. Aktifkan GPS dan izinkan akses lokasi."))
            max_acc = utils.get_int_param(env, 'max_gps_accuracy_m')
            # `accuracy is None` ikut ditolak: kalau tidak, siapa pun bisa
            # melewati ambang akurasi cukup dengan tidak mengirim field-nya.
            if max_acc > 0 and (accuracy is None or accuracy > max_acc):
                return _error('bad_accuracy',
                              _("Akurasi GPS %(a)s m terlalu rendah (maksimum %(m)s m). "
                                "Pindah ke tempat terbuka lalu coba lagi.",
                                a=int(accuracy) if accuracy is not None else '?', m=max_acc))
            if not location:
                # Gagal tertutup. Kalau blok ini dilewati, employee tanpa
                # roster/shift/lokasi default bisa absen dari mana saja
                # walaupun kebijakannya "Blokir".
                if policy == 'block':
                    return _error('no_location_configured',
                                  _("Belum ada lokasi kerja yang ditetapkan untuk kamu. "
                                    "Hubungi HR."))
            else:
                radius = location.radius_m or utils.get_int_param(env, 'default_radius_m')
                geo_checked = distance is not None
                outside = distance is None or distance > radius
                if outside and policy == 'block':
                    return _error(
                        'outside_geofence',
                        _("Kamu berada %(d)s m dari %(loc)s, di luar radius %(r)s m.",
                          d=int(distance or 0), loc=location.name, r=radius),
                        distance=int(distance or 0), radius=radius, location=location.name)
                if outside and utils.get_bool_param(env, 'require_reason_outside') and not note:
                    return _error('reason_required',
                                  _("Kamu di luar radius lokasi. Tulis alasannya dulu."),
                                  need_reason=True, distance=int(distance or 0))

        # -- foto selfie -------------------------------------------------
        # Kebijakan yang dipilih: absensi tanpa foto TETAP diterima, tapi
        # barisnya ditandai supaya HR bisa mengaudit. Karena itu di sini tidak
        # ada `return` — hanya penentuan status.
        if utils.get_bool_param(env, 'require_photo'):
            photo_status = env['hr.attendance']._foom_photo_status(
                bool(photo), _clean_text(data.get('photo_status'), 20))
        else:
            photo_status = 'captured' if photo else 'not_required'

        # -- tulis ke hr.attendance ------------------------------------
        Attendance = env['hr.attendance'].sudo()
        ip, browser = _client_ip(), _user_agent()

        if action == 'in':
            if state == 'checked_in':
                return _error('already_in', _("Kamu sudah tercatat masuk."))
            late = 0
            if schedule['planned_in'] and shift:
                grace = shift.grace_in_minutes or 0
                late = Attendance._foom_minutes_between(now, schedule['planned_in']) - grace
                late = max(0, late)
            vals = {
                'employee_id': employee.id,
                'check_in': now,
                'foom_source': 'public',
                'foom_shift_id': shift.id if shift else False,
                'foom_roster_id': schedule['roster'].id if schedule['roster'] else False,
                'foom_in_location_id': location.id if location else False,
                'foom_in_distance_m': distance if distance is not None else 0.0,
                'foom_in_accuracy_m': accuracy if accuracy is not None else 0.0,
                'foom_in_outside': outside,
                'foom_in_geo_checked': geo_checked,
                'foom_planned_in': schedule['planned_in'] or False,
                'foom_planned_out': schedule['planned_out'] or False,
                'foom_off_schedule': not schedule['in_window'],
                'foom_late_minutes': late,
                'foom_in_note': note,
                'foom_work_date': schedule['day'],
                'foom_in_photo_status': photo_status,
            }
            if photo:
                vals['foom_in_photo'] = photo
            vals.update(Attendance._foom_write_native_geo('in', lat, lon, ip, browser))
            attendance = Attendance.create(vals)
            message = _("Clock in tercatat %s.", self._fmt_local(employee, now))
        else:
            attendance = last
            if not attendance or attendance.check_out:
                return _error('not_in', _("Tidak ada catatan clock in yang terbuka."))
            early = 0
            planned_out = attendance.foom_planned_out or schedule['planned_out']
            if planned_out and shift:
                grace = shift.grace_out_minutes or 0
                early = Attendance._foom_minutes_between(planned_out, now) - grace
                early = max(0, early)
            vals = {
                'check_out': now,
                'foom_out_location_id': location.id if location else False,
                'foom_out_distance_m': distance if distance is not None else 0.0,
                'foom_out_accuracy_m': accuracy if accuracy is not None else 0.0,
                'foom_out_outside': outside,
                'foom_out_geo_checked': geo_checked,
                'foom_early_leave_minutes': early,
                'foom_out_note': note,
                'foom_out_photo_status': photo_status,
            }
            if not attendance.foom_work_date:
                # baris dibuka lewat backend / systray — lengkapi supaya batas
                # satu absensi per hari tetap mengenalinya
                vals['foom_work_date'] = schedule['day']
            if photo:
                vals['foom_out_photo'] = photo
            if not attendance.foom_source or attendance.foom_source == 'backend':
                vals['foom_source'] = 'public'
            vals.update(Attendance._foom_write_native_geo('out', lat, lon, ip, browser))
            attendance.write(vals)
            message = _("Clock out tercatat %s.", self._fmt_local(employee, now))

        session.punch_count += 1
        employee.invalidate_recordset(
            ['attendance_state', 'last_attendance_id', 'hours_today'])

        payload = {'ok': True, 'action': action, 'message': message,
                   'attendance_id': attendance.id,
                   'outside_geofence': outside,
                   'distance_m': int(distance) if distance is not None else None}
        payload.update(self._state_payload(employee))
        return _json_response(payload)

    # ==================================================================
    # helper payload
    # ==================================================================
    def _fmt_local(self, employee, dt_utc):
        tz = utils.employee_tz(employee)
        local = utils.to_local(dt_utc, tz)
        return local.strftime('%H:%M') if local else ''

    def _state_payload(self, employee):
        env = request.env
        employee = employee.sudo()
        now = fields.Datetime.now()
        schedule = employee.foom_resolve_schedule(now)
        tz = schedule['tz']
        shift = schedule['shift']
        locations = employee.foom_candidate_locations(schedule)
        policy = employee.foom_effective_policy(locations[:1] if locations else locations)

        today_local = utils.to_local(now, tz).date()
        start = utils.local_naive_to_utc(today_local, 0.0, tz)
        floor = utils.local_naive_to_utc(today_local - timedelta(days=2), 0.0, tz)
        # Shift malam yang dimulai kemarin harus tetap terlihat, kalau tidak
        # employee melihat status "sedang bekerja" di atas daftar kosong dan
        # baris yang mau dia tutup justru tidak muncul.
        lines = env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', floor),
            '|', '|',
            ('check_in', '>=', start),
            ('check_out', '=', False),
            # tanpa lengan ini, baris shift malam yang baru saja ditutup langsung
            # hilang dari respons clock out yang mengabarkan keberhasilannya
            ('check_out', '>=', start),
        ], order='check_in asc', limit=20)

        def _loc(loc):
            return {
                'id': loc.id, 'name': loc.name,
                'latitude': loc.latitude, 'longitude': loc.longitude,
                'radius_m': loc.radius_m or utils.get_int_param(env, 'default_radius_m'),
                # kebijakan per lokasi supaya klien memakai kebijakan lokasi
                # terdekat, sama seperti yang nanti dipakai server saat punch
                'policy': employee.foom_effective_policy(loc),
            }

        # avatar_128 bisa berupa SVG yang dibuat otomatis (employee tanpa foto),
        # jadi mime-nya harus dibaca dari isi datanya, bukan diasumsikan PNG.
        state = employee.attendance_state or 'checked_out'
        single = utils.get_bool_param(env, 'single_clock_in_per_day')
        day_done = bool(single and state != 'checked_in'
                        and employee.foom_completed_attendance(schedule))

        avatar = employee.avatar_128 or b''
        if isinstance(avatar, str):
            avatar = avatar.encode('ascii', 'ignore')
        return {
            'employee': {
                'name': employee.name,
                'job': employee.job_title or (employee.job_id.name or ''),
                'department': employee.department_id.name or '',
                'code': employee.foom_att_code or employee.barcode or '',
                # dikirim inline supaya token sesi tidak perlu muncul di URL
                # gambar (URL bocor ke access log, history, dan Referer)
                'avatar': image_data_uri(avatar) if avatar else '',
            },
            'state': state,
            'day_done': day_done,
            'server_time': utils.to_local(now, tz).strftime('%Y-%m-%d %H:%M:%S'),
            'timezone': str(tz),
            'schedule': {
                'day': str(schedule['day']),
                'day_off': schedule['day_off'],
                'in_window': schedule['in_window'],
                'shift_name': shift.display_name if shift else '',
                'planned_in': self._fmt_local(employee, schedule['planned_in']),
                'planned_out': self._fmt_local(employee, schedule['planned_out']),
                'has_roster': bool(schedule['roster']),
            },
            'geofence': {
                'policy': policy,
                'locations': [_loc(loc) for loc in locations],
            },
            'options': {
                'require_photo': utils.get_bool_param(env, 'require_photo'),
                'require_reason_outside': utils.get_bool_param(env, 'require_reason_outside'),
                'max_accuracy_m': utils.get_int_param(env, 'max_gps_accuracy_m'),
                'single_clock_in_per_day': single,
            },
            'today': [{
                'check_in': self._fmt_local(employee, line.check_in),
                'check_out': self._fmt_local(employee, line.check_out),
                'worked_hours': round(line.worked_hours or 0.0, 2),
                'late_minutes': line.foom_late_minutes,
                'outside': line.foom_outside,
            } for line in lines],
        }
