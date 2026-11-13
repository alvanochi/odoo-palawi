# -*- coding: utf-8 -*-
"""Model laporan penjualan POS.

Model ini adalah SQL view read-only di atas baris order POS (`pos.order.line`)
yang sudah dibayar. Semua method agregasi untuk dashboard OWL ada di sini supaya
perhitungan tetap terjadi di sisi database, bukan dengan mengiterasi record di
Python.
"""

import logging
from collections import defaultdict
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

# Status order POS yang dihitung sebagai penjualan.
SALE_STATES = ("paid", "done", "invoiced")


class SalesReport(models.Model):
    """Satu baris = satu baris produk pada order POS yang sudah dibayar."""

    _name = "sales.report"
    _description = "Sales Report"
    _auto = False
    _rec_name = "date_ts"
    _order = "date_ts desc"

    date_ts = fields.Datetime(
        string="Transaction Time",
        readonly=True,
        help="Order date of the POS order.",
    )
    order_id = fields.Many2one("pos.order", string="POS Order", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product Template", readonly=True
    )
    categ_id = fields.Many2one("product.category", string="Product Category", readonly=True)
    user_id = fields.Many2one("res.users", string="Cashier", readonly=True)
    config_id = fields.Many2one(
        "pos.config",
        string="Outlet",
        readonly=True,
        help="Point of Sale (outlet) where the order was made.",
    )
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    quantity = fields.Float(string="Qty", readonly=True)
    price_subtotal = fields.Float(
        string="Revenue",
        readonly=True,
        help="Untaxed amount.",
    )
    price_tax = fields.Float(
        string="Sales Tax",
        readonly=True,
        help="Tax amount of the line (negative for refunds).",
    )
    price_total = fields.Float(
        string="Revenue incl. Tax",
        readonly=True,
        help="Revenue plus tax.",
    )
    tax_key = fields.Char(
        string="Tax Set",
        readonly=True,
        help="Comma separated ids of the taxes applied on the line.",
    )
    order_count = fields.Integer(string="Lines", readonly=True)

    # ------------------------------------------------------------------
    # Definisi SQL view
    # ------------------------------------------------------------------

    def _select_clause(self):
        return """
            pol.id                                      AS id,
            po.id                                       AS order_id,
            po.date_order                               AS date_ts,
            po.partner_id                               AS partner_id,
            po.user_id                                  AS user_id,
            ps.config_id                                AS config_id,
            po.company_id                               AS company_id,
            pol.product_id                              AS product_id,
            pp.product_tmpl_id                          AS product_tmpl_id,
            pt.categ_id                                 AS categ_id,
            pol.qty                                     AS quantity,
            pol.price_subtotal                          AS price_subtotal,
            pol.price_subtotal_incl - pol.price_subtotal AS price_tax,
            pol.price_subtotal_incl                     AS price_total,
            (SELECT string_agg(rel.account_tax_id::text, ','
                               ORDER BY tx.sequence, tx.id)
               FROM account_tax_pos_order_line_rel rel
               JOIN account_tax tx ON tx.id = rel.account_tax_id
              WHERE rel.pos_order_line_id = pol.id)     AS tax_key,
            1                                           AS order_count
        """

    def _from_clause(self):
        return """
            FROM pos_order_line pol
            JOIN pos_order po              ON po.id = pol.order_id
            LEFT JOIN pos_session ps       ON ps.id = po.session_id
            LEFT JOIN product_product pp   ON pp.id = pol.product_id
            LEFT JOIN product_template pt  ON pt.id = pp.product_tmpl_id
        """

    def _where_clause(self):
        return """
            WHERE po.state IN {states}
        """.format(states=str(SALE_STATES))

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
            ("config_ids", "r.config_id"),
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
                   COUNT(DISTINCT r.order_id)             AS orders,
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
        """Daftar company dan outlet (pos.config) yang boleh dilihat user aktif."""
        companies = self.env.companies
        outlets = self.env["pos.config"].search(
            [("company_id", "in", companies.ids)]
        )
        currency = self.env.company.currency_id
        return {
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            "outlets": [{"id": o.id, "name": o.display_name} for o in outlets],
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
        config_ids=None,
        user_ids=None,
        limit=10,
    ):
        """Kembalikan seluruh data yang dibutuhkan dashboard dalam satu panggilan."""
        self.check_access("read")

        start, end, d_from, d_to = self._local_range_to_utc(date_from, date_to)
        granularity = self._resolve_granularity(granularity, d_from, d_to)
        limit = max(3, min(int(limit or 10), 50))

        filters = {
            "config_ids": config_ids,
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
                   COUNT(DISTINCT r.order_id)          AS orders,
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
                   COUNT(DISTINCT r.order_id)          AS orders,
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
                   COUNT(DISTINCT r.order_id)              AS orders,
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
                   COUNT(DISTINCT r.order_id)            AS orders,
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

        Baris dikelompokkan per kombinasi pajak (`tax_key`) di SQL, lalu tiap
        kombinasi dihitung ulang dengan `compute_all` supaya pajak majemuk
        (include_base_amount, fixed, dll) dipecah per jenis sesuai aturan Odoo.
        Pajak yang sudah masuk di harga (price include) tidak jadi masalah
        karena dasar yang dipakai adalah subtotal tanpa pajak.
        """
        self.env.cr.execute(
            """
            SELECT r.tax_key                                AS tax_key,
                   COALESCE(SUM(r.price_subtotal), 0.0)     AS base,
                   COALESCE(SUM(r.quantity), 0.0)           AS quantity
              FROM {table} r
             WHERE {where} AND r.tax_key IS NOT NULL
             GROUP BY r.tax_key
            """.format(table=self._table, where=where),
            params,
        )
        groups = self.env.cr.dictfetchall()

        Tax = self.env["account.tax"]
        currency = self.env.company.currency_id
        amounts = defaultdict(float)
        for grp in groups:
            ids = [int(i) for i in grp["tax_key"].split(",")]
            taxes = Tax.browse(ids).exists()
            if not taxes:
                continue
            qty = grp["quantity"] or 0.0
            base = grp["base"] or 0.0
            if not qty:
                qty, price_unit = 1.0, base
            else:
                price_unit = base / qty
            res = taxes.compute_all(
                price_unit,
                currency=currency,
                quantity=qty,
                handle_price_include=False,
            )
            for tax in res["taxes"]:
                amounts[tax["id"]] += tax["amount"]

        # Jumlah order per jenis pajak (satu order dihitung sekali per pajak).
        self.env.cr.execute(
            """
            SELECT tx::int                      AS tax_id,
                   COUNT(DISTINCT r.order_id)   AS orders
              FROM {table} r,
                   unnest(string_to_array(r.tax_key, ',')) AS tx
             WHERE {where} AND r.tax_key IS NOT NULL
             GROUP BY 1
            """.format(table=self._table, where=where),
            params,
        )
        orders = {r["tax_id"]: r["orders"] for r in self.env.cr.dictfetchall()}

        rows = [
            {
                "group_id": tax_id,
                "orders": orders.get(tax_id, 0),
                "quantity": 0.0,
                "amount": amount,
            }
            for tax_id, amount in sorted(
                amounts.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        return self._label_rows(rows, "account.tax", _("No Tax"))

    def _fetch_top_products(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.product_tmpl_id", limit)
        return self._label_rows(rows, "product.template", _("No Product"))

    def _fetch_top_partners(self, where, params, limit):
        rows = self._fetch_grouped(where, params, "r.partner_id", limit)
        return self._label_rows(rows, "res.partner", _("No Customer"))
