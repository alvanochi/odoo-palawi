# POS API — Kitchen Display & Promotions

Referensi integrasi untuk aplikasi POS pihak ketiga (Android) terhadap Odoo 18.

| Modul | Versi | Isi |
|---|---|---|
| `rest_api_odoo` | 18.0.1.1.0 | `/send_request` generik, open bill (`poskas.bill`), order & pembayaran, **penanda promo pada `product.product`** |
| `rest_api_plw` | 1.3.0 | `/api/v2/pos/*` (KDS), katalog, checkout v2 |
| `pos_order_extra_states` | 18.0.2.2.0 | `kitchen_state` per baris `pos.order.line` + channel realtime KDS |

---

## 1. Dasar

### 1.1 Base URL

```
https://kasprima.co.id
```

### 1.2 Autentikasi — beda per keluarga endpoint

| Keluarga | Auth | Header |
|---|---|---|
| `/send_request` | Kredensial Odoo + API key user | `login`, `password`, `db`, `api-key` |
| `/api/pos/promotions*`, `/api/pos/coupons/*`, `/api/pos/pricelists*` | API key | `api-key`: api_key user **atau** `api_key_palawi` |
| `/api/pos/products`, `/api/v2/pos/*` | API key statis | `api-key: <System Parameter api_key_palawi>` |
| `/api/loyalty/promotions` | JWT | `Authorization: Bearer <token>` |
| `/api/pos/bill/*`, `/api/pos/order` | **tidak ada** | — |

> **Catatan keamanan.** `/api/pos/bill/*`, `/api/pos/order`, dan `/api/pos/bill/fingerprint`
> dideklarasikan `auth="none"` tanpa pemeriksaan API key, dan berjalan sebagai
> user admin. Siapa pun yang tahu URL-nya bisa membaca dan mengubah bill. Kalau
> belum dibatasi, batasi di reverse proxy (IP allowlist / mTLS) sampai
> pemeriksaan key ditambahkan di sisi Odoo.

### 1.3 Bentuk response

Sukses (`/api/pos/*`, `/api/v2/pos/*`):
```json
{ "success": true, "data": { } }
```

Gagal:
```json
{ "success": false, "message": "POS Config ID 99 does not exist", "status": 404 }
```

`/send_request` membungkus daftar:
```json
{ "success": true, "data": { "items": [], "limit": 10, "offset": 0,
  "count": 128, "page_count": 10, "search": null, "order": "id asc" } }
```

### 1.4 Wajib dibaca sebelum upgrade

Rilis ini **menambah key** pada beberapa payload yang sudah dipakai (tidak ada
yang dihapus atau di-rename). Kalau client memakai `kotlinx.serialization`,
pastikan:

```kotlin
Json { ignoreUnknownKeys = true }
```

Moshi dan Gson mengabaikan key tak dikenal secara default.

Key baru: `uid`, `source`, `bill` pada payload KDS; `kitchen_state`,
`cooking_started_at`, `ready_at`, `ready_source` pada payload bill.

Field promo pada `product.product` tidak termasuk di sini — ia baru muncul
setelah Anda menambahkannya di GET Fields `connection.api`, jadi tidak ada
response yang berubah dengan sendirinya.

---

## 2. Katalog produk + penanda promo

Penanda promo adalah **field pada `product.product`**, bukan endpoint terpisah.
Konsekuensinya penanda itu ikut di semua jalur yang membaca produk.

Sumber kebenarannya `loyalty.rule` / `loyalty.reward` bawaan Odoo. Pencocokan
produk memakai `_get_valid_product_domain()` dan `_get_discount_product_domain()`
yang sama persis dengan yang dipakai kasir POS, jadi badge di katalog tidak
akan menjanjikan promo yang nanti ditolak saat checkout.

### 2.1 `GET /send_request?model=product.product`

```bash
curl -X GET 'https://kasprima.co.id/send_request?model=product.product&availpos=true&company=PT.%20Palawi&pos_config_id=3&limit=10&offset=0' \
  --header 'login: palawi@gmail.com' \
  --header 'password: ********' \
  --header 'db: odoo-dev' \
  --header 'api-key: ********'
```

**Query params**

| Param | Tipe | Keterangan |
|---|---|---|
| `model` | string | wajib, `product.product` |
| `limit`, `offset` | int | default 10, maksimum 100 |
| `search` / `q` | string | cocok pada `name` / `display_name` |
| `availpos` | bool | `available_in_pos` |
| `category` / `category_id` | string / int | POS category, termasuk anaknya |
| `company` | string | sesuai konfigurasi `connection.api` |
| **`pos_config_id`** | int | **baru** — mempersempit promo ke satu POS |
| **`has_promotion`** | bool | **baru** — hanya produk yang sedang promo |
| `skip` | csv | field yang tidak ingin diambil |

`pos_config_id` diteruskan ke `pos.config._get_program_ids()` milik `pos_loyalty`,
jadi batasan `pos_config_ids`, pricelist, rentang tanggal dan `max_usage` ikut
berlaku. Tanpa param itu, cakupannya adalah semua program POS milik perusahaan
yang boleh dilihat pemanggil.

**Field promo pada response**

