# foom_attendance — Absensi Publik + Geofence (Odoo 18)

Employee clock in / clock out dari HP masing-masing lewat halaman publik
`/foom/attendance`, **tanpa user internal Odoo**. Identitas dipakai lewat
Kode Karyawan + PIN, jadwal diambil dari shift/roster, dan posisi divalidasi
terhadap radius lokasi kerja.

Dependency: `hr`, `hr_attendance`. Tidak butuh Enterprise.

---

## 1. Cara kerja singkat

```
HP employee                     Odoo (auth=public, semua akses via sudo)
-----------                     ----------------------------------------
POST /api/login   {code, pin} -> verifikasi PIN (hash) + throttle
                              <- token sesi (umur default 12 jam)
POST /api/state   {token}     <- status, shift hari ini, lokasi + radius
POST /api/punch   {token,        server yang memutuskan in/out, jarak,
                   lat, lon,     telat, di dalam/luar radius
                   accuracy,
                   note, photo} -> tulis ke hr.attendance
```

Tidak ada endpoint yang menerima `employee_id` dari klien — identitas selalu
dibaca dari token. Klien tidak bisa mengabsenkan orang lain.

Data ditulis ke `hr.attendance` standar (termasuk `in_latitude`,
`in_longitude`, `in_mode='kiosk'`, dst.), jadi semua laporan bawaan Odoo tetap
jalan. Field tambahan modul ini memakai prefix `foom_`.

## 2. Instalasi

1. Salin folder `foom_attendance` ke addons path.
2. Restart service, Update Apps List, install **Foom Attendance**.
3. Halaman publik **wajib diakses lewat HTTPS** — browser hanya memberikan
   `navigator.geolocation` pada origin yang aman (kecuali `localhost`).

## 3. Setup

### a. Lokasi (geofence)

**Absensi Publik ▸ Lokasi & Geofence**

| Field | Keterangan |
|---|---|
| Latitude / Longitude | dari Google Maps: klik kanan titik → angka pertama latitude |
| Radius (m) | default 150 |
| Kebijakan Geofence | `Blokir` / `Izinkan tapi ditandai` / `Tidak dicek` |

### b. Shift

**Absensi Publik ▸ Shift**

- `Jam Pulang <= Jam Masuk` otomatis dianggap **lintas hari**.
- **Toleransi Telat** — clock in dalam toleransi tidak dihitung telat.
- **Jendela** — seberapa awal / selama apa halaman menerima punch. Centang
  *Tolak di Luar Jendela* kalau punch di luar rentang itu harus ditolak
  (default: tetap dicatat tapi ditandai `Di Luar Jadwal`).
- **Lokasi yang Diizinkan** — kalau diisi lebih dari satu, sistem memakai
  lokasi **terdekat** dari posisi employee. Cocok untuk sales yang berputar
  antar outlet.

### c. Employee

Tab **Absensi Publik** di form employee:

- **Kode Absensi** — tombol *Buat Kode Otomatis* menghasilkan `F######`.
  Kalau dikosongkan, employee bisa login pakai Badge ID (`barcode`).
- **Set PIN Baru** — ketik lalu simpan. Disimpan sebagai hash
  (`werkzeug.security`), tidak pernah plaintext. Minimal 4 digit angka;
  PIN yang terlalu mudah (`1234`, `0000`, digit seragam) ditolak.
  Employee yang sudah punya PIN kiosk lama (`hr.employee.pin`) bisa langsung
  login sekali — PIN itu otomatis di-hash setelah pemakaian pertama.
- **Override Geofence** — isi *Tidak dicek* untuk employee lapangan.

### d. Roster

**Absensi Publik ▸ Roster**, atau **Generate Roster** untuk massal
(pilih employee, rentang tanggal, shift, hari kerja `0,1,2,3,4`).

Urutan penentuan jadwal saat punch:

```
baris roster tanggal tsb  ->  Shift Default employee  ->  tidak ada jadwal
```

Untuk shift lintas hari, roster **hari kemarin** juga ikut diuji, sehingga
clock out jam 02:00 tetap menempel ke shift malam kemarin.

Urutan penentuan lokasi:

```
lokasi di baris roster -> Lokasi yang Diizinkan pada shift -> Lokasi Default employee
```

### e. Satu absensi per hari kerja

Aktif secara default. Setelah employee clock in lalu clock out, tombolnya
berubah jadi **"Absensi hari ini selesai"** dan clock in berikutnya ditolak
(`already_done_today`).

