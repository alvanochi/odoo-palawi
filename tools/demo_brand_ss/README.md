# Demo Brand SS (PT ShellaSaukia)

Skrip Node.js (JSON-RPC) yang membangun data dan fitur demo ERP Brand SS di
`https://palawi.rutekebangsaan.com`, database `odoo18_palawi`, company id 13.
Semua skrip idempoten sebisa mungkin (cari dulu, baru buat).

Kredensial diambil dari environment, tidak disimpan di file:

```sh
export ODOO_LOGIN=admin ODOO_PASSWORD=...      # user admin Odoo
export DEMO_PW=...                             # password user demo ss.*
```

## Urutan

| Skrip | Isi |
|---|---|
| `m1.js` | Master data: akun, jurnal, analytic, gudang, kategori, varian, produk, BoM, partner, pricelist, sales team, departemen, karyawan |
| `t1.js` | Stok awal (lot + kedaluwarsa) |
| `t5.js po` / `t5.js mo` | Purchase order & manufacturing order contoh |
| `wh.js ship_only` → `t6.js history` → `wh.js pick_pack_ship` → `t6.js recent` | Order marketplace/reseller/offline dummy (set `THIN=1` untuk volume lebih kecil) |
| `t7.js` | Biaya marketing, sewa, budget, proyek, absensi |
| `t8.js` | Model custom **Live Streaming** (`x_ss_live_session`) + view + menu |
| `t9.js` | Proyek CS tiket & Campaign/KOL |
| `t11.js` | User demo per jabatan + model custom **Pengajuan & Approval** (`x_ss_approval`) + server action |
| `t13.js` | **Aturan Approval** yang bisa diatur dari layar (`x_ss_approval_rule`, menu Pengajuan & Approval → Konfigurasi) dan server action Ajukan/Setujui yang membaca aturan tersebut. Jalankan setelah `t11.js` (menimpa logika batas nominal yang tertanam) |
| `t14.js model` / `t14.js data` | **Budget Proyek** (`x_ss_project_budget`) + jenis pengajuan *Budget Proyek / Riset* dengan alur Researcher → Approval Direktur → Mengetahui Finance → Transfer Dana (Finance), user `ss.yuni`, 3 proyek R&D. Jalankan setelah `t13.js` |
| `t15.js` | Contoh pengajuan dana riset lewat alur sebenarnya (per user) |
| `adminonly.js` | Menu **Konfigurasi → Aturan Approval** hanya untuk Administrator (`base.group_system`); grup *SS Approval / Manager* hanya baca. **Jalankan setelah `t13.js`** (t13 membuat menu dengan grup Manager). Cek per user: `adminchk.js` |
| `t16.js` | **Konfigurasi → Pengaturan Jenis Pengajuan** (Finance + Administrator, grup *SS Approval / Finance*): rekening default Bank/Kas & akun biaya per jenis; field *Bayar dari (Bank/Kas)* di pengajuan (terisi otomatis saat disetujui, bisa diganti Finance) dipakai tombol Transfer Dana. Uji: `t16test.js` |
| `role.js` → `t17.js` | **Peran (Role)** karyawan: `role.js` membuat versi awal (selection), `t17.js` mengubahnya jadi master data `x_ss_role` (Employees → Configuration → Peran (Role), bisa *Create* langsung dari field) yang hanya bisa ditambah/diubah grup *SS HR / Kelola Peran* (Rina) + Administrator, memigrasi data, dan menghapus field lama. Uji: `t17test.js` |
| `trfix.js` | Tombol **Transfer Dana** & field *Bayar dari* hanya untuk grup *SS Approval / Finance* + Administrator (Direktur tidak bisa transfer). Uji: `trtest.js` |
| `t12.js` | Contoh pengajuan, dijalankan sebagai masing-masing user |
| `t10.js settlement,resellers,returns,recentFlow,live,targets` | Settlement marketplace, pembayaran reseller, retur, alur gudang 3 langkah, sesi live, target |
| `hr2.js payroll` / `hr2.js leave` | Struktur gaji Indonesia, kontrak, slip gaji, cuti |
| `misc.js tax,reorder,transfer,asset` | PPh 23/4(2), kalender pajak, reorder rule, permintaan stok toko, aset tetap |
| `pos2.js closed` / `pos2.js open` | Sesi POS Toko Kemang |
| `b2b.js` | Order distributor besar |
| `payfix2.js` | Perbaikan pembayaran tanpa jurnal (akun Outstanding) |
| `hide.js` | Sembunyikan menu PALAWI (Rest API, Marketing Order, Apps, Dashboards) untuk user `ss.*` via `menu_visibility` |
| `prule.js`, `pdedup.js`, `pdup2.js` | Grup "SS Demo / Kontak hanya PT ShellaSaukia" + record rule `res.partner` (hanya kontak company 13, sesama user SS, OdooBot), dan rapikan kontak karyawan dobel. Admin utama **tidak** boleh masuk grup ini |

`ids.json` dan `approval_ids.json` menyimpan id record yang dibuat, dipakai antar skrip.

## Executive Dashboard

Modul `ss_executive_dashboard` ada di `tools/demo_brand_ss/ss_executive_dashboard`, sengaja **bukan** di root repo:
modul ini sudah terpasang di database lewat Apps → Import Module (`imp.js` mengimpor
`ss_executive_dashboard.zip` dari folder kerja). Kalau foldernya ada di addons path, Odoo memuatnya dua kali
dan action dashboard terdaftar ganda. Untuk update: zip folder ini (path di dalam zip pakai "/") lalu jalankan `imp.js`.
Menu hanya untuk grup "Brand SS Demo".

## Catatan

- Database ini juga dipakai PALAWI. Menu demo dibatasi grup `Brand SS Demo` /
  `SS Approval / Pengguna`, data dibatasi `company_id = 13`.
- `shot.js` mengambil screenshot halaman Odoo via Edge headless (cek visual).
- `skema-demo-brand-ss.html` adalah sumber halaman skema demo.

- `qa-test-case-brand-ss.html` adalah sumber halaman test case QA (hasil Pass/Fail/Blocked disimpan di database artifact).
