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
| `t12.js` | Contoh pengajuan, dijalankan sebagai masing-masing user |
| `t10.js settlement,resellers,returns,recentFlow,live,targets` | Settlement marketplace, pembayaran reseller, retur, alur gudang 3 langkah, sesi live, target |
| `hr2.js payroll` / `hr2.js leave` | Struktur gaji Indonesia, kontrak, slip gaji, cuti |
| `misc.js tax,reorder,transfer,asset` | PPh 23/4(2), kalender pajak, reorder rule, permintaan stok toko, aset tetap |
| `pos2.js closed` / `pos2.js open` | Sesi POS Toko Kemang |
| `b2b.js` | Order distributor besar |
| `payfix2.js` | Perbaikan pembayaran tanpa jurnal (akun Outstanding) |

`ids.json` dan `approval_ids.json` menyimpan id record yang dibuat, dipakai antar skrip.

## Executive Dashboard

Modul `ss_executive_dashboard` (root repo) adalah modul data tanpa Python, jadi
bisa di-deploy biasa **atau** diimpor lewat Apps → Import Module (`imp.js`
mengimpor `ss_executive_dashboard.zip` dari folder kerja). Menu hanya untuk grup
"Brand SS Demo".

## Catatan

- Database ini juga dipakai PALAWI. Menu demo dibatasi grup `Brand SS Demo` /
  `SS Approval / Pengguna`, data dibatasi `company_id = 13`.
- `shot.js` mengambil screenshot halaman Odoo via Edge headless (cek visual).
- `skema-demo-brand-ss.html` adalah sumber halaman skema demo.
