# -*- coding: utf-8 -*-
"""Helper murni (tanpa state) yang dipakai lintas model & controller."""

import hashlib
import hmac
import math
import secrets
from datetime import datetime, time as dtime, timedelta

import pytz

PARAM_PREFIX = 'foom_attendance.'

#: radius bumi rata-rata (IUGG mean radius) dalam meter
EARTH_RADIUS_M = 6371008.8

# PENTING — kenapa semua boolean di sini default '0':
#
# `res.config.settings` menghapus baris `ir.config_parameter` ketika nilainya
# False atau 0 (lihat `res_config.set_values`). Jadi "parameter tidak ada"
# adalah satu-satunya cara sebuah checkbox tersimpan dalam keadaan mati.
# Kalau default di bawah diisi '1', mematikan checkbox tidak akan pernah
# berpengaruh — parameternya hilang lalu default '1' terbaca lagi.
#
# Nilai awal saat instalasi diisi lewat `data/foom_attendance_data.xml`,
# bukan lewat tabel ini.
DEFAULTS = {
    'public_enabled': '0',
    'default_radius_m': '150',
    'default_geofence_policy': 'block',
    'max_gps_accuracy_m': '0',        # 0 = tidak dicek
    'require_photo': '0',
    'require_reason_outside': '0',
    'session_minutes': '720',
    'pin_max_attempts': '5',
    'pin_lockout_minutes': '15',
    'ip_max_attempts': '30',
    'ip_window_minutes': '15',
    'min_punch_interval_sec': '0',    # 0 = tanpa jeda
    'allow_without_roster': '0',
    'single_clock_in_per_day': '0',
}


# --------------------------------------------------------------------------
# konfigurasi
# --------------------------------------------------------------------------
def get_param(env, name, default=None):
    if default is None:
        default = DEFAULTS.get(name)
    value = env['ir.config_parameter'].sudo().get_param(PARAM_PREFIX + name, default)
    return value


def get_int_param(env, name, default=None):
    try:
        return int(float(get_param(env, name, default)))
    except (TypeError, ValueError):
        return int(float(DEFAULTS.get(name) or 0))


def get_bool_param(env, name, default=None):
    value = get_param(env, name, default)
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'on')


# --------------------------------------------------------------------------
# geo
# --------------------------------------------------------------------------
def haversine_m(lat1, lon1, lat2, lon2):
    """Jarak great-circle dalam meter antara dua titik derajat desimal."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2.0) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def valid_coords(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if lat == 0.0 and lon == 0.0:
        # Null Island — hampir pasti hasil pembacaan GPS yang gagal
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


# --------------------------------------------------------------------------
# waktu
# --------------------------------------------------------------------------
def float_to_hm(value):
    """0.0-24.0 -> (jam, menit), dibulatkan ke menit terdekat."""
    value = max(0.0, float(value or 0.0))
    total = int(round(value * 60.0))
    return total // 60, total % 60


def local_naive_to_utc(day, float_hour, tz):
    """Gabungkan tanggal lokal + jam desimal lokal menjadi datetime UTC naive."""
    hours, minutes = float_to_hm(float_hour)
    extra_days, hours = divmod(hours, 24)
    naive = datetime.combine(day + timedelta(days=extra_days), dtime(hours, minutes))
    return tz.localize(naive).astimezone(pytz.utc).replace(tzinfo=None)


def employee_tz(employee):
    name = employee.sudo().tz or employee.sudo().company_id.resource_calendar_id.tz or 'UTC'
    try:
        return pytz.timezone(name)
    except pytz.UnknownTimeZoneError:
        return pytz.utc


def to_local(dt_naive_utc, tz):
    if not dt_naive_utc:
        return False
    return pytz.utc.localize(dt_naive_utc).astimezone(tz)


# --------------------------------------------------------------------------
# token
# --------------------------------------------------------------------------
def new_token():
    return secrets.token_urlsafe(36)


def hash_token(token):
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def constant_time_equals(a, b):
    return hmac.compare_digest((a or '').encode('utf-8'), (b or '').encode('utf-8'))


# --------------------------------------------------------------------------
# misc
# --------------------------------------------------------------------------
def filter_existing_vals(model, vals):
    """Buang key yang tidak ada di model — supaya tetap jalan kalau Odoo
    mengganti/menghapus field bawaan di versi lain."""
    known = model._fields
    return {k: v for k, v in vals.items() if k in known}
