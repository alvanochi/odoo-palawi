# -*- coding: utf-8 -*-
{
    'name': 'Foom Attendance — Public Clock In/Out + Geofence',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Absensi mandiri lewat halaman publik (kode + PIN), terikat shift '
               'dan radius lokasi kerja. Tanpa user internal Odoo.',
    'description': """
Foom Attendance
===============

Employee melakukan clock in / clock out dari HP masing-masing lewat halaman
publik ``/foom/attendance`` — tanpa perlu user internal Odoo.

Fitur
-----
* Login pakai **Kode Karyawan + PIN** (PIN disimpan ter-hash, bukan plaintext).
* Sesi bertoken berumur pendek, bisa dicabut, dengan proteksi brute force
  (lockout per employee + throttle per IP).
* **Geofence per Work Location**: titik lat/lon + radius meter, kebijakan
  Blokir / Izinkan-tapi-ditandai / Nonaktif.
* **Shift** custom: jam masuk/pulang, shift lintas hari, toleransi telat,
  jendela clock in/out, daftar lokasi yang diizinkan.
* **Roster** harian per employee (+ wizard generate massal).
* Perhitungan otomatis menit **telat** dan **pulang cepat**.
* Menulis ke ``hr.attendance`` standar, termasuk field geolokasi bawaan Odoo 18.
""",
    'author': 'Foom IT',
    'website': 'https://foom.id',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'security/foom_attendance_security.xml',
        'data/foom_attendance_data.xml',
        'data/ir_cron.xml',
        'views/foom_attendance_location_views.xml',
        'views/foom_attendance_shift_views.xml',
        'views/foom_attendance_roster_views.xml',
        'views/foom_attendance_session_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
        'views/res_config_settings_views.xml',
        'views/foom_attendance_public_templates.xml',
        'wizard/foom_attendance_roster_generate_views.xml',
        'views/foom_attendance_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