| Field | Tipe | Arti |
|---|---|---|
| `has_promotion` | bool | Ada program aktif yang **menyebut produk ini** |
| `has_order_promotion` | bool | Ada program order-level yang ikut mengenai produk ini |
| `promotion_count` | int | Jumlah program yang menyebut produk ini |
| `promotion_labels` | string | Nama program dipisah koma — siap dipakai badge |
| `promotion_types` | string | `program_type` dipisah koma |
| `promotion_roles` | string | `trigger`, `reward`, `discounted` dipisah koma |
| `promotion_details` | array | Rincian program yang menyebut produk ini |
| `order_promotion_details` | array | Rincian program order-level |

**Tidak ada satu pun field yang dipaksa masuk ke response.** Semuanya mengikuti
GET Fields pada `connection.api` untuk model `product.product` — sama seperti
field produk lainnya. Aktifkan dengan menambahkan field yang diinginkan di
Settings → Technical → REST API Config, atau minta per request lewat body
`{"fields": ["has_promotion", "promotion_labels"]}`.

Mulai dari `has_promotion` dan `promotion_labels` saja; `promotion_details` jauh
lebih berat, tambahkan hanya kalau layar detail memang membutuhkannya.

ID `loyalty.program` terbaca lewat `promotion_details[].program_id`. Tidak ada
field relasi ke `loyalty.program`, karena field relasi akan membuat modul
loyalty menjadi dependency `rest_api_odoo` — mencabut loyalty lalu ikut
mematikan seluruh API POS.

**Kenapa dua flag, bukan satu**

`has_promotion` hanya true kalau program menyebut produknya (lewat
`product_ids`, kategori, tag produk, atau `product_domain`). Diskon
"10% untuk seluruh order" tidak menyebut produk mana pun; kalau dimasukkan ke
flag yang sama, **seluruh** katalog akan ber-badge promo dan flag itu berhenti
berguna. Program seperti itu dilaporkan lewat `has_order_promotion`.

**Peran produk (`promotion_roles`)**

| Role | Arti | Contoh UI |
|---|---|---|
| `trigger` | Membelinya yang memicu/mengumpulkan promo | "Beli 2 gratis 1" |
| `reward` | Produk ini yang didapat gratis | "Bisa didapat gratis" |
| `discounted` | Diskon program jatuh pada produk ini | "Diskon 20%" |

**`program_type` Odoo**: `promotion`, `buy_x_get_y`, `loyalty`, `gift_card`,
`ewallet`, `coupons`, `promo_code`, `next_order_coupons`.

**Contoh item**

```json
{
  "id": 412,
  "display_name": "Kopi Susu Gula Aren",
  "list_price": 25000.0,
  "company_id": { "id": 3, "display_name": "PT. Palawi" },
  "pos_categ_ids": [{ "id": 12, "display_name": "Signature" }],
  "has_promotion": true,
  "has_order_promotion": false,
  "promotion_count": 1,
  "promotion_labels": "BOGO Kopi Sore",
  "promotion_types": "buy_x_get_y",
  "promotion_roles": "reward,trigger"
}
```

**Isi satu entri `promotion_details`**

```json
{
  "program_id": 7,
  "program_name": "BOGO Kopi Sore",
  "program_type": "buy_x_get_y",
  "trigger": "auto",
  "applies_on": "current",
  "roles": ["reward", "trigger"],
  "date_from": "2026-08-01",
  "date_to": "2026-08-31",
  "requires_code": false,
  "code": null,
  "minimum_qty": 2,
  "minimum_amount": 0.0,
  "rules": [
    { "rule_id": 3, "mode": "auto", "code": "",
      "minimum_qty": 2, "minimum_amount": 0.0,
      "reward_point_amount": 1.0, "reward_point_mode": "unit",
      "any_product": false,
      "product_ids": [412, 519], "product_category_id": false, "product_tag_id": false }
  ],
  "rewards": [
    {
      "reward_id": 9,
      "reward_type": "product",
      "description": "Gratis 1 Kopi Susu Gula Aren",
      "required_points": 2.0,
      "discount": 0.0,
      "discount_mode": "percent",
      "discount_applicability": "",
      "discount_max_amount": 0.0,
      "reward_product_id": 412,
      "reward_product_name": "Kopi Susu Gula Aren",
      "reward_product_qty": 1,
      "reward_product_ids": [{ "id": 412, "name": "Kopi Susu Gula Aren", "price": 25000.0 }]
    }
  ]
}
```

`requires_code: true` berarti promo tidak berjalan otomatis — pelanggan harus
menyebut `code`, dan UI sebaiknya mengatakan itu.

**Membaca promo "beli A + B gratis C".** Kombinasinya ada di `rules[]`:
`product_ids` adalah produk yang boleh memicu, `reward_point_amount` +
`reward_point_mode` menentukan berapa poin yang dihasilkan tiap unit, dan
`rewards[].required_points` berapa poin yang dibutuhkan. Contoh di atas:
membeli produk 412 atau 519, satu poin per unit, butuh 2 poin — jadi "beli 2 di
antara A dan B, gratis C".

Struktur ini cukup untuk **menampilkan** promonya di kartu produk. Untuk tahu
apakah keranjang saat ini sudah memenuhinya dan berapa nilainya, itu pekerjaan
`/api/pos/promotions/match` (3.6).

### 2.2 Endpoint produk lain

