# Tasks — FOOM Sales Dashboard

Urutan dijaga agar modul tetap installable setelah setiap kelompok task.

- [x] **1. Scaffold modul + manifest**
      - Files: `__init__.py`, `__manifest__.py`, `models/__init__.py`, `static/description/icon.png`
      - Covers: REQ-17
      - Done when: `odoo-bin -u foom_sales_dashboard` sukses, modul tampil di Apps

- [x] **2. Bundle Chart.js**
      - Files: `static/lib/chartjs/chart.umd.js`
      - Covers: risiko "Chart.js versi Odoo berubah"
      - Done when: file UMD Chart.js 4.x ada dan terdaftar di `web.assets_backend`

- [x] **3. Model SQL view `foom.sales.report`**
      - Files: `models/foom_sales_report.py`, `models/__init__.py`
      - Covers: REQ-1, REQ-2, REQ-3, REQ-4, REQ-6
      - Done when: upgrade bersih dan `SELECT * FROM foom_sales_report LIMIT 5` mengembalikan baris

- [x] **4. Security: group, akses, record rule**
      - Files: `security/foom_security.xml`, `security/ir.model.access.csv`
      - Covers: REQ-18
      - Done when: user non-admin di group dashboard bisa membaca report, user di luar group tidak

- [x] **5. Method agregasi `get_dashboard_data` + `get_filter_options`**
      - Files: `models/foom_sales_report.py`
      - Covers: REQ-5, REQ-10, REQ-11, REQ-13, REQ-16
      - Done when: dipanggil dari shell Odoo mengembalikan dict lengkap dengan nilai yang masuk akal

- [x] **6. View list/pivot/graph/search + action `ir.actions.client`**
      - Files: `views/foom_sales_report_views.xml`
      - Covers: US-6, REQ-7
      - Done when: view "Data Penjualan" bisa dibuka, difilter, dan di-export

- [x] **7. Menu FOOM Sales**
      - Files: `views/foom_dashboard_menus.xml`
      - Covers: REQ-7
      - Done when: menu root dan dua submenu muncul untuk user yang berhak

- [x] **8. Shell OWL: komponen root, filter bar, state, fetch**
      - Files: `static/src/js/dashboard.js`, `static/src/xml/dashboard.xml`
      - Covers: REQ-7, REQ-8, REQ-9, REQ-14
      - Done when: dashboard terbuka, filter berubah memicu satu RPC, empty state tampil saat tanpa data

- [x] **9. KPI cards + badge growth**
      - Files: `static/src/js/dashboard.js`, `static/src/xml/dashboard.xml`, `static/src/scss/dashboard.scss`
      - Covers: REQ-10, REQ-11
      - Done when: enam kartu tampil dengan format mata uang dan indikator naik/turun benar

- [x] **10. Heatmap jam × hari**
      - Files: idem task 9
      - Covers: REQ-12
      - Done when: grid 7 × 24 tampil, toggle metrik jalan, tooltip menampilkan nilai persis

- [x] **11. Grafik tren + profil per jam (Chart.js)**
      - Files: idem task 9
      - Covers: REQ-13
      - Done when: ganti granularitas memperbarui grafik tanpa kebocoran instance canvas

- [x] **12. Ranking produk / outlet / pelanggan + export CSV**
      - Files: idem task 9
      - Covers: US-4, REQ-15
      - Done when: tiga daftar terisi dan tombol export mengunduh CSV periode aktif

- [x] **13. Bahasa UI** — *diubah dua kali dari rencana awal*
      - Files: —
      - Covers: kebutuhan i18n
      - Keputusan akhir: atas permintaan user, seluruh string UI (dashboard, view,
        menu, group, label field, README, manifest) ditulis dalam bahasa Inggris.
        `i18n/id.po` tidak dibuat. Bahasa lain ditambahkan lewat export terjemahan
        Odoo. Komentar kode tetap bahasa Indonesia.

- [x] **14. Unit test**
      - Files: `tests/__init__.py`, `tests/test_sales_report.py`
      - Covers: seluruh REQ data-layer
      - Done when: `--test-enable` hijau untuk enam test di design §7

- [x] **15. README + verifikasi akhir + paket ZIP**
      - Files: `README.md`
      - Covers: —
      - Done when: sintaks Python & XML tervalidasi, ZIP terkirim ke chat

## Catatan penyimpangan dari spec

