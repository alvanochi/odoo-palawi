# -*- coding: utf-8 -*-
"""Backfill pajak pada order POS lama yang dibuat tanpa tax_ids.

Order lama dari API tersimpan dengan harga tax-inclusive tetapi tanpa pajak
(`price_subtotal == price_subtotal_incl`, `tax_ids` kosong, `amount_tax = 0`).
Skrip ini mengekstrak pajak dari harga itu dengan pajak produk SAAT INI, memakai
rumus yang sama dengan `_extract_line_taxes` di rest_api_odoo.

PERHATIAN
* Hanya mengubah data laporan POS. Jurnal akuntansi session yang sudah ditutup
  dan invoice tidak ikut berubah.
* Pajak produk bisa sudah berbeda dari saat order dibuat; hasilnya estimasi.
* `amount_total` / `price_subtotal_incl` TIDAK diubah.

Cara pakai (BACKUP DATABASE DULU):

    # 1. dry-run (default): hanya menampilkan ringkasan, tidak mengubah apa pun
    odoo-bin shell -d <db> --no-http < sales_dashboard/scripts/backfill_pos_tax.py

    # 2. terapkan
    APPLY=1 odoo-bin shell -d <db> --no-http < sales_dashboard/scripts/backfill_pos_tax.py

    # opsional: batasi mulai tanggal order (UTC) dan/atau company
    DATE_FROM=2026-01-01 COMPANY_ID=1 APPLY=1 odoo-bin shell ...

Setiap baris yang diubah dicatat di tabel `pos_tax_backfill_log`. Rollback:

    UPDATE pos_order_line pol SET price_subtotal = l.old_subtotal
      FROM pos_tax_backfill_log l WHERE l.line_id = pol.id;
    DELETE FROM account_tax_pos_order_line_rel rel USING pos_tax_backfill_log l
     WHERE rel.pos_order_line_id = l.line_id;
    UPDATE pos_order po SET amount_tax = (
        SELECT COALESCE(SUM(price_subtotal_incl - price_subtotal), 0)
          FROM pos_order_line WHERE order_id = po.id)
     WHERE po.id IN (SELECT DISTINCT order_id FROM pos_tax_backfill_log);
"""

import os
from collections import defaultdict

APPLY = os.environ.get("APPLY") == "1"
DATE_FROM = os.environ.get("DATE_FROM") or None
COMPANY_ID = int(os.environ["COMPANY_ID"]) if os.environ.get("COMPANY_ID") else None

cr = env.cr  # noqa: F821  (tersedia di odoo-bin shell)
Tax = env["account.tax"]  # noqa: F821
Product = env["product.product"]  # noqa: F821

# Pajak yang rumusnya linear terhadap harga. Tipe fixed tidak bisa diekstrak
# dengan rasio, jadi barisnya dilewati dan dilaporkan.
LINEAR_TYPES = ("percent", "division")

where = ["po.state IN ('paid', 'done', 'invoiced')",
         "pol.price_subtotal = pol.price_subtotal_incl",
         "pol.price_subtotal_incl != 0",
         "NOT EXISTS (SELECT 1 FROM account_tax_pos_order_line_rel r "
         "WHERE r.pos_order_line_id = pol.id)"]
params = []
if DATE_FROM:
    where.append("po.date_order >= %s")
    params.append(DATE_FROM)
if COMPANY_ID:
    where.append("po.company_id = %s")
    params.append(COMPANY_ID)

cr.execute(
    """
    SELECT pol.id, pol.order_id, pol.product_id, pol.price_subtotal_incl,
           po.company_id
      FROM pos_order_line pol
      JOIN pos_order po ON po.id = pol.order_id
     WHERE {where}
     ORDER BY pol.id
    """.format(where=" AND ".join(where)),
    params,
)
candidates = cr.fetchall()

ratio_cache = {}   # (company_id, tuple(tax ids)) -> rasio incl/excl atau None
tax_cache = {}     # (company_id, product_id) -> account.tax recordset
updates = []       # (line_id, order_id, old_subtotal, new_subtotal, tax_ids)
skipped = defaultdict(int)

for line_id, order_id, product_id, incl, company_id in candidates:
    if not product_id:
        skipped["no_product"] += 1
        continue
    key = (company_id, product_id)
    if key not in tax_cache:
        company = env["res.company"].browse(company_id)  # noqa: F821
        product = Product.browse(product_id)
        tax_cache[key] = product.taxes_id.filtered_domain(
            Tax._check_company_domain(company)
        )
    taxes = tax_cache[key]
    if not taxes:
        skipped["product_without_tax"] += 1
        continue
    if any(t.amount_type not in LINEAR_TYPES for t in taxes):
        skipped["non_linear_tax"] += 1
        continue

    rkey = (company_id, tuple(taxes.ids))
    if rkey not in ratio_cache:
        company = env["res.company"].browse(company_id)  # noqa: F821
        res = taxes.compute_all(1000.0, currency=company.currency_id, quantity=1.0)
        excl = res["total_excluded"]
        ratio_cache[rkey] = (res["total_included"] / excl) if excl else None
    ratio = ratio_cache[rkey]
    if not ratio:
        skipped["bad_ratio"] += 1
        continue

    currency = env["res.company"].browse(company_id).currency_id  # noqa: F821
    new_subtotal = currency.round(incl / ratio)
    updates.append((line_id, order_id, incl, new_subtotal, taxes.ids))

total_tax = sum(u[2] - u[3] for u in updates)
orders = {u[1] for u in updates}

print("=" * 60)
print("MODE            :", "APPLY" if APPLY else "DRY-RUN (tidak ada perubahan)")
print("Filter          :", "date_from=%s company=%s" % (DATE_FROM, COMPANY_ID))
print("Kandidat baris  :", len(candidates))
print("Baris diubah    :", len(updates))
print("Order terdampak :", len(orders))
print("Total pajak     : %.2f" % total_tax)
print("Dilewati        :", dict(skipped) or "-")
print("=" * 60)

if APPLY and updates:
    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_tax_backfill_log (
            line_id integer PRIMARY KEY,
            order_id integer,
            old_subtotal numeric,
            new_subtotal numeric,
            created_at timestamp DEFAULT now()
        )
        """
    )
    for line_id, order_id, old, new, tax_ids in updates:
        cr.execute(
            "INSERT INTO pos_tax_backfill_log (line_id, order_id, old_subtotal, new_subtotal) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (line_id) DO NOTHING",
            (line_id, order_id, old, new),
        )
        cr.execute(
            "UPDATE pos_order_line SET price_subtotal = %s WHERE id = %s",
            (new, line_id),
        )
        for tax_id in tax_ids:
            cr.execute(
                "INSERT INTO account_tax_pos_order_line_rel "
                "(pos_order_line_id, account_tax_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (line_id, tax_id),
            )
    cr.execute(
        """
        UPDATE pos_order po
           SET amount_tax = (
               SELECT COALESCE(SUM(l.price_subtotal_incl - l.price_subtotal), 0)
                 FROM pos_order_line l WHERE l.order_id = po.id)
         WHERE po.id = ANY(%s)
        """,
        (list(orders),),
    )
    cr.commit()
    env.invalidate_all()  # noqa: F821
    print("Selesai. Perubahan di-commit; log di tabel pos_tax_backfill_log.")
elif APPLY:
    print("Tidak ada baris yang perlu diubah.")
else:
    print("Dry-run selesai. Jalankan ulang dengan APPLY=1 untuk menerapkan.")