Penanda promo hanya ada pada `product.product`, sehingga hanya terbaca lewat
`/send_request`. Endpoint katalog di `rest_api_plw` (`/api/pos/products`,
`/api/pos/product/<id>`) tidak membawanya.

## 3. Mesin promo (evaluasi keranjang)

Penanda di katalog hanya untuk tampilan. Perhitungan sesungguhnya tetap lewat
endpoint di bawah ini, yang memanggil mesin loyalty Odoo.

Semua endpoint pada bagian ini **dilayani `rest_api_odoo`**
(`controllers/promo_api.py`). Sebelumnya ada di `rest_api_plw`; bentuk request
dan response-nya tidak berubah sama sekali, jadi klien yang sudah memakainya
tidak perlu disentuh. Header `api-key` menerima dua nilai: `api_key` milik user
(sama seperti `/send_request`) maupun System Parameter `api_key_palawi` yang
dipakai sebelumnya.

Untuk menghindari dua modul mendaftarkan route yang sama, `promo_controller` di
`rest_api_plw` tidak lagi dimuat.

### 3.1 `GET /api/pos/promotions`

Program aktif pada satu POS.

| Param | Wajib | Keterangan |
|---|---|---|
| `pos_config_id` | ya | |
| `program_type` | tidak | csv, mis. `promotion,buy_x_get_y` |

### 3.2 `POST /api/pos/promotions/match`

Evaluasi keranjang. Ini yang dipanggil setiap kali isi keranjang berubah.

```json
{
  "pos_config_id": 5,
  "pricelist_id": 2,
  "partner_id": 91,
  "coupon_codes": ["HEMAT10"],
  "cart": [
    { "product_id": 412, "qty": 2, "price": 25000 }
  ]
}
```

Ambang qty/nominal dievaluasi pada harga yang benar-benar ditagih (pricelist +
pajak). Response berisi program yang cocok **dan** `claimable_rewards` — payload
itulah yang dikirim balik ke checkout.

### 3.3 `GET /api/pos/coupons` — kupon milik pelanggan

Untuk layar "Kupon Saya". `coupons/validate` hanya memeriksa satu kode yang
diketik; endpoint ini menampilkan daftarnya.

```
GET /api/pos/coupons?pos_config_id=5&partner_id=91
```

```json
{ "success": true, "data": [
  { "coupon_id": 31, "code": "HEMAT10",
    "points": 10.0, "points_display": "10 Points", "point_name": "Points",
    "expiration_date": "2026-12-31", "is_expired": false, "usable": true,
    "program_id": 11, "program_name": "Diskon Member", "program_type": "promo_code",
    "claimable_reward_ids": [14],
    "rewards": [ { "reward_id": 14, "reward_type": "discount", "discount": 10.0,
                   "discount_line_product_id": 92 } ] } ] }
```

| Param | Wajib | Keterangan |
|---|---|---|
| `pos_config_id` | ya | Menentukan program mana yang berlaku di POS itu |
| `partner_id` | ya | Pemilik kupon |
| `program_type` | tidak | csv, mis. `promo_code,loyalty` |

`partner_id` wajib, dan **hanya kupon milik pelanggan itu** yang dikembalikan.
Kupon tanpa pemilik adalah kupon bawa-tunjuk: siapa pun yang tahu kodenya bisa
memakainya, jadi mendaftarkannya lewat API sama saja dengan membagikan seluruh
kode yang masih berlaku.

Kupon yang poinnya belum cukup tetap ditampilkan dengan `usable: false`, supaya
pelanggan tahu ia memilikinya dan berapa lagi yang kurang.

### 3.4 `POST /api/pos/coupons/validate`

```json
{ "pos_config_id": 5, "code": "HEMAT10", "partner_id": 91, "pricelist_id": 2 }
```

Diteruskan ke `pos.config.use_coupon_code()` bawaan Odoo: kedaluwarsa,
kepemilikan partner, poin, pricelist dan validitas program semuanya diperiksa di
sana.

`partner_id` dan `pricelist_id` **opsional, tetapi mengubah jawabannya** — dan
keduanya bukan tebakan, melainkan yang dipakai Odoo di dalam:

- **`partner_id`** — pencarian kupon di Odoo berbunyi `('partner_id', 'in', (False, partner_id))`.
  Kupon yang dimiliki seorang pelanggan (kartu loyalty, kupon personal) hanya
  **ditemukan** bila partner-nya disebut. Tanpa itu, kupon personal dijawab
  "This coupon is invalid" walaupun sah. Kupon anonim dan gift card tidak
  terpengaruh.
- **`pricelist_id`** — bila program dibatasi pricelist tertentu
  (`loyalty.program.pricelist_ids`), Odoo menolak dengan "This coupon is not
  available with the current pricelist" ketika pricelist yang sedang aktif
  tidak disebut.

Kirim keduanya persis seperti yang sedang dipakai di layar kasir, supaya
jawaban validasi sama dengan yang nanti terjadi saat pembayaran.

### 3.5 Pricelist

- `GET /api/pos/pricelists?pos_config_id=5`
- `POST /api/pos/pricelists/prices` — body `{ "pricelist_id": 2, "items": [{"product_id": 412, "qty": 2}], "partner_id": 91 }`

### 3.6 Kapan `match` dipanggil, dan kenapa