Batas harinya adalah **hari shift**, bukan tengah malam kalender — jadi shift
malam 22:00–06:00 tetap dihitung satu hari walau melewati tengah malam.
Tanggalnya disimpan di kolom `foom_work_date` pada setiap baris absensi, dan
bisa dipakai untuk group by di laporan.

Baris absensi yang dibuat HR lewat backend atau systray **ikut terhitung**,
walaupun tidak punya `foom_work_date` — pengecekan juga melihat rentang waktu
`check_in`. Kalau tidak begitu, employee bisa absen dua kali hanya karena baris
pertamanya tidak dibuat lewat halaman publik.

Matikan lewat **Settings ▸ Satu Absensi per Hari** kalau ada divisi yang memang
perlu absen beberapa kali sehari.

### f. Foto selfie

Kalau **Minta Foto Selfie** diaktifkan, halaman menyalakan **kamera depan
langsung** (`getUserMedia`) — employee menekan *Ambil Foto*, gambarnya
di-resize ke 720 px dan dikirim sebagai JPEG.

Yang penting: ini **bukan** `<input type="file" capture="user">`. Atribut
`capture` hanya saran, dan di banyak browser employee tetap bisa memilih foto
lama dari galeri. Dengan `getUserMedia`, gambar hanya bisa berasal dari kamera
saat itu juga.

Kalau kamera tidak bisa dipakai — izin ditolak, perangkat tanpa kamera, atau
halaman diakses tanpa HTTPS — **absensi tetap diterima** tapi barisnya ditandai:

| Field | Isi |
|---|---|
| `foom_in_photo_status` / `foom_out_photo_status` | `captured`, `denied`, `no_camera`, `insecure`, `failed`, `not_required` |
| `foom_photo_missing` | `True` kalau foto diminta tapi tidak didapat |

HR bisa memfilter lewat **Foto tidak ada** di layar Attendances. Karena alasan
kegagalan dilaporkan oleh klien, ini adalah **catatan audit, bukan penegakan** —
yang dijamin adalah barisnya tidak akan terlihat bersih seolah foto tidak
pernah diminta.

Kamera dilepas otomatis setelah memotret dan saat halaman di-background,
supaya lampu kamera tidak menyala terus dan baterai tidak terkuras.

### g. Settings

**Settings ▸ Attendances ▸ Absensi Publik (Foom)**

| Setting | Default |
|---|---|
| Halaman Absensi Publik | aktif |
| Kebijakan Geofence Default | Blokir |
| Radius Default | 150 m |
| Akurasi GPS Maksimum | 100 m (0 = tidak dicek) |
| Satu Absensi per Hari | aktif |
| Minta Foto Selfie | mati |
| Wajib Alasan bila di luar radius | aktif |
| Izinkan absen tanpa jadwal shift | aktif |
| Umur sesi | 720 menit |
| Kunci setelah salah PIN | 5 kali / 15 menit |
| Batas per IP | 30 percobaan / 15 menit |
| Jeda minimum antar punch | 60 detik |

> **Catatan teknis.** Odoo menghapus baris `ir.config_parameter` ketika sebuah
> checkbox dimatikan atau angka diisi 0. Karena itu di modul ini
> "parameter tidak ada" **selalu** berarti mati/nol, dan nilai awal yang
> menyala di-seed lewat `data/foom_attendance_data.xml` (noupdate). Jangan
> mengubah `DEFAULTS` di `models/utils.py` menjadi `'1'` — checkbox tidak akan
> pernah bisa dimatikan.

## 4. Keamanan

