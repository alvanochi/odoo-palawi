# -*- coding: utf-8 -*-
"""Test untuk SQL view dan agregasi dashboard penjualan (sumber: POS)."""

from datetime import date, datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSalesReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["sales.report"]
        cls.today = date.today()
        cls.company = cls.env.company
        cls.tax = cls.env["account.tax"].create({
            "name": "Test Tax 10%",
            "amount_type": "percent",
            "amount": 10.0,
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Test Product",
            "type": "consu",
            "available_in_pos": True,
            "list_price": 100.0,
        })
        cls.config = cls.env["pos.config"].create({
            "name": "Test Outlet",
            "company_id": cls.company.id,
        })
        cls.config.open_ui()
        cls.session = cls.config.current_session_id

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_order(self, base=100.0, qty=1.0, taxed=True, state="paid", at=None):
        tax = self.tax if taxed else self.env["account.tax"]
        subtotal = base * qty
        tax_amount = round(subtotal * 0.10, 2) if taxed else 0.0
        default_at = datetime.combine(self.today, datetime.min.time()) + timedelta(hours=5)
        order = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.company.id,
            "pricelist_id": self.config.pricelist_id.id,
            "date_order": at or default_at,
            "amount_tax": tax_amount,
            "amount_total": subtotal + tax_amount,
            "amount_paid": 0.0,
            "amount_return": 0.0,
            "lines": [(0, 0, {
                "product_id": self.product.id,
                "qty": qty,
                "price_unit": base,
                "price_subtotal": subtotal,
                "price_subtotal_incl": subtotal + tax_amount,
                "tax_ids": [(6, 0, tax.ids)],
                "full_product_name": self.product.name,
            })],
        })
        order.write({"state": state})
        return order

    def _lines_for(self, order):
        return self.report.search([("order_id", "=", order.id)])

    def _today_data(self):
        return self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )

    # ------------------------------------------------------------------
    # Isi SQL view
    # ------------------------------------------------------------------

    def test_view_excludes_draft(self):
        """Order draft tidak ikut terhitung; setelah paid baru muncul."""
        order = self._make_order(state="draft")
        self.assertFalse(self._lines_for(order))
        order.write({"state": "paid"})
        self.assertTrue(self._lines_for(order))

    def test_outlet_is_pos_config(self):
        """Outlet diambil dari pos.config order."""
        order = self._make_order()
        self.assertEqual(self._lines_for(order).config_id, self.config)

    def test_amount_and_tax(self):
        """Revenue tanpa pajak, price_tax = selisih incl - excl."""
        order = self._make_order(base=100.0, qty=2.0)
        lines = self._lines_for(order)
        self.assertAlmostEqual(sum(lines.mapped("price_subtotal")), 200.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped("price_tax")), 20.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped("price_total")), 220.0, places=2)

    def test_tax_zero_without_tax(self):
        order = self._make_order(taxed=False)
        self.assertAlmostEqual(sum(self._lines_for(order).mapped("price_tax")), 0.0)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def test_kpi_tax_and_orders(self):
        self._make_order(base=100.0, qty=1.0)
        self._make_order(base=50.0, qty=2.0)
        data = self._today_data()
        self.assertEqual(data["kpi"]["orders"]["value"], 2)
        self.assertAlmostEqual(data["kpi"]["amount"]["value"], 200.0, places=2)
        self.assertAlmostEqual(data["kpi"]["tax"]["value"], 20.0, places=2)

    def test_tax_breakdown_matches_total(self):
        self._make_order(base=100.0, qty=1.0)
        data = self._today_data()
        breakdown = data["tax_breakdown"]
        self.assertIn(self.tax.id, [r["id"] for r in breakdown])
        self.assertAlmostEqual(
            sum(r["amount"] for r in breakdown), data["kpi"]["tax"]["value"], places=2
        )

    def test_outlet_filter(self):
        self._make_order()
        other = self.env["pos.config"].create({
            "name": "Other Outlet", "company_id": self.company.id,
        })
        data = self.report.get_dashboard_data(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
            config_ids=[other.id],
        )
        self.assertEqual(data["kpi"]["orders"]["value"], 0)

    def test_no_warehouse_or_location_ranking(self):
        data = self._today_data()
        self.assertNotIn("top_warehouses", data)
        self.assertNotIn("top_locations", data)

    def test_timezone_hour_shift(self):
        """Jam agregasi mengikuti timezone user, bukan UTC."""
        utc_dt = datetime.combine(self.today, datetime.min.time()) + timedelta(hours=2)
        self._make_order(at=utc_dt)
        self.env.user.tz = "Asia/Jakarta"
        data = self._today_data()
        busiest = max(data["hourly"], key=lambda h: h["orders"])
        self.assertEqual(busiest["hour"], 9)

    def test_growth_zero_previous(self):
        self._make_order()
        self.assertIsNone(self._today_data()["kpi"]["amount"]["growth"])

    def test_growth_computed(self):
        self.assertAlmostEqual(self.report._growth(150.0, 100.0), 50.0, places=4)
        self.assertIsNone(self.report._growth(50.0, 0.0))

    def test_granularity_explicit_is_whitelisted(self):
        d_from, d_to = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual(self.report._resolve_granularity("month", d_from, d_to), "month")
        self.assertEqual(
            self.report._resolve_granularity("day'); DROP TABLE pos_order;--", d_from, d_to),
            "day",
        )

    def test_heatmap_grid_is_complete(self):
        data = self._today_data()
        self.assertEqual(len(data["heatmap"]), 7 * 24)
        self.assertEqual(len(data["hourly"]), 24)

    def test_empty_period_has_no_data_flag(self):
        far = date(2001, 1, 1).isoformat()
        data = self.report.get_dashboard_data(date_from=far, date_to=far)
        self.assertFalse(data["has_data"])

    def test_filter_options_shape(self):
        options = self.report.get_filter_options()
        for key in ("companies", "outlets", "multi_company", "tz", "lang", "currency"):
            self.assertIn(key, options)

    def test_filter_key_is_not_taken_from_client(self):
        where, params = self.report._base_domain_sql(
            datetime(2026, 1, 1), datetime(2026, 1, 2),
            None, {"config_ids": [1], "bogus_ids": [2]},
        )
        self.assertIn("r.config_id IN", where)
        self.assertNotIn("bogus", where)