Aplikasi yang menyimpan keranjang di state lokal tidak perlu memanggilnya tiap
kali item ditambah. Panggil **sekali**, tepat sebelum `bill/upsert` atau
`POST /api/pos/order` — atau saat layar ringkasan/promo dibuka.

Yang dikerjakan endpoint ini, dan yang harus ditiru sendiri kalau tidak dipakai:

- ambang `minimum_qty` dan `minimum_amount`, dievaluasi pada harga setelah
  pricelist **dan** pajak, bukan pada harga list
- jumlah klaim Buy X Get Y (beli 5 pada aturan "beli 2" = dua reward, bukan lima)
- `discount_max_amount`, dan diskon yang tidak boleh melebihi isi keranjang
- sasaran diskon: `order`, `cheapest` (satu unit produk termurah), atau `specific`
- mode `percent`, `per_order`, `per_point`
- program berkode yang baru ikut bermain setelah kodenya disertakan

Selisih sekecil apa pun di antaranya berarti pelanggan ditagih berbeda dari
yang dilakukan kasir POS Odoo untuk keranjang yang sama.

`claimable_rewards` juga membawa `reward_id` dan `discount_line_product_id`
yang persis dibutuhkan langkah berikutnya (3.6) untuk mencatat promonya.

### 3.7 Alur yang disarankan

1. Katalog → pakai `has_promotion` / `promotion_labels` untuk badge (tanpa panggilan tambahan)
2. Halaman detail → `promotion_details` untuk syarat dan hadiah
3. Keranjang berubah → `POST /api/pos/promotions/match`
4. Checkout → kirim `claimable_rewards` hasil langkah 3

---

### 3.8 Mencatat promo pada order & pembayaran

Penanda katalog dan hasil `match` hanya hidup di sisi frontend sampai promonya
ikut tercatat pada order. Dua endpoint yang sudah dipakai aplikasi menerima
field **opsional** untuk itu. Tanpa field-field ini keduanya berperilaku persis
seperti sebelumnya — aplikasi yang berjalan sekarang tidak perlu diubah.

Backend **tidak** menghitung ulang promo dan **tidak** mengubah total. Yang
dilakukannya adalah mencatat: baris potongan menjadi baris reward Odoo yang
sesungguhnya, sehingga laporan loyalty, `is_reward_line`, dan poin kupon benar.

**`POST /api/pos/order`** — per baris di dalam `lines[]`:

| Field | Tipe | Arti |
|---|---|---|
| `reward_id` | int | `loyalty.reward` yang menghasilkan baris ini |
| `coupon_id` | int | `loyalty.card` yang dipakai |
| `is_reward_line` | bool | Default `true` bila `reward_id` diisi; kirim eksplisit untuk menimpanya |
| `points_cost` | float | Poin yang dipotong baris ini |
| `reward_identifier_code` | string | Pengelompokan baris reward, seperti di POS Odoo |

Produk untuk baris reward diambil dari `promotion_details[].rewards[].discount_line_product_id`.

Baris reward mengikuti cara POS Odoo mencatatnya: produknya adalah
`discount_line_product_id` milik reward itu (ada di `promotion_details[].rewards[]`),
dengan `price_unit` **negatif**. Ini berlaku untuk keduanya — diskon maupun
produk gratis. Untuk produk gratis, produknya tetap masuk keranjang dengan harga
normal, lalu baris reward yang menihilkannya.

```json
{
  "session_id": 77,
  "lines": [
    { "product_id": 412, "qty": 2, "price_unit": 25000, "discount": 0 },

    { "product_id": 519, "qty": 1, "price_unit": 25000, "discount": 0 },
    { "product_id": 88, "qty": 1, "price_unit": -25000, "discount": 0,
      "reward_id": 9, "coupon_id": 31, "points_cost": 2,
      "reward_identifier_code": "bogo-1" }
  ]
}
```

Di atas: produk 412 dua porsi (pemicu promo), produk 519 satu porsi gratis pada
harga normal, dan produk 88 — `discount_line_product_id` milik reward 9 — yang
membatalkan harganya. `amount_total` ikut turun dengan sendirinya karena baris
negatif itu masuk hitungan.

`reward_id` atau `coupon_id` yang tidak ada → **404**. Mengirim field promo pada
database tanpa modul `pos_loyalty` → **400** dengan pesan yang menyebutkannya,
bukan diam-diam diabaikan.

**`POST /api/pos/order/pay`** — `coupon_data` opsional di level atas body:

```json
{ "session_id": 77, "payment_method_id": 3, "amount": 50000,
  "coupon_data": { "31": { "program_id": 7, "points": 2 } } }
```

Isinya diteruskan apa adanya ke `confirm_coupon_programs()` bawaan
`pos_loyalty` — inilah yang memotong poin kupon dan menerbitkan kupon hadiah,
dengan hasil yang sama seperti kasir POS Odoo. Dijalankan **sebelum** pembayaran
dicatat: kalau mesin loyalty menolak, tidak ada uang yang tercatat dan aplikasi
masih bisa memperbaiki keranjangnya.

Pengulangan pembayaran setelah timeout jaringan aman: bila order itu sudah
pernah menerbitkan kupon, `coupon_data` dilewati, bukan dijalankan dua kali.

### 3.9 Kamus ID promo — setiap field, asalnya dari mana

