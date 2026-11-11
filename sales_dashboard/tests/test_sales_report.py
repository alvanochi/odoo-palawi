# -*- coding: utf-8 -*-
"""Test untuk SQL view dan agregasi dashboard FOOM."""

from datetime import date, datetime, timedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestFoomSalesReport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["foom.sales.report"]
        cls.today = date.today()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_invoice(self, move_type="out_invoice", post=True, amounts=None):
        invoice = self.init_invoice(
            move_type,
            partner=self.partner_a,
            invoice_date=self.today,
            amounts=amounts or [1000.0],
            taxes=[],
        )
        if post:
            invoice.action_post()
        return invoice

    def _set_create_date(self, invoice, value):
        """Paksa create_date invoice; view memakainya sebagai fallback waktu."""
        self.env.cr.execute(
            "UPDATE account_move SET create_date = %s WHERE id = %s",
            (value, invoice.id),
        )
        self.env.invalidate_all()

    def _lines_for(self, invoice):
        return self.report.search([("move_id", "=", invoice.id)])

    # ------------------------------------------------------------------
    # Isi SQL view
    # ------------------------------------------------------------------

    def test_view_excludes_draft(self):
        """Invoice draft tidak boleh ikut terhitung sebagai penjualan."""
        draft = self._make_invoice(post=False)
        self.assertFalse(
            self._lines_for(draft),
            "Invoice draft seharusnya tidak muncul di foom.sales.report",
        )

        draft.action_post()
        self.assertTrue(
            self._lines_for(draft),
            "Invoice yang sudah posted seharusnya muncul di report",
        )

    def test_refund_sign_negative(self):
        """Credit note mengurangi omzet, bukan menambah."""
        refund = self._make_invoice(move_type="out_refund")
        lines = self._lines_for(refund)

        self.assertTrue(lines)
        self.assertLess(
            sum(lines.mapped("price_subtotal")), 0.0,
            "Omzet credit note harus bernilai negatif",
        )
        self.assertLess(
            sum(lines.mapped("quantity")), 0.0,
            "Qty credit note harus bernilai negatif",
        )

    def test_invoice_amount_positive(self):
        """Invoice biasa menghasilkan omzet positif senilai subtotal."""
        invoice = self._make_invoice(amounts=[1500.0])
        lines = self._lines_for(invoice)
        self.assertAlmostEqual(sum(lines.mapped("price_subtotal")), 1500.0, places=2)

    def test_order_count_distinct(self):
        """Invoice dengan tiga baris tetap dihitung sebagai satu order."""
        invoice = self._make_invoice(amounts=[100.0, 200.0, 300.0])
        self.assertEqual(len(self._lines_for(invoice)), 3, "Harus ada 3 baris produk")

        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )
        self.assertEqual(
            data["kpi"]["orders"]["value"], 1,
            "Tiga baris pada satu invoice harus dihitung sebagai satu order",
        )
        self.assertAlmostEqual(data["kpi"]["amount"]["value"], 600.0, places=2)

    # ------------------------------------------------------------------
    # Sales tax
    # ------------------------------------------------------------------

    def _make_taxed_invoice(self, move_type="out_invoice", amount=1000.0):
        invoice = self.init_invoice(
            move_type,
            partner=self.partner_a,
            invoice_date=self.today,
            amounts=[amount],
            taxes=self.tax_sale_a,
        )
        invoice.action_post()
        return invoice

    def _today_data(self):
        return self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )

    def test_tax_amount_in_view(self):
        """price_tax = pajak baris, price_total = subtotal + pajak."""
        invoice = self._make_taxed_invoice(amount=1000.0)
        lines = self._lines_for(invoice)
        expected_tax = invoice.amount_tax
        self.assertAlmostEqual(sum(lines.mapped("price_tax")), expected_tax, places=2)
        self.assertAlmostEqual(
            sum(lines.mapped("price_total")), 1000.0 + expected_tax, places=2
        )

    def test_tax_zero_without_tax(self):
        """Invoice tanpa pajak menghasilkan price_tax nol."""
        invoice = self._make_invoice(amounts=[500.0])
        self.assertAlmostEqual(sum(self._lines_for(invoice).mapped("price_tax")), 0.0)

    def test_refund_tax_negative(self):
        """Pajak credit note bernilai negatif."""
        refund = self._make_taxed_invoice(move_type="out_refund")
        self.assertLess(sum(self._lines_for(refund).mapped("price_tax")), 0.0)

    def test_kpi_tax(self):
        """KPI Sales Tax sama dengan total pajak invoice."""
        invoice = self._make_taxed_invoice()
        data = self._today_data()
        self.assertAlmostEqual(
            data["kpi"]["tax"]["value"], invoice.amount_tax, places=2
        )

    def test_tax_breakdown_matches_total(self):
        """Breakdown per jenis pajak berjumlah sama dengan KPI Sales Tax."""
        invoice = self._make_taxed_invoice()
        data = self._today_data()
        breakdown = data["tax_breakdown"]
        self.assertTrue(breakdown)
        self.assertIn(self.tax_sale_a.id, [r["id"] for r in breakdown])
        self.assertAlmostEqual(
            sum(r["amount"] for r in breakdown), invoice.amount_tax, places=2
        )
        self.assertAlmostEqual(
            sum(r["amount"] for r in breakdown), data["kpi"]["tax"]["value"], places=2
        )

    # ------------------------------------------------------------------
    # Timezone
    # ------------------------------------------------------------------

    def test_timezone_hour_shift(self):
        """Jam agregasi mengikuti timezone user, bukan UTC."""
        invoice = self._make_invoice()
        # 02:00 UTC pada hari ini = 09:00 di Asia/Jakarta (UTC+7).
        utc_dt = datetime.combine(self.today, datetime.min.time()) + timedelta(hours=2)
        self._set_create_date(invoice, utc_dt)

        self.env.user.tz = "Asia/Jakarta"
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )
        busiest = max(data["hourly"], key=lambda h: h["orders"])
        self.assertEqual(
            busiest["hour"], 9,
            "Transaksi 02:00 UTC harus tampil pada jam 09:00 untuk user Asia/Jakarta",
        )

    # ------------------------------------------------------------------
    # Perhitungan dashboard
    # ------------------------------------------------------------------

    def test_growth_zero_previous(self):
        """Periode pembanding kosong menghasilkan None, bukan pembagian nol."""
        self._make_invoice()
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )
        self.assertIsNone(
            data["kpi"]["amount"]["growth"],
            "Growth harus None ketika periode sebelumnya tidak punya penjualan",
        )

    def test_growth_computed(self):
        """Growth dihitung relatif terhadap periode sebelumnya yang sama panjang."""
        report = self.report
        self.assertAlmostEqual(report._growth(150.0, 100.0), 50.0, places=4)
        self.assertAlmostEqual(report._growth(50.0, 100.0), -50.0, places=4)
        self.assertIsNone(report._growth(50.0, 0.0))

    def test_granularity_auto(self):
        """Granularitas otomatis mengikuti panjang rentang."""
        report = self.report
        cases = [
            (date(2026, 1, 1), date(2026, 1, 1), "hour"),
            (date(2026, 1, 1), date(2026, 1, 31), "day"),
            (date(2026, 1, 1), date(2026, 6, 30), "week"),
            (date(2024, 1, 1), date(2026, 1, 1), "month"),
            (date(2016, 1, 1), date(2026, 1, 1), "year"),
        ]
        for d_from, d_to, expected in cases:
            with self.subTest(d_from=d_from, d_to=d_to):
                self.assertEqual(
                    report._resolve_granularity("auto", d_from, d_to), expected
                )

    def test_granularity_explicit_is_whitelisted(self):
        """Nilai granularitas dari client tidak boleh lolos apa adanya ke SQL."""
        report = self.report
        d_from, d_to = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual(report._resolve_granularity("month", d_from, d_to), "month")
        # Nilai berbahaya jatuh kembali ke pemilihan otomatis.
        self.assertEqual(
            report._resolve_granularity("day'); DROP TABLE account_move;--", d_from, d_to),
            "day",
        )

    def test_heatmap_grid_is_complete(self):
        """Heatmap selalu mengembalikan 7 x 24 sel walau sebagian kosong."""
        self._make_invoice()
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )
        self.assertEqual(len(data["heatmap"]), 7 * 24)
        self.assertEqual(len(data["hourly"]), 24)

    def test_empty_period_has_no_data_flag(self):
        """Periode tanpa transaksi ditandai has_data=False untuk empty state."""
        far_past = date(2001, 1, 1)
        data = self.report.get_dashboard_data(
            date_from=far_past.isoformat(),
            date_to=far_past.isoformat(),
        )
        self.assertFalse(data["has_data"])
        self.assertEqual(data["kpi"]["orders"]["value"], 0)

    def test_filter_options_shape(self):
        """get_filter_options memuat kunci yang dibutuhkan komponen OWL."""
        options = self.report.get_filter_options()
        for key in (
            "companies", "warehouses", "locations",
            "multi_company", "tz", "lang", "currency",
        ):
            self.assertIn(key, options)
        for key in ("symbol", "position", "decimals"):
            self.assertIn(key, options["currency"])

    def test_filter_options_locations_are_internal(self):
        """Daftar lokasi filter hanya berisi lokasi internal."""
        options = self.report.get_filter_options()
        ids = [loc["id"] for loc in options["locations"]]
        usages = set(self.env["stock.location"].browse(ids).mapped("usage"))
        self.assertTrue(usages.issubset({"internal"}), usages)

    def test_dashboard_has_warehouse_and_location_rankings(self):
        """Ranking outlet sekarang per warehouse dan per location."""
        self._make_invoice()
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )
        self.assertIn("top_warehouses", data)
        self.assertIn("top_locations", data)
        self.assertNotIn("top_teams", data)

    def test_warehouse_filter_narrows_result(self):
        """Memfilter warehouse yang tidak dipakai menghasilkan nol order."""
        self._make_invoice()
        unused = self.env["stock.warehouse"].search([], limit=1)
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
            warehouse_ids=[unused.id if unused else 0],
        )
        # Invoice pada test ini tidak punya pengiriman done, jadi warehouse_id
        # NULL dan tidak pernah cocok dengan filter warehouse mana pun.
        self.assertEqual(data["kpi"]["orders"]["value"], 0)

    def test_filter_key_is_not_taken_from_client(self):
        """Nama kolom filter berasal dari peta tetap, bukan input client."""
        where, params = self.report._base_domain_sql(
            datetime(2026, 1, 1), datetime(2026, 1, 2),
            None, {"warehouse_ids": [1], "bogus_ids": [2]},
        )
        self.assertIn("r.warehouse_id IN", where)
        self.assertNotIn("bogus", where)