| Ancaman | Mitigasi |
|---|---|
| Tebak PIN | Tiga lapis: per IP (30×/15 mnt), per (employee, IP) (5×/15 mnt), dan rem longgar per employee (20×/60 mnt). Kode karyawan salah, employee dinonaktifkan, dan akun terkunci semuanya menghasilkan respons yang **persis sama**, jadi kode karyawan tidak bisa dienumerasi. |
| Enumerasi lewat wildcard | Input kode di-escape sebelum masuk `=ilike`; `%` dan `_` tidak lagi berfungsi sebagai wildcard. |
| Absen dari mana saja karena lokasi belum diatur | Gagal tertutup: kalau kebijakan `Blokir` tapi tidak ada lokasi yang bisa diselesaikan, punch ditolak dengan `no_location_configured`. |
| Ambang akurasi GPS dilewati | Request tanpa field `accuracy` ikut ditolak, bukan dianggap lolos. |
| Token dipakai employee yang sudah diarsipkan | `_resolve` mensyaratkan `employee_id.active = True`. |
| PIN bocor dari dump DB | PIN disimpan sebagai hash `werkzeug.security`, bukan plaintext seperti `hr.employee.pin` bawaan. |
| Token dicuri | Token hanya ada di respons pertama; DB menyimpan SHA-256-nya. Token **tidak pernah** muncul di URL (foto profil dikirim inline sebagai data URI) supaya tidak bocor lewat access log, history, atau header `Referer`. Bisa dicabut per sesi (**Sesi Perangkat**) atau per employee, dan umurnya terbatas. |
| Absen buat orang lain | Tidak ada endpoint yang menerima `employee_id`; semuanya dari token. |
| Jam HP dimundurkan | Waktu yang dicatat adalah `fields.Datetime.now()` di server. |
| Double punch / dobel klik | Aksi ditentukan server dari `attendance_state`, plus jeda minimum antar punch. |
| GPS asal-asalan | Ambang akurasi (`accuracy`) menolak pembacaan berbasis IP/wifi yang kasar; koordinat 0,0 ditolak. |
| Titip absen / absen dua kali sehari | Batas satu absensi per hari kerja, dihitung dari hari shift dan mencakup baris yang dibuat lewat backend. |
| Selfie pakai foto lama dari galeri | Foto diambil langsung lewat `getUserMedia`, bukan `<input type="file">`. Isi gambar diperiksa sampai magic byte JPEG/PNG, jadi endpoint ini juga tidak bisa dipakai menitipkan blob sembarangan ke `ir.attachment`. |

**Yang TIDAK bisa dicegah dari browser:** aplikasi *mock location* / GPS palsu
di Android. Browser tidak mengekspos flag `isFromMockProvider`. Kalau ini jadi
risiko nyata, opsinya: aplikasi native, atau kombinasi bukti lain (selfie wajib
+ audit `foom_outside` + IP kantor).

**Trade-off yang disengaja — DoS ringan.** Rem per-employee (20 percobaan
gagal dalam 60 menit) bisa dipakai orang luar untuk mengunci satu employee
selama 15 menit, asal dia menebak kode karyawannya. Tanpa rem itu, penyerang
dengan banyak IP bisa menebak PIN 4 digit tanpa batas. Kalau gangguan ini lebih
mengkhawatirkan daripada brute force, naikkan **Kunci setelah** atau kosongkan
`foom_att_locked_until` lewat tombol *Buka Kunci* di form employee. Memakai PIN
6 digit membuat rem ini jauh lebih longgar tanpa kehilangan keamanan.

## 5. Model

| Model | Isi |
|---|---|
| `foom.attendance.location` | titik lat/lon, radius, kebijakan geofence |
| `foom.attendance.shift` | jam masuk/pulang, toleransi, jendela, lokasi |
| `foom.attendance.roster` | jadwal harian per employee (unik per employee+tanggal) |
| `foom.attendance.session` | sesi bertoken perangkat |
| `foom.attendance.throttle` | penghitung percobaan login |
| `foom.attendance.roster.generate` | wizard generate roster |