| Field | Model Odoo | Siapa yang menghasilkannya |
|---|---|---|
| `reward_id` | `loyalty.reward` | Odoo. Ambil dari `claimable_rewards[].reward_id` atau katalog `promotion_details[].rewards[].reward_id` |
| `coupon_id` | `loyalty.card` | Odoo. Dari `coupons/validate` → `data.coupon_id` |
| `points_cost` | — (angka) | Dihitung: `required_points` × jumlah klaim |
| `reward_identifier_code` | **tidak ada di Odoo** | **Dibuat aplikasi.** String acak, satu per klaim |
| `is_reward_line` | — (boolean) | **Ditentukan aplikasi.** Lihat di bawah |
| `discount_line_product_id` | `product.product` | Odoo, otomatis saat reward dibuat |

Susunan modelnya: satu **`loyalty.program`** (promonya) berisi **`loyalty.rule`**
(syaratnya: produk apa, berapa unit) dan **`loyalty.reward`** (hadiahnya).
`reward_id` menunjuk hadiah, bukan program.

**`discount_line_product_id` itu produk apa?** Produk teknis yang dibuat Odoo
sendiri setiap kali sebuah reward dibuat: `type: service`, `sale_ok: false`,
harga 0, namanya mengikuti deskripsi reward ("Gratis 1 Croissant"). Satu produk
per reward. Ia tidak pernah muncul di katalog POS — hanya menjadi wadah angka
potongan pada baris order.

**`is_reward_line` untuk apa?** Memisahkan "barang yang dipesan pelanggan" dari
"artefak potongan harga". Yang membacanya: laporan loyalty, alur refund
(membatalkan hadiah berbeda dari membatalkan pesanan), dan layar dapur — baris
promo tidak dimasak siapa pun. Karena itu hanya baris teknis yang ditandai;
menandai baris makanan akan mengeluarkannya dari antrean dapur.

**Kenapa hanya satu baris yang membawa field promo?** Pada contoh BOGO di 3.7,
dua baris pertama adalah barang yang benar-benar dipesan pelanggan — dapur
memasaknya, stok berkurang karenanya. Baris ketiga adalah promonya itu sendiri.
Menandai ketiganya membuat laporan menghitung kopi dan croissant sebagai hadiah,
dan pembatalan promo akan ikut menghapus makanannya.

**Menampilkan produk hadiah di UI.** Dari `claimable_rewards[]`:

```json
{ "reward_type": "product", "free_product_qty": 1.0,
  "reward_product_ids": [{ "id": 519, "name": "Croissant", "price": 20000.0 }],
  "estimated_discount": 20000.0, "discount_line_product_id": 88 }
```

`reward_product_ids` adalah produk hadiahnya. Bila isinya lebih dari satu,
pelanggan memilih salah satu (di Odoo ini terjadi ketika hadiahnya ditentukan
lewat product tag). Setelah dipilih, aplikasi menambahkan **dua** baris ke
order: produk hadiah pada harga normal, dan baris reward yang menihilkannya.
Baris produknya harus benar-benar ada — itulah yang membuat dapur memasaknya
dan stok berkurang.

## 4. Kitchen Display (KDS)

### 4.1 Dua sumber hidangan

| `source` | Asal | Kapan muncul |
|---|---|---|
| `pos_order` | `pos.order` | Setelah checkout dijalankan |
| `bill` | `poskas.bill` | Open bill — `pos.order` **belum** dibuat |

Keduanya memakai bentuk payload yang sama supaya bisa dirender satu komponen.
Yang harus diperhatikan client:

- **Kunci daftar adalah `uid`, bukan `id`.** ID keduanya berasal dari tabel
  berbeda, jadi `id` bisa bentrok. Format: `pos_order-123`, `bill-42`.
- **Route update state berbeda per `source`** (lihat 4.5).
- Bill yang sudah ditautkan ke `pos.order` (`bill.pos_order_id` terisi) **tidak**
  ikut dikirim — pesanannya sudah ada di antrean sebagai `pos_order`, dan
  menampilkan keduanya berarti hidangan yang sama muncul dua kali.

### 4.2 `GET /api/v2/pos/kitchen/orders`

Endpoint utama KDS: menentukan session aktif dan antreannya sekaligus. Simpan
`pos_config_id` di client, **bukan** `session_id` — session berganti tiap kasir
buka/tutup POS.

| Param | Default | Keterangan |
|---|---|---|
| `pos_config_id` | wajib | |
| `limit`, `offset` | 100 / 0 | |
| `table_id` | — | |
| `state` | `draft,paid` | state `pos.order` |
| `kitchen_state` | `pending,cooking,ready` | punya minimal satu baris pada state ini |
| **`source`** | `pos_order,bill` | csv; `pos_order` saja = perilaku sebelum rilis ini |
| **`bill_state`** | `open` | state `poskas.bill` |
| `require_today` | `false` | tolak session yang dibuka kemarin |

```bash
curl -H 'api-key: ********' \
  'https://kasprima.co.id/api/v2/pos/kitchen/orders?pos_config_id=5'
```

```json
{
  "success": true,
  "data": {
    "pos_config_id": 5,
    "session": { "id": 77, "name": "POS/00077", "state": "opened" },
    "orders": [ ],
    "reason": null,
    "open_session_count": 1,
    "stale_session_ids": [],
    "filters": {
      "state": ["draft", "paid"],
      "kitchen_state": ["pending", "cooking", "ready"],
      "source": ["pos_order", "bill"],
      "bill_state": ["open"]
    }
  }
}
```

