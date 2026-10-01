# Requirements — POS Payment Gateway Credential

## Context
- Odoo 18.0, modul baru `pos_payment_gateway` (depends: `point_of_sale`, `mail`).
- Sebelumnya: credential Paper.id dari env var `PAPER_BASE_URL`, `PAPER_CLIENT_ID`,
  `PAPER_CLIENT_SECRET` → satu merchant saja, merchant baru butuh develop/deploy.
- Tujuan: credential per POS config untuk Paper.id **dan gateway lain**, dikelola via UI
  oleh user tertentu, bisa diambil lewat API dan method backend.

## User Stories
- US-1 As a Payment Gateway Credential Manager, I want CRUD credential per POS config & gateway.
- US-2 As a Payment Gateway Credential Manager, I want menambah gateway baru lewat UI.
- US-3 As a sistem integrasi, I want mengambil credential by `pos_config_id` (+ gateway).
- US-4 As a user tanpa grup, I must not see credentials or secrets.

## Acceptance Criteria
- REQ-1 WHEN manager membuat credential THEN SHALL simpan gateway, POS, base_url, client_id, client_secret, extra params.
- REQ-2 WHEN gateway dipilih THEN base_url SHALL terisi dari default gateway; boleh diubah; harus https, trailing slash dibuang.
- REQ-3 WHEN sudah ada credential aktif untuk (POS, gateway) THEN SHALL tolak duplikat.
- REQ-4 WHEN gateway code tidak sesuai `[a-z0-9_]+` atau duplikat THEN SHALL tolak.
- REQ-5 WHEN user tanpa grup akses THEN SHALL ditolak (menu hidden, ACL deny).
- REQ-6 client_secret SHALL tampil masked dan tidak ditulis ke chatter.
- REQ-7 API `GET /api/payment-gateway/credential/<id>?gateway=<code>` SHALL mengembalikan object; tanpa `gateway` SHALL mengembalikan list.
- REQ-8 API SHALL mengembalikan 401/403/404 (POS_CONFIG_NOT_FOUND, GATEWAY_NOT_FOUND, CREDENTIAL_NOT_FOUND) sesuai kondisi.
- REQ-9 Helper `get_credential(pos_config_id, code)` SHALL fallback ke env var `<CODE>_*` selama transisi.

## Out of Scope
- Implementasi flow pembayaran tiap gateway.
- Enkripsi secret at-rest, rotasi otomatis.
- Masking nilai Extra Parameters.

## Keputusan (asumsi, bisa direvisi)
- Pemanggil API: service eksternal, auth API key Odoo (Bearer).
- Gateway = model master (bukan selection) supaya gateway baru tanpa develop.
- Menggantikan draft `pos_paper_credential` (belum pernah di-deploy).
