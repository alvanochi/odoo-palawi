# POS Payment Gateway (Odoo 18)

Menyimpan credential payment gateway (**Paper.id**, dan gateway lain) **per POS config**,
menggantikan env var seperti `PAPER_BASE_URL`, `PAPER_CLIENT_ID`, `PAPER_CLIENT_SECRET`.
Merchant atau gateway baru cukup ditambahkan lewat UI, tanpa develop/deploy ulang
(kode integrasi gateway-nya sendiri tetap perlu dibuat sekali per gateway).

## Konsep
- **Payment Gateway** (`pos.payment.gateway`): master data. `code` unik (mis. `paper`,
  `midtrans`, `xendit`) + default base URL. Paper.id sudah tersedia saat install.
- **Credential** (`pos.payment.gateway.credential`): per (POS config, gateway) —
  `base_url`, `client_id`, `client_secret`, plus **Extra Parameters** (key/value)
  untuk kebutuhan khusus gateway, misal `webhook_token`, `merchant_code`.
- 1 POS config boleh punya banyak gateway, tapi hanya 1 credential aktif per gateway.

## Install
1. Copy folder `pos_payment_gateway` ke addons path.
2. `odoo-bin -d <db> -i pos_payment_gateway --stop-after-init`
3. Settings > Users > centang **Point of Sale: Payment Gateway Credential Manager**.
4. Menu: **Point of Sale > Configuration > Payment Gateway Credentials / Payment Gateways**.

## Akses
- Hanya grup *Payment Gateway Credential Manager* yang bisa melihat menu, CRUD, dan membaca secret.
- Record rule multi-company aktif.
- Perubahan dicatat di chatter; nilai client secret tidak pernah ditulis ke chatter/log.
- Catatan: nilai Extra Parameters tidak di-mask di form. Simpan secret utama di `client_secret`.

## API
`GET /api/payment-gateway/credential/<pos_config_id>[?gateway=<code>]`

Auth: API key Odoo milik user grup manager (Preferences > Account Security > New API Key).

```bash
# satu gateway -> data berupa object
curl -H "Authorization: Bearer <odoo_api_key>" \
  "https://odoo.domain.id/api/payment-gateway/credential/5?gateway=paper"

# semua gateway aktif di POS itu -> data berupa list
curl -H "Authorization: Bearer <odoo_api_key>" \
  "https://odoo.domain.id/api/payment-gateway/credential/5"
```

Response 200 (dengan `?gateway=paper`):
```json
{
  "success": true,
  "data": {
    "gateway": "paper",
    "gateway_name": "Paper.id",
    "pos_config_id": 5,
    "pos_config_name": "Outlet Depok",
    "base_url": "https://open-api.paper.id/api/v1",
    "client_id": "abc123xyz",
    "client_secret": "s3cr3t-v4lu3",
    "extra_params": {},
    "write_date": "2026-10-01 08:15:00"
  }
}
```

| Status | code | Kondisi |
|---|---|---|
| 401 | UNAUTHORIZED | API key tidak ada / salah |
| 403 | FORBIDDEN | user bukan manager / beda company |
| 404 | POS_CONFIG_NOT_FOUND | POS config tidak ada |
| 404 | GATEWAY_NOT_FOUND | `?gateway=` tidak dikenal |
| 404 | CREDENTIAL_NOT_FOUND | POS belum punya credential aktif untuk gateway itu |

Tanpa `?gateway=`, POS yang belum punya credential mengembalikan `200` dengan `data: []`.

Kalau banyak database di satu server, pastikan `dbfilter` / `db_name` sudah menunjuk
ke satu DB untuk domain ini, karena route memakai `auth="none"`.

> Response berisi secret plain: panggil hanya server-to-server lewat HTTPS.

## Pakai dari kode Odoo (disarankan untuk backend)
```python
cred = self.env["pos.payment.gateway.credential"].get_credential(pos_config.id, "paper")
if not cred:
    raise UserError("Credential Paper untuk POS ini belum diatur.")
base_url = cred["base_url"]
client_id = cred["client_id"]
client_secret = cred["client_secret"]
webhook_token = cred["extra_params"].get("webhook_token")
```

Fallback masa transisi: kalau record belum ada, method membaca env var
`<CODE>_BASE_URL`, `<CODE>_CLIENT_ID`, `<CODE>_CLIENT_SECRET`
(untuk `paper`: `PAPER_BASE_URL`, dst.) dan mengembalikan `source: "env"`.
Setelah semua POS terisi, panggil dengan `fallback_env=False` lalu hapus env var-nya.
Jangan kirim hasil method ini ke frontend POS.

## Menambah gateway baru
1. Payment Gateways > New: isi nama, `code`, default base URL.
2. Payment Gateway Credentials > New: pilih POS + gateway, isi credential.
3. Di kode integrasi gateway tersebut, panggil `get_credential(pos_config.id, "<code>")`.

## Test
```bash
odoo-bin -d <db> -u pos_payment_gateway --test-enable --test-tags /pos_payment_gateway --stop-after-init
```