**Saat tidak ada session terbuka**, `session` bernilai `null` dan `reason` terisi
(`no_open_session` atau `no_session_today`), tetapi **`orders` tetap bisa berisi
bill**: open bill hidup di luar `pos.session` dan bisa melewati pergantian
session. Jangan tampilkan layar kosong hanya karena `reason != null`.

### 4.3 Bentuk satu pesanan

```json
{
  "id": 42,
  "uid": "bill-42",
  "source": "bill",
  "name": "Bill - Budi (Meja 7)",
  "state": "open",
  "state_label": "Open",
  "kitchen_state": "cooking",
  "date_order": "2026-08-21T03:11:04",
  "processing_started_at": "2026-08-21T03:15:00",
  "estimated_ready_at": "2026-08-21T03:27:00",
  "estimated_time_max": 12,
  "estimated_time_total": 18,
  "amount_total": 150000.0,
  "amount_tax": 0.0,
  "amount_paid": 50000.0,
  "company_id": 3,
  "session": null,
  "config": { "id": 5, "name": "Resto Palawi" },
  "partner": null,
  "table": { "id": 19, "table_number": 7, "floor": { "id": 2, "name": "Lantai 1" } },
  "pricelist": null,
  "general_note": null,
  "tracking_number": null,
  "pos_reference": null,
  "bill": {
    "id": 42,
    "customer_name": "Budi",
    "waiter_name": "Sari",
    "type_order": "dine_in",
    "is_dp": true,
    "dp_amount": 50000.0,
    "amount_due": 100000.0,
    "table_ref": null,
    "pos_order_id": null,
    "write_date": "2026-08-21T03:16:22"
  },
  "lines": [
    {
      "id": 113,
      "uid": "bill-113",
      "source": "bill",
      "product_id": 412,
      "product_tmpl_id": 88,
      "product_name": "Kopi Susu Gula Aren",
      "full_product_name": "Kopi Susu Gula Aren",
      "qty": 2.0,
      "price_unit": 25000.0,
      "discount": 0.0,
      "price_subtotal": 50000.0,
      "price_subtotal_incl": 50000.0,
      "estimated_time": 5,
      "attributes": [],
      "customer_note": "less sugar",
      "note": "less sugar",
      "is_reward_line": false,
      "reward_id": null,
      "coupon_id": null,
      "kitchen_state": "cooking",
      "cooking_started_at": "2026-08-21T03:15:00",
      "ready_at": null,
      "ready_source": null
    }
  ]
}
```

**Perbedaan `source: "bill"`**

| Field | Nilai pada bill | Sebabnya |
|---|---|---|
| `session` | selalu `null` | Open bill tidak terikat `pos.session` |
| `amount_tax` | `0.0` | Bill tidak melewati mesin pajak POS |
| `amount_paid` | DP | Yang benar-benar masuk baru uang muka |
| `price_subtotal` / `_incl` | sama | Bill hanya punya satu angka subtotal |
| `attributes` | `[]` | Varian belum dipilih di level bill |
| `is_reward_line` | selalu `false` | Baris reward baru lahir saat checkout |
| `partner`, `pricelist`, `tracking_number` | `null` | Belum ada di tahap bill |
| `bill` | objek | `null` pada `source: "pos_order"` |

**`estimated_time`** (menit) berasal dari addon `product_estimated_time`.
`estimated_time_max` adalah estimasi pesanan siap (dapur memasak paralel);
`estimated_time_total` untuk dapur yang mengerjakan satu per satu.

### 4.4 Status dapur

Per baris, bukan per pesanan — dapur multi-stasiun menyelesaikan tiap hidangan
pada waktu berbeda.

```
pending ──▶ cooking ──▶ ready ──▶ served
```

Transisi melompat ditolak dengan HTTP 400. Nilai kosong dibaca sebagai
`pending`.

`kitchen_state` di level pesanan **diturunkan** dari baris-barisnya, tidak
pernah di-set langsung:

| Kondisi baris (di luar baris reward) | Hasil |
|---|---|
| semua `served` | `served` |
| semua `ready` atau `served` | `ready` |
| ada satu saja `cooking`/`ready`/`served` | `cooking` |
| sisanya | `pending` |

`ready_source` membedakan `staff` (ditandai petugas) dari `timer` (hitung mundur
habis). Hitung mundur yang habis bukan bukti makanan sudah jadi.

### 4.5 Menggeser status satu hidangan

Pilih route berdasarkan `source` pada baris:

```
PUT /api/v2/pos/orders/<order_id>/lines/<line_id>/state     # source: pos_order
PUT /api/v2/pos/bills/<bill_id>/lines/<line_id>/state       # source: bill
```

Body:
```json
{ "state": "cooking", "source": "staff" }
```

- `state` (atau `action`): `cooking` | `ready` | `served`
- `source`: `staff` (default) | `timer`

Response mengembalikan pesanan/bill utuh setelah perubahan, jadi client tidak
perlu memanggil ulang endpoint daftar:

```json
{ "success": true, "message": "Kitchen state updated to 'cooking'", "data": { } }
```