1. **Granularitas otomatis** — ditambahkan tingkat `week` untuk rentang 93–400 hari.
   Tanpanya, rentang enam bulan tergambar sebagai ~180 titik harian yang tidak terbaca.
   REQ-13 sudah diperbarui.
2. **Bahasa UI** — awalnya Indonesia, lalu diubah ke Inggris penuh atas permintaan
   user; `i18n/id.po` tidak dibuat. Alasan di task 13.
3. **`account.move.team_id`** — keberadaan kolom dicek ke `information_schema` saat
   view dibuat, karena field ini disediakan modul lain dan tidak ada di semua instance.
4. **Scroll: tinggi piksel tetap dari JS** — empat pendekatan dicoba sebelum berhasil:

   | # | Pendekatan | Hasil |
   |---|---|---|
   | 1 | `min-height: 0` pada root (perbaikan flex item klasik) | gagal — pemotongan bukan di root |
   | 2 | `:has()` memaksa pembungkus Odoo jadi scroller | gagal — selector tidak kena elemen yang tepat |
   | 3 | JS menelusuri leluhur mencari yang `scrollHeight > clientHeight` | gagal — keluar lebih awal saat menemui leluhur ber-`overflow: auto` yang sebenarnya tidak melimpah |
   | 4 | **JS memasang tinggi piksel tetap = `innerHeight - rect.top`** | **berhasil** |

   Ketiga pendekatan pertama sama-sama bergantung pada leluhur: entah tinggi
   induk yang definit, atau tebakan nama kelas. Pendekatan keempat tidak
   menyentuh leluhur sama sekali — tinggi definit dalam piksel plus
   `overflow-y: scroll` selalu menghasilkan scrollbar. Dipasang ulang saat
   jendela di-resize dan setelah setiap patch DOM.

   `box-sizing: border-box` wajib menyertainya; tanpa itu padding 48px
   ditambahkan di luar tinggi yang dipasang dan bagian bawah kembali terpotong.

