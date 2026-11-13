# POS Union Econique Integration (Odoo 18)

Mengirim transaksi POS yang sudah lunas ke API **Union Kuliner Econique**
(`POST /api/kuliner/login`, `POST /api/kuliner/transaction`). Credential dan semua
aturan pemetaan disimpan per POS config lewat modul `pos_payment_gateway`.

## Cara kerja

```
order lunas (kasir POS atau REST API)
  -> pos.order.write(state=paid)        hook di level model
  -> pos.econique.transaction (pending) antrian + log
  -> cron tiap 5 menit (dipicu langsung saat antrian dibuat)
       -> login (token di-cache, login ulang bila 401)
       -> POST /api/kuliner/transaction
       -> sent | retry (jaringan, 5xx) | failed
```

- Hook ada di `pos.order`, bukan di UI POS. Order yang dilunasi lewat `rest_api_odoo`
  (`/api/pos/order/pay`) ikut terkirim karena sama-sama menulis `state = paid`.
- Pembayaran di POS **tidak pernah** diblokir atau digagalkan oleh integrasi ini.
- Satu order = satu transaksi (unique `order_id`), jadi tidak terkirim dobel.
- Gagal sementara dicoba ulang dengan jeda 2, 4, 8 ... maksimal 60 menit, sampai
  `Maks Percobaan`, lalu `Failed`. Error validasi (4xx) langsung `Failed`.
- Refund dan order total nol dicatat `Skipped` (API tidak punya endpoint refund).

## Setup

1. Install modul: `odoo-bin -d <db> -i pos_econique_union --stop-after-init`
   (otomatis memasang `pos_payment_gateway`).
2. **Point of Sale > Configuration > Payment Gateway Credentials > New**:
   - Payment Gateway: *Union Kuliner Econique*, pilih POS config.
   - Base URL: produksi `https://api.econique.co.id`, staging `https://stg-api.econique.id`.
   - Client ID = username API, Client Secret = password API.
3. Tab **Union / Econique**: isi Tenant Code dan Tenant Name, atur pemetaan, isi
   **Pemetaan Metode Pembayaran**, lalu klik **Test Login**.
4. Pantau di **Point of Sale > Configuration > Econique Transactions** (tombol
   *Kirim Sekarang*, *Kembalikan ke Pending*, *Lewati*).

Tanpa credential Econique aktif (atau `Kirim Otomatis` mati), order POS itu tidak
masuk antrian. Order yang lunas sebelum modul dipasang tidak dikirim otomatis.

## Pemetaan field (bisa diubah per credential)

| Field Econique | Sumber di Odoo |
|---|---|
| `invoice_number` | `pos_reference` (atau nama order) |
| `tenant_code`, `tenant_name` | pengaturan credential |
| `voucher_code` | kode kupon dari baris reward, selain itu `null` |
| `transaction_date`, `payment_date` | `date_order` / tanggal payment, zona waktu company (default Asia/Jakarta) |
| `bruto` | jumlah `price_unit * qty` baris barang |
| `discount` | persen (maks 100) dari diskon baris + baris reward terhadap bruto |
| `service_fee` | `Service Fee (%)` x (bruto - diskon) |
| `ppn` | `amount_tax` order |
| `netto` | `bruto - diskon - service_fee - ppn` (cocok dengan contoh di dokumentasi) |
| `payment_type`, `payment_provider`, `payment_issuer` | tabel pemetaan metode pembayaran; tanpa pemetaan: tunai = `Cash`, selain itu nama metode; issuer = Default payment_issuer (`PT PHI`) |
| `payment_transactions_id` | `transaction_id` payment, lalu nama payment, lalu `pos_reference` |
| `items[].product_code` | Internal Reference / Barcode / ID produk |
| `items[].price_code`, `price_name` | nilai tetap, atau ID dan nama pricelist |

Baris reward/potongan (nilai negatif) tidak dikirim sebagai item; nilainya masuk ke
`discount`. Qty pecahan dikirim sebagai 1 item bernilai total baris karena `amount`
bertipe Int. Order dengan lebih dari satu pembayaran dikirim memakai pembayaran
terbesar (API hanya punya satu set field payment).

## Hal di dokumentasi Econique yang ambigu (dan pilihan modul ini)

- Contoh request memakai `payment_vendor`, tabel field memakai `payment_issuer`:
  dua-duanya dikirim (bisa dimatikan).
- Login disebut memakai Basic Auth, tanpa menyebut kredensialnya: dikirim Basic dengan
  username/password yang sama (bisa dimatikan atau di-override lewat Extra Parameters
  `basic_auth_user` / `basic_auth_password`).
- `amount` pada contoh item berisi nominal, tetapi tabel mendefinisikannya sebagai
  jumlah barang: modul mengikuti tabel (qty).
- `discount_nominal` per item dihitung untuk seluruh baris
  (`unit_price * qty * persen`), bukan per unit.
- Dokumentasi tidak menjelaskan respons bila `invoice_number` dikirim dua kali.

## Menyesuaikan aturan

Seluruh penyusunan payload ada di `pos.econique.transaction._build_payload()`
(mengumpulkan data Odoo) dan `services/union_payload.py` (rumus, tanpa dependensi
Odoo). Override salah satunya bila aturan Econique berubah.

## Test

Tes yang ada hanya menguji rumus dan klien HTTP (HTTP di-mock), tidak menyentuh data order:

```bash
odoo-bin -d <db> -u pos_econique_union --test-enable --test-tags /pos_econique_union --stop-after-init
```