Kesalahan transisi:
```json
{ "success": false,
  "message": "Bill line Kopi Susu Gula Aren cannot become served because its kitchen state is pending (should be ready).",
  "status": 400 }
```

### 4.6 Endpoint KDS lain

| Endpoint | Keterangan |
|---|---|
| `GET /api/v2/pos/orders?pos_session_id=` atau `?pos_config_id=` | Daftar mentah; mendukung `source`, `state`, `kitchen_state`, `table_id`, `bill_state`. Tanpa filter apa pun, defaultnya antrean dapur |
| `GET /api/v2/pos/orders/<order_id>` | Detail satu `pos.order` |
| `GET /api/v2/pos/bills/<bill_id>` | Detail satu open bill, bentuk sama |

Paging dijalankan **per sumber** lalu digabung dan diurutkan FIFO
(`date_order` menaik). Untuk KDS ini tidak masalah — antreannya jauh lebih
pendek dari `limit` — tetapi client yang benar-benar mem-paging sebaiknya
meminta satu `source` saja.

### 4.7 Realtime (WebSocket)

`GET /api/v2/pos/kitchen/realtime?pos_config_id=5`

```json
{
  "success": true,
  "data": {
    "pos_config_id": 5,
    "websocket_url": "wss://kasprima.co.id/websocket?version=18.0-5",
    "channel": "pos_kds.9f2c1a…",
    "notification_type": "pos_kds/update",
    "snapshot_url": "/api/v2/pos/kitchen/orders?pos_config_id=5",
    "protocol": { "subscribe_event": "subscribe", "keepalive_seconds": 50 }
  }
}
```

Alur:

1. Panggil endpoint ini, simpan `channel` (token kapabilitas — perlakukan seperti rahasia)
2. Buka `websocket_url`
3. Kirim: `{"event_name": "subscribe", "data": {"channels": ["pos_kds.9f2c1a…"], "last": 0}}`
4. Ping tiap ~50 detik
5. Setiap notifikasi bertipe `pos_kds/update` → **ambil ulang** `snapshot_url`

Payload event sengaja hanya berisi ID dan jenis perubahan, tidak memuat detail
pesanan. Ia adalah sinyal invalidasi, bukan sumber data — event yang terlewat
atau reconnect tidak akan merusak antrean karena isinya selalu dibaca ulang
lewat REST.

**Daftar `event`**

| Event | Pemicu |
|---|---|
| `order.created`, `order.updated`, `order.state_changed`, `order.deleted` | `pos.order` |
| `line.created`, `line.updated`, `line.kitchen_state_changed`, `line.deleted` | `pos.order.line` |
| `bill.created`, `bill.updated`, `bill.deleted` | `poskas.bill` |
| `bill.lines_replaced` | Upsert menulis ulang keranjang bill |
| `bill.line.created`, `bill.line.updated`, `bill.line.kitchen_state_changed`, `bill.line.deleted` | `poskas.bill.line` |
| `session.created`, `session.changed` | `pos.session` |

Bill yang menempel pada `pos.order` tidak menerbitkan event apa pun — ia hanya
cermin, dan pesanannya sudah punya event sendiri.

---

## 5. Open bill

`auth="none"` — lihat catatan keamanan di 1.2.

| Endpoint | Method | Body / Param |
|---|---|---|
| `/api/pos/bill/open` | GET | `config_id`, `table_id` |
| `/api/pos/bill/open_list` | GET | `config_id` |
| `/api/pos/bill/upsert` | POST | lihat di bawah |
| `/api/pos/bill/move` | PUT | `values: { id, new_table_id, if_match_write_date }` |
| `/api/pos/bill/cancel` | PUT | `values: { id, if_match_write_date }` |
| `/api/pos/bill/delete` | POST | `values: { id }` atau `{ config_id, table_id }` — soft delete ke state `paid` |
| `/api/pos/bill/fingerprint` | POST | `{ pos_config_id }` → `{ open_count, max_write_date, fingerprint }` |

**Upsert**

```json
{
  "values": {
    "config_id": 5,
    "name_customer": "Budi",
    "name_waiters": "Sari",
    "table_id": "7",
    "type_order": "dine_in",
    "dp_amount": 50000,
    "force_new": false,
    "if_match_write_date": "2026-08-21 03:16:22",
    "items": [
      { "product_id": 412, "qty": 2, "unit_price": 25000, "discount_percent": 0, "note": "less sugar" }
    ]
  }
}
```

- `table_id` yang bukan ID `restaurant.table` valid disimpan apa adanya sebagai teks (`table_ref`)
- `if_match_write_date` tidak cocok → HTTP 409 `{"code": "CONFLICT"}`
- `items` kosong → bill dihapus, response `type: "NOOP_CART_EMPTY"`
- `type` pada response: `CREATED_NEW` | `UPDATED_EXISTING` | `NOOP_CART_EMPTY`

**Promo pada open bill.** Bill juga membawa promo — pelanggan melihat totalnya
sebelum membayar. Bedanya dengan order: bill **tidak bisa** menampung baris
berharga negatif (subtotal-nya menjepit nilai negatif ke nol), jadi promo di
tahap ini dinyatakan sebagai diskon per baris:

