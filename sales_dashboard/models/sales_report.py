# -*- coding: utf-8 -*-
"""Model laporan penjualan FOOM.

Model ini adalah SQL view read-only di atas baris invoice pelanggan yang sudah
posted. Semua method agregasi untuk dashboard OWL ada di sini supaya perhitungan
tetap terjadi di sisi database, bukan dengan mengiterasi record di Python.
"""

import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Granularitas tren yang diizinkan masuk ke DATE_TRUNC. Nilai dari client
# selalu divalidasi terhadap whitelist ini sebelum menyentuh SQL.
GRANULARITIES = ("hour", "day", "week", "month", "year")

# Batas rentang (dalam hari) untuk pemilihan granularitas otomatis.
AUTO_GRANULARITY_STEPS = (
    (2, "hour"),
    (92, "day"),
    (400, "week"),
    (1095, "month"),
)


class FoomSalesReport(models.Model):
    """Satu baris = satu baris produk pada invoice / credit note yang posted."""

    _name = "foom.sales.report"
    _description = "FOOM Sales Report"
    _auto = False
    _rec_name = "date_ts"
    _order = "date_ts desc"

    date_ts = fields.Datetime(
        string="Transaction Time",
        readonly=True,
        help="Order date from the Sales Order when available, "
             "otherwise the invoice creation time.",
    )
    invoice_date = fields.Date(string="Invoice Date", readonly=True)
    move_id = fields.Many2one("account.move", string="Invoice", readonly=True)
    move_type = fields.Selection(
        [("out_invoice", "Customer Invoice"), ("out_refund", "Credit Note")],
        string="Document Type",
        readonly=True,
    )
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product Template", readonly=True
    )
    categ_id = fields.Many2one("product.category", string="Product Category", readonly=True)
    user_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    team_id = fields.Many2one("crm.team", string="Sales Team", readonly=True)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        readonly=True,
        help="Warehouse of the delivery that fulfilled this invoice line.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        readonly=True,
        help="Stock location the goods were actually shipped from.",
    )
    journal_id = fields.Many2one("account.journal", string="Journal", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    quantity = fields.Float(string="Qty", readonly=True)
    price_subtotal = fields.Float(
        string="Revenue",
        readonly=True,
        help="Untaxed amount, expressed in the company currency.",
    )
    price_tax = fields.Float(
        string="Sales Tax",
        readonly=True,
        help="Tax amount of the line in company currency "
             "(negative for credit notes).",
    )
    price_total = fields.Float(
        string="Revenue incl. Tax",
        readonly=True,
        help="Revenue plus tax, in company currency.",
    )
    order_count = fields.Integer(string="Lines", readonly=True)

    # ------------------------------------------------------------------
    # Definisi SQL view
    # ------------------------------------------------------------------

    def _has_move_team_column(self):
        """`account.move.team_id` disediakan oleh modul lain dan tidak selalu ada.

        Dicek langsung ke information_schema supaya view tetap bisa dibuat pada
        instance yang tidak memilikinya, dengan team_id bernilai NULL.
        """
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'account_move' AND column_name = 'team_id'
            """
        )
        return bool(self.env.cr.fetchone())

    def _select_clause(self):
        team_expr = "am.team_id" if self._has_move_team_column() else "NULL::integer"
        return """
            aml.id                                      AS id,
            am.id                                       AS move_id,
            am.move_type                                AS move_type,
            am.invoice_date                             AS invoice_date,
            COALESCE(so.date_order, am.create_date)     AS date_ts,
            am.partner_id                               AS partner_id,
            am.invoice_user_id                          AS user_id,
            {team_expr}                                 AS team_id,
            dlv.warehouse_id                            AS warehouse_id,
            dlv.location_id                             AS location_id,
            am.journal_id                               AS journal_id,
            am.company_id                               AS company_id,
            aml.product_id                              AS product_id,
            pp.product_tmpl_id                          AS product_tmpl_id,
            pt.categ_id                                 AS categ_id,
            CASE WHEN am.move_type = 'out_refund'
                 THEN -aml.quantity ELSE aml.quantity END   AS quantity,
            -aml.balance                                AS price_subtotal,
            CASE WHEN COALESCE(aml.price_subtotal, 0) = 0 THEN 0.0
                 ELSE -aml.balance
                      * (aml.price_total - aml.price_subtotal)
                      / aml.price_subtotal END              AS price_tax,
            CASE WHEN COALESCE(aml.price_subtotal, 0) = 0 THEN -aml.balance
                 ELSE -aml.balance * aml.price_total
                      / aml.price_subtotal END              AS price_total,
            1                                         AS order_count
        """.format(team_expr=team_expr)

    def _from_clause(self):
        return """
            FROM account_move_line aml
            JOIN account_move am           ON am.id = aml.move_id
            LEFT JOIN product_product pp   ON pp.id = aml.product_id
            LEFT JOIN product_template pt  ON pt.id = pp.product_tmpl_id
            LEFT JOIN LATERAL (
                SELECT so2.date_order
                  FROM sale_order_line_invoice_rel rel
                  JOIN sale_order_line sol ON sol.id = rel.order_line_id
                  JOIN sale_order so2      ON so2.id = sol.order_id
                 WHERE rel.invoice_line_id = aml.id
                 ORDER BY so2.date_order
                 LIMIT 1
            ) so ON TRUE
            -- Outlet dipisah per warehouse/location, jadi keduanya diambil dari
            -- pengiriman yang BENAR-BENAR terjadi: invoice line -> sale order
            -- line -> stock.move yang sudah `done`, bukan dari warehouse yang
            -- dipilih di Sales Order.
            --
            -- Satu baris invoice bisa terpenuhi oleh beberapa pengiriman
            -- (kirim bertahap). Karena satu baris report harus tetap satu baris
            -- agar omzet tidak terhitung ganda, diambil pengiriman PERTAMA.
            -- Untuk order yang dikirim dari lebih dari satu lokasi, lokasi
            -- berikutnya tidak terwakili.
            LEFT JOIN LATERAL (
                SELECT sm.location_id, spt.warehouse_id
                  FROM sale_order_line_invoice_rel rel2
                  JOIN stock_move sm            ON sm.sale_line_id = rel2.order_line_id
                  LEFT JOIN stock_picking_type spt ON spt.id = sm.picking_type_id
                 WHERE rel2.invoice_line_id = aml.id
                   AND sm.state = 'done'
                 ORDER BY sm.date
                 LIMIT 1
            ) dlv ON TRUE
        """

    def _where_clause(self):
        return """
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND aml.display_type = 'product'
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            "CREATE OR REPLACE VIEW {table} AS (SELECT {select} {from_} {where})".format(
                table=self._table,
                select=self._select_clause(),
                from_=self._from_clause(),
                where=self._where_clause(),
            )
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _user_tz(self):
        try:
            return pytz.timezone(self.env.user.tz or "UTC")
        except pytz.UnknownTimeZoneError:
            _logger.warning("Timezone user tidak dikenal, memakai UTC.")
            return pytz.UTC

    def _local_range_to_utc(self, date_from, date_to):
        """Ubah dua tanggal lokal menjadi batas datetime UTC naive."""
        tz = self._user_tz()
        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)
        if not d_from or not d_to:
            raise UserError(_("The date range is not valid."))
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        start = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.UTC)
        end = tz.localize(datetime.combine(d_to, time.max)).astimezone(pytz.UTC)
        return (
            start.replace(tzinfo=None),
            end.replace(tzinfo=None),
            d_from,
            d_to,
        )

    def _resolve_granularity(self, granularity, d_from, d_to):
        if granularity in GRANULARITIES:
            return granularity
        span = (d_to - d_from).days + 1
        for limit, value in AUTO_GRANULARITY_STEPS:
            if span <= limit:
                return value
        return "year"

    def _base_domain_sql(self, start, end, company_ids, filters=None):
        """Bangun potongan WHERE beserta parameter bernama."""
        filters = filters or {}
        clauses = ["r.date_ts >= %(start)s", "r.date_ts <= %(end)s"]
        params = {"start": start, "end": end, "tz": str(self._user_tz())}

        allowed = set(self.env.companies.ids)
        selected = {int(c) for c in (company_ids or [])} & allowed or allowed
        clauses.append("r.company_id IN %(company_ids)s")
        params["company_ids"] = tuple(selected) or (0,)

        # Nama kolom diambil dari peta tetap, tidak pernah dari input client.
        for key, column in (
            ("warehouse_ids", "r.warehouse_id"),
            ("location_ids", "r.location_id"),
            ("team_ids", "r.team_id"),
            ("user_ids", "r.user_id"),
        ):
            values = filters.get(key)
            if not values:
                continue
            clauses.append("{col} IN %({key})s".format(col=column, key=key))
            params[key] = tuple(int(v) for v in values) or (0,)

        return " AND ".join(clauses), params

    @staticmethod
    def _local_expr(column="r.date_ts"):
        """Ekspresi konversi UTC -> waktu lokal user."""
        return "({col} AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)".format(col=column)

    @staticmethod
    def _growth(current, previous):
        """Persentase perubahan; None bila pembanding nol (hindari bagi nol)."""
        if not previous:
            return None
        return (current - previous) / abs(previous) * 100.0

    def _fetch_totals(self, where, params):
        self.env.cr.execute(
            """
            SELECT COALESCE(SUM(r.price_subtotal), 0.0)  AS amount,
                   COUNT(DISTINCT r.move_id)             AS orders,
                   COUNT(DISTINCT r.partner_id)          AS customers,
                   COALESCE(SUM(r.quantity), 0.0)        AS quantity,
                   COALESCE(SUM(r.price_tax), 0.0)       AS tax
              FROM {table} r
             WHERE {where}
            """.format(table=self._table, where=where),
            params,
        )
        row = self.env.cr.dictfetchone() or {}
        return {
            "tax": row.get("tax") or 0.0,
            "amount": row.get("amount") or 0.0,
            "orders": row.get("orders") or 0,
            "customers": row.get("customers") or 0,
            "quantity": row.get("quantity") or 0.0,
        }

    # ------------------------------------------------------------------
    # API untuk dashboard
    # ------------------------------------------------------------------

    @api.model
    def get_filter_options(self):
        """Daftar company, warehouse, dan location yang boleh dilihat user aktif."""
        companies = self.env.companies
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "in", companies.ids + [False])]
        )
        # Hanya lokasi internal: lokasi pemasok/pelanggan/inventory-loss bukan
        # tempat jualan dan hanya akan mengotori daftar filter.
        locations = self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", companies.ids + [False]),
            ]
        )
        currency = self.env.company.currency_id
        return {
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            "warehouses": [{"id": w.id, "name": w.display_name} for w in warehouses],
            "locations": [{"id": l.id, "name": l.display_name} for l in locations],
            "multi_company": len(companies) > 1,
            "tz": str(self._user_tz()),
            # BCP-47 untuk Intl.NumberFormat di sisi client (id_ID -> id-ID).
            "lang": (self.env.user.lang or "en_US").replace("_", "-"),
            "currency": {
                "symbol": currency.symbol or "",
                "position": currency.position or "before",
                "decimals": currency.decimal_places,
            },
        }

    @api.model
    def get_dashboard_data(
        self,
        date_from,
        date_to,
        granularity="auto",
        company_ids=None,
        warehouse_ids=None,
        location_ids=None,
        team_ids=None,
        user_ids=None,
        limit=10,
    ):
        """Kembalikan seluruh data yang dibutuhkan dashboard dalam satu panggilan."""
        self.check_access("read")

        start, end, d_from, d_to = self._local_range_to_utc(date_from, date_to)
        granularity = self._resolve_granularity(granularity, d_from, d_to)
        limit = max(3, min(int(limit or 10), 50))

        filters = {
            "warehouse_ids": warehouse_ids,
            "location_ids": location_ids,
            "team_ids": team_ids,
            "user_ids": user_ids,
        }
        where, params = self._base_domain_sql(start, end, company_ids, filters)

        # Periode pembanding: panjang sama, berakhir tepat sebelum date_from.
        span = end - start
        prev_end = start - timedelta(microseconds=1)
        prev_start = prev_end - span
        prev_where, prev_params = self._base_domain_sql(
            prev_start, prev_end, company_ids, filters
        )

        totals = self._fetch_totals(where, params)
        previous = self._fetch_totals(prev_where, prev_params)

        data = {
            "granularity": granularity,
            "tz": params["tz"],
            "date_from": fields.Date.to_string(d_from),
            "date_to": fields.Date.to_string(d_to),
            "kpi": self._build_kpi(totals, previous),
            "heatmap": self._fetch_heatmap(where, params),
            "hourly": self._fetch_hourly(where, params),
            "trend": self._fetch_trend(where, params, granularity),
            "top_products": self._fetch_top_products(where, params, limit),
            "top_warehouses": self._fetch_top_warehouses(where, params, limit),
            "top_locations": self._fetch_top_locations(where, params, limit),
            "top_partners": self._fetch_top_partners(where, params, limit),
            "tax_breakdown": self._fetch_tax_breakdown(where, params),
        }
        data["has_data"] = bool(totals["orders"])
        data["kpi"]["peak_hour"] = self._peak_hour(data["hourly"])
        return data

    def _build_kpi(self, totals, previous):
        avg_now = totals["amount"] / totals["orders"] if totals["orders"] else 0.0
        avg_prev = previous["amount"] / previous["orders"] if previous["orders"] else 0.0
        pairs = {
            "amount": (totals["amount"], previous["amount"]),
            "orders": (totals["orders"], previous["orders"]),
            "avg_order": (avg_now, avg_prev),
            "customers": (totals["customers"], previous["customers"]),
            "quantity": (totals["quantity"], previous["quantity"]),
            "tax": (totals["tax"], previous["tax"]),
        }
        return {
            key: {
                "value": cur,
                "previous": prev,
                "growth": self._growth(cur, prev),
            }
            for key, (cur, prev) in pairs.items()
        }

    @staticmethod
    def _peak_hour(hourly):
        best = max(hourly, key=lambda h: h["amount"], default=None)
        if not best or not best["amount"]:
            return {"hour": None, "label": "—", "amount": 0.0, "orders": 0}
        return {
            "hour": best["hour"],
            "label": "%02d:00–%02d:00" % (best["hour"], (best["hour"] + 1) % 24),
            "amount": best["amount"],
            "orders": best["orders"],
        }

    def _fetch_heatmap(self, where, params):
        local = self._local_expr()
        self.env.cr.execute(
            """
            SELECT EXTRACT(ISODOW FROM {local})::int  AS dow,
                   EXTRACT(HOUR  FROM {local})::int   AS hour,
                   COUNT(DISTINCT r.move_id)          AS orders,
                   COALESCE(SUM(r.price_subtotal), 0.0) AS amount
              FROM {table} r
             WHERE {where}
             GROUP BY 1, 2
            """.format(local=local, table=self._table, where=where),
            params,
        )
        found = {(r["dow"], r["hour"]): r for r in self.env.cr.dictfetchall()}
        # Grid penuh 7 x 24 supaya sel kosong tetap tergambar sebagai nol.
        return [
            {
                "dow": dow,
                "hour": hour,
                "orders": found.get((dow, hour), {}).get("orders", 0),
                "amount": found.get((dow, hour), {}).get("amount", 0.0),
            }
            for dow in range(1, 8)
            for hour in range(24)
        ]

    def _fetch_hourly(self, where, params):
        local = self._local_expr()
        self.env.cr.execute(
            """
            SELECT EXTRACT(HOUR FROM {local})::int    AS hour,
                   COUNT(DISTINCT r.move_id)          AS orders,
                   COALESCE(SUM(r.price_subtotal), 0.0) AS amount
              FROM {table} r
             WHERE {where}
             GROUP BY 1
            """.format(local=local, table=self._table, where=where),
            params,
        )
        found = {r["hour"]: r for r in self.env.cr.dictfetchall()}
        return [
            {
                "hour": h,
                "orders": found.get(h, {}).get("orders", 0),
                "amount": found.get(h, {}).get("amount", 0.0),
            }
            for h in range(24)
        ]

    def _fetch_trend(self, where, params, granularity):
        local = self._local_expr()
        query_params = dict(params, granularity=granularity)
        self.env.cr.execute(
            """
            SELECT DATE_TRUNC(%(granularity)s, {local})   AS bucket,
                   COUNT(DISTINCT r.move_id)              AS orders,
                   COALESCE(SUM(r.price_subtotal), 0.0)   AS amount
              FROM {table} r
             WHERE {where}
             GROUP BY 1
             ORDER BY 1
            """.format(local=local, table=self._table, where=where),
            query_params,
        )
        rows = self.env.cr.dictfetchall()
        return [
            {
                "key": r["bucket"].isoformat(),
                "label": self._trend_label(r["bucket"], granularity),
                "orders": r["orders"],
                "amount": r["amount"] or 0.0,
            }
            for r in rows
        ]

    def _trend_label(self, bucket, granularity):
        """Label sumbu X yang ringkas dan mengikuti bahasa user."""
        formats = {
            "hour": "d MMM HH:mm",
            "day": "d MMM",
            "week": "'W'w, MMM y",
            "month": "MMM y",
            "year": "y",
        }
        try:
            from babel.dates import format_datetime

            lang = (self.env.context.get("lang") or self.env.user.lang or "en_US")
            return format_datetime(
                bucket, format=formats[granularity], locale=lang.replace("-", "_")
            )
        except Exception:  # pragma: no cover - fallback bila locale tidak ada
            return bucket.strftime("%Y-%m-%d %H:%M")

    def _fetch_grouped(self, where, params, column, limit):
        query_params = dict(params, limit=limit)
        self.env.cr.execute(
            """
            SELECT {column}                             AS group_id,
                   COUNT(DISTINCT r.move_id)            AS orders,
                   COALESCE(SUM(r.quantity), 0.0)       AS quantity,
                   COALESCE(SUM(r.price_subtotal), 0.0) AS amount
              FROM {table} r
             WHERE {where}
             GROUP BY 1
             ORDER BY amount DESC NULLS LAST
             LIMIT %(limit)s
            """.format(column=column, table=self._table, where=where),
            query_params,
        )
        return self.env.cr.dictfetchall()

    def _label_rows(self, rows, model, fallback):
        """Lampirkan display_name lewat ORM supaya hak akses & terjemahan ikut."""
        ids = [r["group_id"] for r in rows if r["group_id"]]
        names = {}
        if ids:
            records = self.env[model].browse(ids).exists()
            names = {rec.id: rec.display_name for rec in records}
        return [
            {
                "id": r["group_id"] or 0,
                "name": names.get(r["group_id"], fallback),
                "orders": r["orders"],
                "quantity": r["quantity"] or 0.0,
                "amount": r["amount"] or 0.0,
            }
            for r in rows
        ]

    def _fetch_tax_breakdown(self, where, params):
        """Total pajak per jenis pajak (PNBP, PBJT, PPN, dst).

        Diambil dari baris pajak invoice (`tax_line_id`). Satu invoice bisa
        mencakup beberapa warehouse/lokasi, jadi pajaknya dialokasikan
        proporsional terhadap porsi subtotal baris yang lolos filter, supaya
        totalnya konsisten dengan KPI Sales Tax.
        """
        self.env.cr.execute(
            """
            WITH f AS (
                SELECT r.move_id, SUM(r.price_subtotal) AS amt
                  FROM {table} r
                 WHERE {where}
                 GROUP BY r.move_id
            ),
            t AS (
                SELECT r.move_id, SUM(r.price_subtotal) AS amt
                  FROM {table} r
                 WHERE r.move_id IN (SELECT move_id FROM f)
                 GROUP BY r.move_id
            )
            SELECT tl.tax_line_id                         AS group_id,
                   COUNT(DISTINCT tl.move_id)             AS orders,
                   SUM(-tl.balance * CASE WHEN COALESCE(t.amt, 0) = 0
                                          THEN 1.0 ELSE f.amt / t.amt END) AS amount
              FROM account_move_line tl
              JOIN f ON f.move_id = tl.move_id
              JOIN t ON t.move_id = tl.move_id
             WHERE tl.tax_line_id IS NOT NULL
             GROUP BY 1
             ORDER BY amount DESC NULLS LAST
            """.format(table=self._table, where=where),
            params,
        )
        rows = [dict(r, quantity=0.0) for r in self.env.cr.dictfetchall()]
        return self._label_rows(rows, "account.tax", _("No Tax"))

    def _fetch_top_products(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.product_tmpl_id", limit)
        return self._label_rows(rows, "product.template", _("No Product"))

    def _fetch_top_warehouses(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.warehouse_id", limit)
        # "No Warehouse" muncul untuk baris tanpa pengiriman ber-status done:
        # produk jasa, invoice manual tanpa sale order, atau barang yang belum
        # dikirim saat invoice sudah di-posting.
        return self._label_rows(rows, "stock.warehouse", _("No Warehouse"))

    def _fetch_top_locations(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.location_id", limit)
        return self._label_rows(rows, "stock.location", _("No Location"))

    def _fetch_top_partners(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.partner_id", limit)
        return self._label_rows(rows, "res.partner", _("No Customer"))
