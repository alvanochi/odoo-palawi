# Requirements — FOOM Sales Dashboard

## Konteks environment

| Item | Nilai |
|---|---|
| Odoo version | 18.0 |
| Modul baru | `foom_sales_dashboard` |
| Environment | Remote instance (odoo.rel.id), modul dikirim sebagai ZIP untuk di-extract ke addons path |
| Dependency | `base`, `web`, `account`, `sale` |
| Sumber data | Customer Invoice / Credit Note yang sudah **posted** (`account.move` + `account.move.line`) |
| Basis waktu | `sale_order.date_order` (waktu transaksi asli), fallback ke `account_move.create_date` |
| Timezone | Semua agregasi jam/hari dikonversi dari UTC ke timezone user (mis. Asia/Jakarta) |

## User stories

**US-1 — Melihat ritme penjualan per jam**
> Sebagai manajer penjualan FOOM, saya ingin melihat heatmap jam × hari, sehingga saya tahu jam berapa toko ramai dan bisa mengatur shift staf.

**US-2 — Melihat tren jangka panjang**
> Sebagai manajer penjualan, saya ingin melihat grafik tren jumlah order dan total omzet per jam/hari/minggu/bulan/tahun, sehingga saya bisa melihat pertumbuhan dan musiman.

**US-3 — Melihat ringkasan angka kunci**
> Sebagai pemilik bisnis, saya ingin KPI card (total omzet, jumlah order, rata-rata per order, jumlah pelanggan unik) beserta persentase pertumbuhan vs periode sebelumnya, sehingga saya langsung tahu kondisi bisnis tanpa membaca grafik.

**US-4 — Mengetahui produk & outlet terbaik**
> Sebagai manajer penjualan, saya ingin ranking produk terlaris dan outlet/tim penjualan dengan omzet tertinggi, sehingga saya bisa fokus ke yang perform dan membenahi yang lemah.

**US-5 — Memfilter data**
> Sebagai user dashboard, saya ingin memfilter berdasarkan rentang tanggal (preset + custom), company, dan sales team, sehingga saya bisa menganalisis segmen tertentu.

**US-6 — Menggali data mentah**
> Sebagai analis, saya ingin membuka data yang mendasari dashboard dalam view list/pivot/graph Odoo dan meng-export-nya, sehingga saya bisa melakukan analisis lanjutan di spreadsheet.

## Acceptance criteria (EARS)

**Data & agregasi**

- REQ-1: WHEN modul di-install THEN system SHALL membuat SQL view `foom_sales_report` yang hanya memuat baris produk (`display_type = 'product'`) dari `account.move` bertipe `out_invoice`/`out_refund` dengan `state = 'posted'`.
- REQ-2: WHEN sebuah baris berasal dari credit note (`out_refund`) THEN system SHALL menghitung amount dan quantity-nya sebagai nilai negatif, sehingga retur mengurangi omzet.
- REQ-3: WHEN menghitung amount THEN system SHALL menggunakan `-account_move_line.balance` (mata uang company), BUKAN `price_subtotal` mata uang dokumen, sehingga penjualan multi-currency dapat dijumlahkan.
- REQ-4: WHEN sebuah invoice line terhubung ke sale order line THEN system SHALL memakai `sale_order.date_order` sebagai waktu transaksi; OTHERWISE system SHALL memakai `account_move.create_date`.
- REQ-5: WHEN mengagregasi per jam atau per hari THEN system SHALL mengonversi timestamp UTC ke timezone user aktif (`res.users.tz`), dan SHALL fallback ke `UTC` bila `tz` kosong.
- REQ-6: WHEN menghitung jumlah order THEN system SHALL menghitung `COUNT(DISTINCT move_id)`, bukan jumlah baris.

**Dashboard**