5. **Kontras scrollbar** — setelah scroll berfungsi, thumb-nya tetap tidak terlihat
   sampai halaman di-zoom 175%. Penyebabnya pilihan warna: thumb `--foom-baseline`
   (#c3c2b7) di atas track `--foom-plane` (#f9f9f7) — abu-abu muda di atas
   hampir-putih. Thumb diganti ke `--foom-ink-2` dan lebar dinaikkan ke 16px.

   Padanan Firefox (`scrollbar-width`/`scrollbar-color`) harus dikurung
   `@supports (-moz-appearance: none)`. Tanpa kurungan itu Chrome ikut membacanya,
   lalu beralih ke jalur styling standar dan mengabaikan SELURUH aturan
   `::-webkit-scrollbar` — termasuk lebar 16px-nya. Sudah diverifikasi:
   `CSS.supports('(-moz-appearance: none)')` bernilai false di Chrome, dan
   `CSS.supports('(scrollbar-color: red blue)')` bernilai true.

6. **Outlet dipetakan ulang: dari Sales Team ke warehouse + location** — asumsi
   awal (`crm.team` sebagai outlet) ternyata salah; di FOOM outlet dipisah per
   warehouse dan stock location. Keduanya kini diambil dari `stock.move` yang
   sudah `done` lewat `sale_line_id`, bukan dari `sale_order.warehouse_id`, agar
   mencerminkan pengiriman yang benar-benar terjadi. Modul menambah dependency
   `sale_stock` (penyedia `stock.move.sale_line_id`).

   Filter Team/Outlet diganti Warehouse + Location; ranking "Top teams" diganti
   "Top warehouses" + "Top locations". Kolom `team_id` tetap ada di SQL view dan
   view Raw data untuk pivot manual.

   Batasan yang diterima: satu baris invoice yang dikirim bertahap hanya
   diwakili pengiriman pertama, supaya satu baris report tetap satu baris dan
   omzet tidak terhitung ganda.

7. **Balasan server dinormalisasi sebelum dipakai template** — gejalanya muncul
   sebagai "scroll tiba-tiba hilang lagi" setelah perubahan warehouse/location,
   padahal seluruh kode scroll masih utuh.

   Sebabnya: `loadOptions`/`loadData` menimpa `state` mentah-mentah dengan
   balasan server. Kalau Python dan asset JS tidak seumur — upgrade setengah
   jalan, atau bundle lama yang masih ter-cache di browser — satu kunci hilang
   (`warehouses`, `top_warehouses`, `kpi.peak_hour`) membuat SELURUH render OWL
   gagal. Dan karena tinggi dashboard dipasang oleh `_fitToViewport` di dalam
   `useEffect`, render yang gagal berarti tinggi tidak pernah terpasang; scroll
   ikut hilang tanpa pesan error yang jelas.

   `_withDefaults()` kini melengkapi balasan server dengan nilai bawaan dan
   menolak tipe yang salah. Versi yang tidak cocok sekarang menurun mutunya
   dengan anggun (dropdown tersembunyi, ranking kosong) alih-alih mematikan
   halaman.

   Pelajaran umum: kalau tata letak bergantung pada JS yang berjalan setelah
   render, setiap kegagalan render akan menyamar sebagai bug tata letak.

## Pelajaran: Odoo memakai libsass, bukan dart-sass

Selama beberapa iterasi SCSS divalidasi dengan dart-sass dan selalu lulus,
padahal Odoo mengompilasi dengan **libsass** yang berhenti di Sass 3.5.
`@supports not selector(...)` ditolak libsass; saat kompilasi gagal Odoo diam-diam
memakai CSS versi lama sambil menampilkan banner merah di halaman — jadi seluruh
perbaikan CSS tampak "tidak berpengaruh" tanpa sebab yang jelas.

Sejak sekarang setiap perubahan SCSS wajib diuji dengan:

```bash
python3 -c "import sass; sass.compile(filename='static/src/scss/dashboard.scss')"
```

Konstruksi yang sudah diuji AMAN di libsass 3.6.6: `:has()` (termasuk dengan
pseudo-element dan `!important`), `clamp()`, `inset`, `100dvh`, `scrollbar-color`,
`@supports` biasa. Yang GAGAL: `@supports not selector(...)`.

## Verifikasi yang dijalankan

| Cek | Hasil |
|---|---|
| `python -m py_compile` seluruh berkas Python | lulus |
| Parsing XML seluruh view, security, dan template | lulus |
| Kompilasi SCSS ke CSS | lulus |
| Kompilasi keempat template OWL dengan `@odoo/owl` 2.8.3 | lulus |
| Mount komponen di Chromium dengan data sintetis + Chart.js asli | lulus, tanpa error konsol |
| Validator palet dataviz (mode terang & gelap) | seluruh cek lulus |
| Uji interaksi: toggle metrik heatmap, tooltip, dropdown filter | lulus |
| Render mode gelap, verifikasi token warna terpakai | lulus |
| Scroll di dalam layout mirip action manager Odoo (`min-height: 0`) | lulus, scrollHeight 1711 > clientHeight 854 |
| Render ulang setelah seluruh UI dialihbahasakan ke Inggris | lulus, tanpa error konsol |
| **Kompilasi SCSS dengan libsass 3.6.6 (kompiler Odoo)** | lulus |
| Deteksi scroll runtime pada 3 layout pembungkus berbeda | lulus, tepat satu scroller di tiap kasus |
| Layout dengan SEMUA leluhur `overflow: hidden` (case-c) | lulus, scrollTop 857 |
| Ganti filter 4x berturut-turut | lulus, scroll host tetap satu (tidak menumpuk) |
| Pengembalian gaya saat komponen di-unmount | lulus, inline style & kelas bersih |
| Scroll pada 4 layout pembungkus, termasuk `html`/`body`/semua leluhur `overflow: hidden` | lulus, tepat satu scroller di tiap kasus |
| Resize jendela 1440x900 → 1100x640 | lulus, tinggi menyesuaikan, dashboard tetap pas di viewport |
| Ganti filter 4x pada layout terburuk | lulus, tinggi tetap benar |
| Render ulang setelah filter Warehouse + Location menggantikan Team | lulus, tanpa error konsol |
| Dropdown warehouse: buka, centang satu, ringkasan berubah jadi nama warehouse | lulus |
| Empat kartu ranking (produk, warehouse, location, pelanggan) dalam satu baris | lulus pada lebar 1440 |
| **Regresi: server bentuk lama + JS baru** (`case-stale`) | sebelum perbaikan: render crash, tinggi tidak terpasang, scroll hilang |
| Regresi yang sama setelah `_withDefaults()` | lulus, render jalan, scrollTop 857, tanpa error konsol |