| Promo | Cara menuliskannya di `items[]` |
|---|---|
| Diskon 20% pada satu produk | `discount_percent: 20` pada baris itu |
| Produk gratis | baris produknya dengan `discount_percent: 100` |
| Diskon nominal pada order | sebar sebagai `discount_percent` per baris |

Tiga field opsional mencatat promo **mana** yang dipakai, supaya identitasnya
tidak hilang sampai bill menjadi order:

```json
{ "product_id": 519, "qty": 1, "unit_price": 20000, "discount_percent": 100,
  "reward_id": 9, "coupon_id": 31, "reward_identifier_code": "bogo-a1f3" }
```

`reward_id`/`coupon_id` yang tidak ada di database dibuang beserta peringatan di
log — bill yang mengaku memakai promo yang tidak pernah ada hanya membuat
laporan berbohong.

**`is_reward_line` jangan diisi di bill.** Di `pos.order`, baris reward adalah
baris teknis berharga negatif yang memang bukan makanan. Di bill, promo
menempel pada baris makanannya sendiri: croissant gratis **tetap harus
dimasak**. Baris ber-`is_reward_line` lahir `kitchen_state: served` dan hilang
dari layar dapur — pelanggan lalu menunggu makanan yang tidak pernah dibuat.
Karena itu flag ini tidak pernah disimpulkan dari `reward_id`; isi hanya bila
barisnya memang bukan hidangan (misal baris voucher berharga nol).

Saat checkout, susun ulang barisnya untuk `POST /api/pos/order` memakai
`discount_line_product_id` berharga negatif (3.8) — itulah bentuk yang dipahami
laporan loyalty Odoo.

**Upsert dan progres dapur.** Upsert menulis ulang **seluruh** keranjang
(hapus semua baris lalu buat lagi). Status dapur yang sudah berjalan dipulihkan
dengan mencocokkan pasangan **(produk, note)**. Artinya:

- menambah item baru **tidak** mengembalikan hidangan lain ke `pending`
- mengubah `note` sebuah baris membuatnya dianggap hidangan baru, dan statusnya kembali `pending`

Response bill kini memuat `kitchen_state` di level bill dan, per item,
`kitchen_state`, `cooking_started_at`, `ready_at`, `ready_source`,
`is_reward_line`, `reward_id`, `coupon_id`, `reward_identifier_code`.

---

## 6. Kode error

| HTTP | Kapan |
|---|---|
| 400 | Param hilang/salah tipe, transisi kitchen state tidak sah |
| 401 | API key salah atau tidak dikirim |
| 404 | Order / bill / config / produk tidak ada |
| 405 | Method tidak diizinkan untuk model di `connection.api` |
| 409 | `if_match_write_date` tidak cocok, atau meja tujuan sudah terisi |
| 500 | Kesalahan tak terduga (`api_key_palawi` belum diset juga 500) |
| 503 | `pos_order_extra_states` belum terpasang / versinya terlalu lama (KDS realtime) |

---

## 7. Endpoint aplikasi POS existing

Alur yang dipakai aplikasi Android saat ini, semuanya di `rest_api_odoo` dan
**tidak berubah** oleh pekerjaan promo:

| Alur | Endpoint |
|---|---|
| Simpan keranjang sebagai open bill | `POST /api/pos/bill/upsert` |
| Buat order draft | `POST /api/pos/order` |
| Daftar / batal / hitung / detail order | `GET /api/pos/order`, `PUT /api/pos/order/cancel`, `GET /api/pos/order/count`, `GET /api/pos/order/{id}` |
| Bayar | `POST /api/pos/order/pay` |
| QRIS | `POST /api/v1/payments/qris` |
| Hapus bill setelah lunas | `POST /api/pos/bill/delete` |

Dine-in: `bill/upsert` → `order/pay` (opsional `payments/qris` di tengah) →
`bill/delete`.

Perubahannya hanya berupa **tambahan** yang bersifat opsional:

- response `bill/*` membawa field dapur (`kitchen_state`, `cooking_started_at`,
  `ready_at`, `ready_source`)
- `POST /api/pos/order` menerima penanda reward per baris, dan
  `POST /api/pos/order/pay` menerima `coupon_data` — lihat 3.8

Tidak ada field yang dihapus atau di-rename, tidak ada parameter request yang
berubah artinya, dan payload yang dikirim aplikasi sekarang menghasilkan order
yang sama persis seperti sebelum rilis ini.

## 8. Checklist integrasi frontend

- [ ] `ignoreUnknownKeys = true` (atau setara) di parser JSON
- [ ] KDS memakai `uid` sebagai kunci daftar, bukan `id`
- [ ] KDS memilih route update state berdasarkan `source`
- [ ] Layar KDS tetap merender `orders` walau `session == null` / `reason != null`
- [ ] Field promo sudah ditambahkan di GET Fields `connection.api` (tanpa itu tidak ada yang terkirim)
- [ ] Badge katalog memakai `has_promotion`; `has_order_promotion` ditampilkan berbeda (mis. banner, bukan badge produk)
- [ ] Perhitungan promo yang mengikat tetap lewat `/api/pos/promotions/match`, bukan dari penanda katalog
- [ ] Baris potongan dikirim dengan `reward_id` agar tercatat sebagai baris reward Odoo, bukan sekadar `discount`
- [ ] Rollback cepat tersedia: `?source=pos_order` mengembalikan perilaku KDS sebelum rilis ini