Field tambahan di `hr.attendance`: `foom_shift_id`, `foom_roster_id`,
`foom_in_location_id` / `foom_out_location_id`, `foom_in_distance_m` /
`foom_out_distance_m`, `foom_in_accuracy_m` / `foom_out_accuracy_m`,
`foom_in_outside` / `foom_out_outside` / `foom_outside`, `foom_planned_in` /
`foom_planned_out`, `foom_late_minutes`, `foom_early_leave_minutes`,
`foom_in_geo_checked` / `foom_out_geo_checked` (membedakan "0 m karena benar-benar
di titik lokasi" dari "jarak tidak pernah diukur"),
`foom_off_schedule`, `foom_work_date`, `foom_in_note` / `foom_out_note`,
`foom_in_photo_status` / `foom_out_photo_status` / `foom_photo_missing`,
`foom_in_photo` / `foom_out_photo`, `foom_source`.

## 6. Endpoint

Semua `POST`, `Content-Type: application/json`, `auth=public`, `csrf=False`.

| Path | Body | Balasan |
|---|---|---|
| `/foom/attendance/api/login` | `{code, pin}` | `{ok, token, expire_at, ...state}` |
| `/foom/attendance/api/state` | `{token}` | `{ok, employee, state, schedule, geofence, today}` |
| `/foom/attendance/api/punch` | `{token, action, latitude, longitude, accuracy, note, photo}` | `{ok, action, message, attendance_id, ...state}` |
| `/foom/attendance/api/logout` | `{token}` | `{ok}` |

Kode error yang mungkin muncul di `error`: `disabled`, `missing`, `invalid`,
`throttled`, `unauthorized`, `disabled_employee`, `state_mismatch`,
`too_soon`, `no_schedule`, `day_off`, `outside_window`, `no_location`,
`no_location_configured`, `bad_accuracy`, `outside_geofence`, `reason_required`,
`already_done_today`, `already_in`, `not_in`, `rejected`, `server_error`.

Karena bentuknya JSON biasa (bukan JSON-RPC), endpoint yang sama bisa dipakai
bot WhatsApp atau aplikasi native nanti tanpa perubahan.

## 7. Menjalankan test

### a. Test otomatis (131 test)

Ada di folder `tests/`, memakai kerangka test bawaan Odoo. Jalankan di
database **staging atau scratch**, jangan di produksi:

```bash
odoo-bin -d nama_db -u foom_attendance \
         --test-enable --test-tags /foom_attendance --stop-after-init
```

Semua test memakai transaksi yang di-rollback, jadi tidak meninggalkan data.
Kode karyawan yang dipakai fixture (`ZZTEST001`, `ZZTEST002`, `ZZTEST009`)
sengaja dipilih supaya tidak bentrok dengan kode sungguhan.

| Berkas | Cakupan |
|---|---|
| `test_geofence.py` | haversine, jarak, pemilihan lokasi terdekat, resolusi kebijakan, batas koordinat |
| `test_shift.py` | shift lintas hari, konversi zona waktu, jendela punch, validasi jam |
| `test_schedule.py` | roster vs shift default, clock out dini hari, jendela yang membuka sebelum tengah malam, dan **regresi** fallback yang tidak boleh mencomot jadwal hari lain |
| `test_security.py` | hashing PIN, PIN lemah, escape wildcard, sesi & pencabutan, throttle |
| `test_config.py` | semantik parameter yang dihapus Odoo saat checkbox dimatikan |
| `test_roster_wizard.py` | generate massal, skip/overwrite, validasi rentang |
| `test_public_api.py` | endpoint HTTP sungguhan: login, throttle, geofence, clock in/out, dan bahwa tidak ada cara mengabsenkan orang lain |
| `test_single_punch.py` | batas satu absensi per hari kerja (termasuk shift lintas hari dan baris buatan backend) + status foto selfie |

Test bertanda **regresi** mengunci bug yang pernah nyata ada di modul ini —
jangan dihapus kalau suatu saat gagal; itu tandanya bug-nya kembali.

### b. Smoke test manual — `tools/smoke_test.sh`

Untuk memeriksa instance yang **sudah jalan** (setelah deploy, atau setelah
mengubah setting). Skrip ini membuat absensi sungguhan, jadi pakai employee uji.

```bash
./tools/smoke_test.sh https://odoo.foom.id F100001 482913 -6.2001 106.8167
```

Argumen: URL, kode karyawan, PIN, lalu koordinat yang memang **di dalam**
radius lokasi employee tersebut. Skrip memeriksa 15 hal — termasuk bahwa kode
karyawan tidak bisa dienumerasi, wildcard `%` tidak tembus, titik jauh ditolak,
dan token mati setelah logout — lalu mencetak ringkasan pass/fail.

## 8. Yang perlu diuji sebelum produksi

Sisi server sudah tercakup test otomatis di atas. Yang tersisa adalah hal-hal
yang hanya bisa dibuktikan di perangkat sungguhan:

1. Install di database staging (`-u foom_attendance`) lalu jalankan test suite —
   log harus bersih dan 131 test hijau.
2. Buat 1 lokasi, 1 shift, isi kode + PIN pada 1 employee uji, jalankan
   `tools/smoke_test.sh` terhadap staging.
3. **Buka `/foom/attendance` dari HP sungguhan lewat HTTPS.** Pastikan browser
   meminta izin lokasi, angka jarak berjalan, dan tombol aktif hanya setelah
   GPS terbaca.
4. Uji **foto selfie** (kalau disetel wajib) dari kamera depan HP.
5. Uji di lokasi kerja yang asli: berdiri di dalam gedung, di parkiran, dan di
   luar pagar — lihat apakah radius yang dipilih masuk akal atau perlu
   dilonggarkan. Akurasi GPS di dalam gedung sering jelek.
6. Uji dengan jaringan lambat / sinyal naik-turun.
