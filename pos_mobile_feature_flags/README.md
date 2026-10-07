# POS Mobile Feature Flags (Odoo 18)

Flag fitur dinamis untuk app Android POS, **per POS Config**.

## Cara kerja
- Katalog: 16 modul (master flag `module.<modul>`) + 72 fitur mobile (key unik `<modul>.<fitur>`), di-seed dari Excel (`noupdate`, jadi edit via UI tidak ditimpa saat upgrade).
- Per POS: pilih **Mobile Plan** (Lite/Medium/Enterprise) -> tekan **Apply Plan Defaults**, lalu toggle modul/fitur sesuai kebutuhan.
- Efektif = master modul AND flag fitur. Fitur/modul baru otomatis ditambahkan ke semua POS (default sesuai plan).
- Menu: Point of Sale > Configuration > Mobile Feature Flags (Flags per POS / Modules / Features).

## API
`GET /api/pos/feature-flags/<pos_config_id>[?detail=1]`
`GET /api/pos/feature-flags` (semua POS yang bisa diakses user)

Auth: session Odoo, atau `Authorization: Bearer <API key user>`; user harus POS User.

```json
{"pos_config_id": 3, "pos_config_name": "Palawi Kasir 1", "plan": "medium",
 "modules": {"module.cashier": true, "module.kds": true},
 "flags": {"cashier.split_bill": true, "table.merge": false},
 "version": "a1b2c3d4e5f60718"}
```
`flags` sudah efektif (master sudah diperhitungkan). Key yang tidak dikirim -> app pakai default bawaan.