- REQ-7: WHEN user membuka menu FOOM Sales → Dashboard THEN system SHALL menampilkan client action OWL berisi: baris KPI card, heatmap jam × hari, grafik tren, grafik profil per jam, top produk, top outlet/tim, dan top pelanggan.
- REQ-8: WHEN dashboard dimuat pertama kali THEN system SHALL memakai preset periode "30 hari terakhir".
- REQ-9: WHEN user mengganti preset periode, granularitas tren, company, atau tim THEN system SHALL memuat ulang data via satu panggilan ORM dan memperbarui seluruh visual tanpa reload halaman.
- REQ-10: WHEN KPI dihitung THEN system SHALL juga menghitung nilai periode sebelumnya yang panjangnya sama dan persis mendahului `date_from`, lalu menampilkan persentase perubahan dengan indikator naik/turun.
- REQ-11: WHEN nilai periode sebelumnya adalah nol THEN system SHALL menampilkan tanda "—" alih-alih pembagian nol atau "∞%".
- REQ-12: WHEN heatmap ditampilkan THEN system SHALL menampilkan grid 7 baris (Senin–Minggu) × 24 kolom (jam 0–23), dengan intensitas warna proporsional terhadap nilai maksimum, tooltip berisi nilai persis, dan toggle metrik antara jumlah order dan total amount.
- REQ-13: WHEN rentang periode ≤ 2 hari THEN granularitas tren SHALL default ke per jam; WHEN ≤ 92 hari THEN per hari; WHEN ≤ 400 hari THEN per minggu; WHEN ≤ 3 tahun THEN per bulan; OTHERWISE per tahun.
- REQ-14: WHEN periode yang dipilih tidak memiliki data sama sekali THEN system SHALL menampilkan empty state yang jelas, bukan grafik kosong tanpa keterangan.
- REQ-15: WHEN user menekan tombol export pada tabel ringkasan THEN system SHALL mengunduh file CSV berisi data periode aktif.

**Non-fungsional**

- REQ-16: WHEN dashboard memuat data untuk periode 1 tahun THEN seluruh query SHALL selesai dalam satu round-trip RPC dan SHALL memakai agregasi di sisi SQL (bukan iterasi record di Python).
- REQ-17: WHEN modul di-uninstall THEN system SHALL menghapus SQL view tanpa menyisakan objek database yatim.
- REQ-18: WHERE instance multi-company aktif, system SHALL membatasi data ke `allowed_company_ids` dari konteks user.

## Kebutuhan Odoo-specific

**Model**

| Model | Jenis | Keterangan |
|---|---|---|
| `foom.sales.report` | `models.Model`, `_auto = False` | SQL view read-only; menampung semua field analisis dan method `get_dashboard_data` |

Tidak ada model core yang di-inherit → risiko konflik dengan addon lain minimal.

**Security**

| Group | XML id | Hak |
|---|---|---|
| FOOM Dashboard / User | `group_foom_dashboard_user` | read `foom.sales.report`, akses menu |
| FOOM Dashboard / Manager | `group_foom_dashboard_manager` | implied `group_foom_dashboard_user`; disiapkan untuk konfigurasi lanjutan |

- `ir.model.access.csv`: read-only (`1,0,0,0`) untuk kedua group. Tidak ada create/write/unlink karena model adalah SQL view.
- Record rule multi-company pada `company_id` (`in company_ids`).
- `group_foom_dashboard_user` otomatis diberikan ke `sales_team.group_sale_salesman` via `implied_ids` agar tim sales langsung punya akses.

**Views & menu**

- `ir.actions.client` tag `foom_sales_dashboard.dashboard`.
- Menu root `FOOM Sales` (web icon sendiri) → item `Dashboard` dan `Data Penjualan`.
- View `list`, `pivot`, `graph`, dan `search` untuk `foom.sales.report` (Odoo 18 memakai tag `<list>`, bukan `<tree>`).

**Assets**

- Chart.js 4.x UMD di-bundle di dalam modul (`static/lib/chartjs/chart.umd.js`) agar tidak bergantung pada path lib internal Odoo yang berubah antar versi.
- Bundle `web.assets_backend` memuat lib, JS OWL, template XML, dan SCSS modul.

**i18n**

- Semua string UI dibungkus terjemahan; disediakan file `i18n/id.po` untuk bahasa Indonesia.

**Data/demo**

- Tidak ada data demo; dashboard membaca transaksi nyata.

## Out of scope

Hal-hal berikut **tidak** dibangun pada iterasi ini:

- Data dari POS (`pos.order`) — hanya invoice/credit note dari alur Sales.
- Target penjualan dan pencapaian terhadap target.
- Penjadwalan laporan otomatis lewat email.
- Analisis margin/profitabilitas (butuh data cost yang belum dikonfirmasi).
- Analisis geografis/peta outlet.
- Dashboard untuk portal atau website (backend-only).
- Konversi multi-currency dengan kurs historis kustom — memakai nilai company currency yang sudah dihitung Odoo.
