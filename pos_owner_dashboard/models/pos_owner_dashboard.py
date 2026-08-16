# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import datetime, timedelta
from calendar import monthrange
import json
import logging
import io
import base64
import pytz

_logger = logging.getLogger(__name__)


class PosOwnerDashboard(models.Model):
    _name = "pos.owner.dashboard"
    _description = "POS Owner Dashboard"
    _order = "create_date desc"

    name = fields.Char(string="Name", default="POS Owner Dashboard", required=True)
    
    # Filters
    date_from = fields.Date(
        string="Dari Tanggal",
        default=fields.Date.context_today,
        required=True,
    )
    date_to = fields.Date(
        string="Sampai Tanggal",
        default=fields.Date.context_today,
        required=True,
    )
    
    pos_config_id = fields.Many2one(
        "pos.config",
        string="Point of Sale",
        help="Filter berdasarkan POS tertentu (dari company aktif)",
    )
    # pos_session_id = fields.Many2one(
    #     "pos.session",
    #     string="Sesi / Shift",
    #     help="Opsi laporan berbasis shift untuk kebutuhan audit",
    #     domain="[('config_id', '=', pos_config_id)]" if 'pos_config_id' else "[]"
    # )
    
    @api.model
    def default_get(self, fields_list):
        """Override to set domain for pos_config_id based on active company."""
        res = super().default_get(fields_list)
        return res
    
    @api.onchange('pos_config_id')
    def _onchange_pos_config_id(self):
        """Set domain for pos_config_id based on active company."""
        return {
            'domain': {
                'pos_config_id': [('company_id', 'in', self.env.companies.ids)]
            }
        }

    # ==================== SALES SUMMARY ====================
    total_sales = fields.Monetary(
        string="Total Penjualan",
        compute="_compute_sales_metrics",
        currency_field="currency_id",
    )
    total_orders = fields.Integer(
        string="Total Order",
        compute="_compute_sales_metrics",
    )
    average_order_value = fields.Monetary(
        string="Rata-rata per Order",
        compute="_compute_sales_metrics",
        currency_field="currency_id",
    )
    total_tax = fields.Monetary(
        string="Total Pajak",
        compute="_compute_sales_metrics",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )

    # ==================== FINANCIAL METRICS ====================
    total_margin = fields.Monetary(
        string="Total Margin",
        compute="_compute_financial_metrics",
        currency_field="currency_id",
    )
    average_margin_percent = fields.Float(
        string="Rata-rata Margin (%)",
        compute="_compute_financial_metrics",
    )
    total_discount = fields.Monetary(
        string="Total Diskon",
        compute="_compute_financial_metrics",
        currency_field="currency_id",
    )

    # ==================== CUSTOMER METRICS ====================
    unique_customers = fields.Integer(
        string="Pelanggan Unik",
        compute="_compute_customer_metrics",
    )
    total_guests = fields.Integer(
        string="Total Tamu",
        compute="_compute_customer_metrics",
    )
    dine_in_count = fields.Integer(
        string="Order Dine-in",
        compute="_compute_customer_metrics",
    )
    takeaway_count = fields.Integer(
        string="Order Takeaway",
        compute="_compute_customer_metrics",
    )
    
    cancel_orders = fields.Integer(
    string="Total Cancel Order",
        compute="_compute_cancel_metrics",
    )

    cancel_amount = fields.Monetary(
        string="Total Cancel Amount",
        compute="_compute_cancel_metrics",
        currency_field="currency_id",
    )

    # ==================== HTML DASHBOARD ====================
    dashboard_html = fields.Html(
        string="Dashboard",
        compute="_compute_dashboard_html",
        sanitize=False,
    )
    
    # ==================== CHARTS DATA ====================
    top_products_html = fields.Html(
        string="Produk Terlaris",
        compute="_compute_top_products",
        sanitize=False,
    )
    
    hourly_orders_html = fields.Html(
        string="Order per Jam",
        compute="_compute_hourly_orders",
        sanitize=False,
    )
    
    payment_methods_html = fields.Html(
        string="Metode Pembayaran",
        compute="_compute_payment_methods",
        sanitize=False,
    )
    
    cashier_performance_html = fields.Html(
        string="Performa Kasir",
        compute="_compute_cashier_performance",
        sanitize=False,
    )
    
    # ==================== TRANSACTION LIST ====================
    transaction_list_html = fields.Html(
        string="Daftar Transaksi",
        compute="_compute_transaction_list",
        sanitize=False,
    )
    
    status_filter = fields.Selection(
        [
            ("all", "Semua Status"),
            ("paid", "Paid"),
            ("done", "Posted"),
        ],
        string="Filter Status",
        default="all",
    )
    
    net_sales = fields.Float(
    string="Net Sales",
    compute="_compute_financial_metrics",
    store=False,
    )

    discount_percent = fields.Float(
        string="Discount %",
        compute="_compute_financial_metrics",
        store=False,
    )

    cancel_rate = fields.Float(
        string="Cancel Rate",
        compute="_compute_financial_metrics",
        store=False,
    )

    average_guest_spend = fields.Float(
        string="Average Guest Spend",
        compute="_compute_financial_metrics",
        store=False,
    )

    real_margin = fields.Float(
        string="Real Margin",
        compute="_compute_financial_metrics",
        store=False,
    )

    # ==================== PAGE SIZE SELECTORS ====================
    page_size_products = fields.Selection(
        [("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"), ("0", "Semua")],
        string="Tampilkan", default="10",
    )
    page_size_transactions = fields.Selection(
        [("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"), ("0", "Semua")],
        string="Tampilkan", default="25",
    )
    page_size_bills = fields.Selection(
        [("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"), ("0", "Semua")],
        string="Tampilkan", default="25",
    )
    page_size_cash = fields.Selection(
        [("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"), ("0", "Semua")],
        string="Tampilkan", default="25",
    )

    # ==================== BILLS & CASH MOVEMENT ====================
    bills_html = fields.Html(
        string="Bills (POSKAS)",
        compute="_compute_bills",
        sanitize=False,
    )
    
    cash_movement_html = fields.Html(
        string="Cash In/Out",
        compute="_compute_cash_movement",
        sanitize=False,
    )

    def _format_datetime_local(self, dt):
        """Convert UTC datetime to Asia/Jakarta and format."""
        if not dt:
            return "-"
        tz = pytz.timezone('Asia/Jakarta')
        utc_dt = pytz.utc.localize(dt)
        local_dt = utc_dt.astimezone(tz)
        return local_dt.strftime("%d/%m/%Y %H:%M")

    def _get_datetime_range_utc(self):
        """Get proper datetime range in UTC based on date fields and Asia/Jakarta timezone."""
        date_from, date_to = self._get_date_range()
        tz = pytz.timezone('Asia/Jakarta')
        
        local_from = tz.localize(datetime.combine(date_from, datetime.min.time()))
        local_to = tz.localize(datetime.combine(date_to, datetime.max.time()))
        
        utc_from = local_from.astimezone(pytz.utc).replace(tzinfo=None)
        utc_to = local_to.astimezone(pytz.utc).replace(tzinfo=None)
        
        return utc_from, utc_to

    
    def _get_discount_summary(self):
        """Return summary by discount percent: {5: {'qty': 10, 'amount': 50000}}"""
        orders = self._get_orders()
        discount_data = {}

        for order in orders:
            for line in order.lines:
                if line.discount and line.discount > 0:
                    percent = int(line.discount) if float(line.discount).is_integer() else line.discount

                    if percent not in discount_data:
                        discount_data[percent] = {"qty": 0, "amount": 0}

                    # qty
                    discount_data[percent]["qty"] += line.qty

                    # amount (nilai diskon)
                    discount_amount = (line.price_unit * line.qty) * (line.discount / 100)
                    discount_data[percent]["amount"] += discount_amount

        return dict(sorted(discount_data.items(), key=lambda x: x[0]))

    def _get_date_range(self):
        """Get date range from date_from and date_to fields."""
        today = fields.Date.context_today(self)
        date_from = self.date_from or today
        date_to = self.date_to or today
        return date_from, date_to
    
    def _get_period_label(self):
        """Get human-readable period label from date range."""
        date_from, date_to = self._get_date_range()
        if date_from == date_to:
            return date_from.strftime("%d %b %Y")
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"

    def _get_orders_domain(self):
        """Build domain for pos.order search."""
        date_from, date_to = self._get_date_range()
        
        # Convert dates to proper UTC datetime bounds ensuring local Asia/Jakarta boundaries
        datetime_from, datetime_to = self._get_datetime_range_utc()
        
        # Filter by active company from user session
        domain = [
            ("date_order", ">=", datetime_from),
            ("date_order", "<=", datetime_to),
            ("state", "in", ["paid", "done", "invoiced"]),
            ("company_id", "in", self.env.companies.ids),
        ]
        
        if self.pos_config_id:
            domain.append(("config_id", "=", self.pos_config_id.id))
        
        # if self.pos_session_id:
        #     domain.append(("session_id", "=", self.pos_session_id.id))
            
        return domain

    def _get_orders(self):
        """Get filtered pos.order records."""
        domain = self._get_orders_domain()
        return self.env["pos.order"].search(domain)

    # ==================== COMPUTE METHODS ====================
    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_sales_metrics(self):
        for record in self:
            orders = record._get_orders()
            
            record.total_sales = sum(orders.mapped("amount_total"))
            record.total_orders = len(orders)
            record.average_order_value = (
                record.total_sales / record.total_orders if record.total_orders else 0
            )
            record.total_tax = sum(orders.mapped("amount_tax"))
            
            
            
    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_cancel_metrics(self):
        for record in self:
            datetime_from, datetime_to = record._get_datetime_range_utc()

            domain = [
                ("date_order", ">=", datetime_from),
                ("date_order", "<=", datetime_to),
                ("state", "=", "cancel"),
                ("company_id", "in", record.env.companies.ids),
            ]

            if record.pos_config_id:
                domain.append(("config_id", "=", record.pos_config_id.id))

            record.cancel_orders = record.env["pos.order"].search_count(domain)

            data = record.env["pos.order"].read_group(
                domain,
                ["amount_total:sum"],
                []
            )

            record.cancel_amount = (
                data[0]["amount_total"]
                if data and data[0]["amount_total"]
                else 0
            )

    @api.depends(
    "date_from",
    "date_to",
    "pos_config_id",
    )
    def _compute_financial_metrics(self):
        for record in self:
            orders = record._get_orders()

            # =========================
            # TOTAL MARGIN
            # =========================

            record.total_margin = sum(orders.mapped("margin"))

            margin_percents = [
                o.margin_percent
                for o in orders
                if o.margin_percent
            ]

            record.average_margin_percent = (
                sum(margin_percents) / len(margin_percents) * 100
                if margin_percents
                else 0
            )

            # =========================
            # TOTAL DISCOUNT
            # =========================

            total_discount = 0

            for order in orders:
                for line in order.lines:

                    product_name = (
                        line.product_id.name or ""
                    ).lower()

                    # Discount %
                    if line.discount > 0:
                        total_discount += (
                            (line.price_unit * line.qty)
                            * (line.discount / 100)
                        )

                    # Discount Product
                    if "discount" in product_name:
                        total_discount += abs(
                            line.price_subtotal_incl
                        )

            record.total_discount = total_discount

            # =========================
            # NET SALES
            # =========================

            record.net_sales = (
                record.total_sales
                - record.total_discount
                - record.cancel_amount
            )

            # =========================
            # DISCOUNT %
            # =========================

            record.discount_percent = (
                (
                    record.total_discount
                    / record.total_sales
                )
                * 100
                if record.total_sales
                else 0
            )

            # =========================
            # CANCEL RATE
            # =========================

            record.cancel_rate = (
                (
                    record.cancel_orders
                    / record.total_orders
                )
                * 100
                if record.total_orders
                else 0
            )

            # =========================
            # SPEND / GUEST
            # =========================

            record.average_guest_spend = (
                record.total_sales
                / record.total_guests
                if record.total_guests
                else 0
            )

            # =========================
            # REAL MARGIN
            # =========================

            record.real_margin = (
                record.total_margin
                - record.total_discount
            )
        
    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_customer_metrics(self):
        for record in self:
            orders = record._get_orders()

            customers = orders.mapped("partner_id").filtered(lambda p: p.id)
            record.unique_customers = len(customers)

            record.total_guests = sum(orders.mapped("customer_count"))

            domain = []

            if record.pos_config_id:
                domain.append(
                    ("config_id", "=", record.pos_config_id.id)
                )

            if record.date_from:
                domain.append(
                    ("create_date", ">=", record.date_from)
                )

            if record.date_to:
                domain.append(
                    ("create_date", "<=", record.date_to)
                )

            groups = self.env["poskas.bill"].read_group(
                domain,
                ["type_order"],
                ["type_order"],
            )

            result = {
                g["type_order"]: g["type_order_count"]
                for g in groups
            }

            record.dine_in_count = result.get("dine_in", 0)
            record.takeaway_count = result.get("take_away", 0)

    @api.depends("date_from", "date_to", "pos_config_id", "page_size_products")
    def _compute_top_products(self):
        # Keywords to exclude from top products
        exclude_keywords = ['testing', 'discount', 'diskon']
        
        for record in self:
            orders = record._get_orders()
            limit = int(record.page_size_products or '10')
            
            # Aggregate product sales
            product_sales = {}
            for order in orders:
                for line in order.lines:
                    product_name = line.product_id.name or ""
                    # Skip products containing excluded keywords
                    if any(kw in product_name.lower() for kw in exclude_keywords):
                        continue
                    
                    product_id = line.product_id.id
                    if product_id not in product_sales:
                        product_sales[product_id] = {
                            "name": product_name,
                            "qty": 0,
                            "total": 0,
                        }
                    product_sales[product_id]["qty"] += line.qty
                    product_sales[product_id]["total"] += line.price_subtotal_incl

            # Sort and get top N
            sorted_products = sorted(
                product_sales.values(),
                key=lambda x: x["qty"],
                reverse=True
            )
            if limit > 0:
                sorted_products = sorted_products[:limit]
            total_all = len(product_sales)

            record.top_products_html = record._render_top_products_html(sorted_products, total_all)

    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_hourly_orders(self):
        tz = pytz.timezone('Asia/Jakarta')
        for record in self:
            orders = record._get_orders()
            
            # Aggregate orders by hour
            hourly_data = {h: 0 for h in range(24)}
            for order in orders:
                if order.date_order:
                    utc_dt = pytz.utc.localize(order.date_order)
                    local_dt = utc_dt.astimezone(tz)
                    hour = local_dt.hour
                    hourly_data[hour] += 1

            record.hourly_orders_html = record._render_hourly_orders_html(hourly_data)

    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_payment_methods(self):
        for record in self:
            orders = record._get_orders()
            
            # Aggregate by payment method
            payment_data = {}
            for order in orders:
                for payment in order.payment_ids:
                    method_name = payment.payment_method_id.name
                    if method_name not in payment_data:
                        payment_data[method_name] = 0
                    payment_data[method_name] += payment.amount

            record.payment_methods_html = record._render_payment_methods_html(payment_data)

    @api.depends("date_from", "date_to", "pos_config_id")
    def _compute_cashier_performance(self):
        for record in self:
            orders = record._get_orders()
            
            # Aggregate by user/cashier
            cashier_data = {}
            for order in orders:
                user_name = order.user_id.name or "Unknown"
                if user_name not in cashier_data:
                    cashier_data[user_name] = {"orders": 0, "total": 0}
                cashier_data[user_name]["orders"] += 1
                cashier_data[user_name]["total"] += order.amount_total

            record.cashier_performance_html = record._render_cashier_performance_html(cashier_data)

    @api.depends(
    "date_from",
    "date_to",
    "pos_config_id",
    "cancel_orders",
    "cancel_amount",
    )
    def _compute_dashboard_html(self):
        for record in self:
            record._compute_sales_metrics()
            record._compute_cancel_metrics()
            record._compute_financial_metrics()
            record._compute_customer_metrics()
            record.dashboard_html = record._render_dashboard_html()

    # ==================== HTML RENDERING METHODS ====================
    def _format_currency(self, amount):
        """Format amount as currency string."""
        return "Rp {:,.0f}".format(amount).replace(",", ".")

    def _render_dashboard_html(self):
        """Render main dashboard HTML with summary cards - Mobile Responsive."""
        orders = self._get_orders()
        date_from, date_to = self._get_date_range()

        period_label = self._get_period_label()

       # ==================== DISCOUNT BREAKDOWN ====================
        discount_summary = {}
        product_discount_summary = {}
        transaction_discount_summary = {}
        for order in orders:
            for line in order.lines:
                product_name = (line.product_id.name or "")
                product_name_clean = product_name.strip().lower()

                # ================= SYSTEM DISCOUNT (%) =================
                if line.discount and line.discount > 0:
                    percent = int(line.discount) if float(line.discount).is_integer() else line.discount

                    if percent not in discount_summary:
                        discount_summary[percent] = {"qty": 0, "amount": 0}

                    discount_summary[percent]["qty"] += abs(line.qty)
                    discount_summary[percent]["amount"] += abs(
                        (line.price_unit * line.qty) * (line.discount / 100)
                    )

                # ================= TRANSACTION DISCOUNT =================
                label = None
                
                customer_note = getattr(line, "customer_note", "") or ""
                customer_note = customer_note.strip()


                # Diskon item khusus
                if product_name_clean.startswith("10% diskon"):
                    label = "Diskon Produk 10%"

                # Diskon transaksi
                elif product_name_clean == "discount":

                    if "(100%)" in customer_note:
                        label = "Diskon Transaksi 100%"

                    elif "(50%)" in customer_note:
                        label = "Diskon Transaksi 50%"

                    elif "(40%)" in customer_note:
                        label = "Diskon Transaksi 40%"

                    elif "(30%)" in customer_note:
                        label = "Diskon Transaksi 30%"

                    elif "(20%)" in customer_note:
                        label = "Diskon Transaksi 20%"

                    elif "(10%)" in customer_note:
                        label = "Diskon Transaksi 10%"

                    elif "(5%)" in customer_note:
                        label = "Diskon Transaksi 5%"

                    else:
                        label = "Diskon Transaksi Nominal"                

                if label:
    
                    target = (
                        transaction_discount_summary
                        if label.startswith("Diskon Transaksi")
                        else product_discount_summary
                    )

                    if label not in target:
                        target[label] = {"qty": 0, "amount": 0}

                    target[label]["qty"] += abs(line.qty)
                    target[label]["amount"] += abs(line.price_subtotal_incl)

       # sort biar rapi
        discount_summary = dict(sorted(discount_summary.items(), key=lambda x: x[0]))

        product_discount_items = ""
        transaction_discount_items = ""

        # =====================================================
        # DISKON PRODUK
        # =====================================================

        for label, data in product_discount_summary.items():
            product_discount_items += f"""
            <div class="pos-metric" style="background:#ffebee;">
                <div class="pos-metric-label">{label}</div>
                <div class="pos-metric-value" style="color:#c62828;">
                    {int(data['qty'])} qty
                </div>
                <div style="font-size:12px;color:#c62828;margin-top:4px;font-weight:600;">
                    {self._format_currency(data['amount'])}
                </div>
            </div>
            """

        for percent, data in discount_summary.items():
            product_discount_items += f"""
            <div class="pos-metric" style="background:#fff0f0;">
                <div class="pos-metric-label">Diskon Sistem {percent}%</div>
                <div class="pos-metric-value" style="color:#c62828;">
                    {int(data['qty'])} qty
                </div>
                <div style="font-size:12px;color:#c62828;margin-top:4px;font-weight:600;">
                    {self._format_currency(data['amount'])}
                </div>
            </div>
            """

        # =====================================================
        # DISKON TRANSAKSI
        # =====================================================

        display_order = [
            "Diskon Transaksi 5%",
            "Diskon Transaksi 10%",
            "Diskon Transaksi 20%",
            "Diskon Transaksi 30%",
            "Diskon Transaksi 40%",
            "Diskon Transaksi 50%",
            "Diskon Transaksi 100%",
            "Diskon Transaksi Nominal",
        ]

        transaction_total_qty = 0
        transaction_total_amount = 0

        for item in transaction_discount_summary.values():
            transaction_total_qty += item["qty"]
            transaction_total_amount += item["amount"]

        if transaction_discount_summary:

            transaction_discount_items += f"""
            <div class="pos-metric" style="
                background:linear-gradient(135deg,#fff3e0 0%,#ffe0b2 100%);
                border:1px solid #ffcc80;
            ">
                <div class="pos-metric-label">TOTAL DISKON TRANSAKSI</div>
                <div class="pos-metric-value" style="color:#ef6c00;">
                    {int(transaction_total_qty)} qty
                </div>
                <div style="font-size:13px;color:#ef6c00;margin-top:4px;font-weight:700;">
                    {self._format_currency(transaction_total_amount)}
                </div>
            </div>
            """

        for label in display_order:

            if label not in transaction_discount_summary:
                continue

            data = transaction_discount_summary[label]

            short_label = (
                label.replace("Diskon Transaksi ", "")
                    .replace("Nominal", "Nominal")
            )

            transaction_discount_items += f"""
            <div class="pos-metric" style="background:#fff8e1;">
                <div class="pos-metric-label">{short_label}</div>
                <div class="pos-metric-value" style="color:#f57c00;">
                    {int(data['qty'])} qty
                </div>
                <div style="font-size:12px;color:#f57c00;margin-top:4px;font-weight:600;">
                    {self._format_currency(data['amount'])}
                </div>
            </div>
            """

        # fallback
        if not product_discount_items:
            product_discount_items = """
            <div class="pos-metric">
                <div class="pos-metric-label">Tidak Ada Diskon Produk</div>
                <div class="pos-metric-value">0</div>
            </div>
            """

        if not transaction_discount_items:
            transaction_discount_items = """
            <div class="pos-metric">
                <div class="pos-metric-label">Tidak Ada Diskon Transaksi</div>
                <div class="pos-metric-value">0</div>
            </div>
            """

        # Mobile responsive CSS
        responsive_css = """
        <style>
            .pos-dashboard { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; }
            .pos-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 16px; margin-bottom: 20px; color: white; }
            .pos-header h1 { margin: 0; font-size: 24px; font-weight: 700; }
            .pos-header p { margin: 8px 0 0 0; opacity: 0.9; font-size: 14px; }
            .pos-grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
            .pos-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
            .pos-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px; }
            .pos-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
            .pos-grid-4-inner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
            .pos-card { padding: 16px; border-radius: 12px; color: white; }
            .pos-card-label { font-size: 12px; opacity: 0.9; margin-bottom: 6px; }
            .pos-card-value { font-size: 22px; font-weight: 700; word-break: break-word; }
            .pos-section { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .pos-section h3 { margin: 0 0 16px 0; font-size: 16px; color: #333; }
            .pos-metric { text-align: center; padding: 12px; border-radius: 8px; }
            .pos-metric-label { font-size: 10px; color: #666; margin-bottom: 4px; }
            .pos-metric-value { font-size: 16px; font-weight: 600; }

            @media (max-width: 1024px) {
                .pos-grid-5 { grid-template-columns: repeat(3, 1fr); }
                .pos-grid-4 { grid-template-columns: repeat(2, 1fr); }
                .pos-grid-4-inner { grid-template-columns: repeat(2, 1fr); }
                .pos-card-value { font-size: 18px; }
            }

            @media (max-width: 768px) {
                .pos-header { padding: 16px; border-radius: 12px; }
                .pos-header h1 { font-size: 20px; }
                .pos-grid-5 { grid-template-columns: repeat(2, 1fr); gap: 8px; }
                .pos-grid-4 { grid-template-columns: repeat(2, 1fr); gap: 8px; }
                .pos-grid-2 { grid-template-columns: 1fr; }
                .pos-grid-3 { grid-template-columns: repeat(2, 1fr); }
                .pos-grid-4-inner { grid-template-columns: repeat(2, 1fr); }
                .pos-card { padding: 12px; }
                .pos-card-value { font-size: 16px; }
                .pos-section { padding: 16px; }
                .pos-metric { padding: 10px; }
                .pos-metric-value { font-size: 14px; }
            }

            @media (max-width: 480px) {
                .pos-grid-5 { grid-template-columns: 1fr; }
                .pos-grid-4 { grid-template-columns: 1fr; }
                .pos-grid-3 { grid-template-columns: 1fr; }
                .pos-grid-4-inner { grid-template-columns: repeat(2, 1fr); }
                .pos-header h1 { font-size: 18px; }
                .pos-card-value { font-size: 18px; }
            }
        </style>
        """

        html = f"""
        {responsive_css}
        <div class="pos-dashboard">

            <div class="pos-header">
                <h1>🏪 POS Owner Dashboard</h1>
                <p>Periode: {period_label}</p>
            </div>

            <div class="pos-grid-5">

                <div class="pos-card" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                    <div class="pos-card-label">💰 Total Penjualan</div>
                    <div class="pos-card-value">{self._format_currency(self.total_sales)}</div>
                </div>
                
                <div class="pos-card"
                    style="background: linear-gradient(135deg,#ff7675 0%,#d63031 100%);">
                    <div class="pos-card-label">💸 Nilai Cancel</div>
                    <div class="pos-card-value">
                        {self._format_currency(self.cancel_amount)}
                    </div>
                </div>
               

                <div class="pos-card" style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); color: #d32f2f;">
                    <div class="pos-card-label" style="color: #c62828;">📉 Total Diskon</div>
                    <div class="pos-card-value" style="color: #c62828;">- {self._format_currency(self.total_discount)}</div>
                </div>

                <div class="pos-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                    <div class="pos-card-label">📝 Total Order</div>
                    <div class="pos-card-value">{self.total_orders}</div>
                </div>
                
                 <div class="pos-card"
                    style="background: linear-gradient(135deg,#ff6b6b 0%,#ee5a24 100%);">
                    <div class="pos-card-label">❌ Order Cancel</div>
                    <div class="pos-card-value">{self.cancel_orders}</div>
                </div>
                

                <div class="pos-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                    <div class="pos-card-label">📊 Rata-rata/Order</div>
                    <div class="pos-card-value">{self._format_currency(self.average_order_value)}</div>
                </div>

                <div class="pos-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                    <div class="pos-card-label">🧾 Total Pajak</div>
                    <div class="pos-card-value">{self._format_currency(self.total_tax)}</div>
                </div>

            </div>

            <div class="pos-section" style="margin-bottom:20px;">
            <h3>📉 Breakdown Diskon</h3>

            <div style="margin-top:15px;">
                <h4 style="
                    margin:0 0 10px 0;
                    color:#c62828;
                    font-size:14px;
                    font-weight:700;
                ">
                    🏷️ Diskon Produk
                </h4>

                <div class="pos-grid-4-inner">
                    {product_discount_items}
                </div>
            </div>

            <div style="margin-top:20px;">
                <h4 style="
                    margin:0 0 10px 0;
                    color:#ef6c00;
                    font-size:14px;
                    font-weight:700;
                ">
                    💳 Diskon Transaksi
                </h4>

                <div class="pos-grid-4-inner">
                    {transaction_discount_items}
                </div>
            </div>

        </div>

            <div class="pos-grid-2">

               <div class="pos-section">
                <h3>💵 Metrik Keuangan</h3>

                <div class="pos-grid-3">

                    <div class="pos-metric" style="background:#e8f5e9;">
                        <div class="pos-metric-label">Net Sales</div>
                        <div class="pos-metric-value" style="color:#2e7d32;">
                            {self._format_currency(self.net_sales)}
                        </div>
                    </div>

                  

                    <div class="pos-metric" style="background:#ffebee;">
                        <div class="pos-metric-label">Discount %</div>
                        <div class="pos-metric-value" style="color:#c62828;">
                            {self.discount_percent:.1f}%
                        </div>
                    </div>

                    <div class="pos-metric" style="background:#fce4ec;">
                        <div class="pos-metric-label">Cancel Rate</div>
                        <div class="pos-metric-value" style="color:#ad1457;">
                            {self.cancel_rate:.1f}%
                        </div>
                    </div>
  

                </div>
            </div>

            <div class="pos-section">
                <h3>👥 Metrik Pelanggan</h3>

                <div class="pos-grid-4-inner">

                    <div class="pos-metric" style="background: #e3f2fd;">
                        <div class="pos-metric-label">Total Kunjungan</div>
                        <div class="pos-metric-value" style="color: #1976d2;">
                            {self.dine_in_count + self.takeaway_count}
                        </div>
                    </div>

                    <div class="pos-metric" style="background: #e8f5e9;">
                        <div class="pos-metric-label">Dine-in</div>
                        <div class="pos-metric-value" style="color: #388e3c;">
                            {self.dine_in_count}
                        </div>
                    </div>

                    <div class="pos-metric" style="background: #fff3e0;">
                        <div class="pos-metric-label">Takeaway</div>
                        <div class="pos-metric-value" style="color: #f57c00;">
                            {self.takeaway_count}
                        </div>
                    </div>

                </div>
            </div>

            </div>

        </div>
        """

        bills_summary = self._get_bills_summary()
        cash_summary = self._get_cash_movement_summary()

        bills_cash_html = f"""
        <div class="pos-dashboard">
            <div class="pos-grid-2">

                <div class="pos-section">
                    <h3>🧾 Bills</h3>
                    <div class="pos-grid-4-inner">
                        <div class="pos-metric" style="background: #e3f2fd;">
                            <div class="pos-metric-label">Total Bills</div>
                            <div class="pos-metric-value" style="color: #1976d2;">{bills_summary['total']}</div>
                        </div>
                        <div class="pos-metric" style="background: #e8f5e9;">
                            <div class="pos-metric-label">Paid ({bills_summary['paid']})</div>
                            <div class="pos-metric-value" style="color: #388e3c; font-size: 14px;">{self._format_currency(bills_summary['paid_amount'])}</div>
                        </div>
                        <div class="pos-metric" style="background: #fff3e0;">
                            <div class="pos-metric-label">Open ({bills_summary['open']})</div>
                            <div class="pos-metric-value" style="color: #f57c00; font-size: 14px;">{self._format_currency(bills_summary['open_amount'])}</div>
                        </div>
                        <div class="pos-metric" style="background: #f3e5f5;">
                            <div class="pos-metric-label">Total Amount</div>
                            <div class="pos-metric-value" style="color: #7b1fa2; font-size: 14px;">{self._format_currency(bills_summary['amount'])}</div>
                        </div>
                    </div>
                </div>

                <div class="pos-section">
                    <h3>💵 Cash In/Out</h3>
                    <div class="pos-grid-3">
                        <div class="pos-metric" style="background: #e8f5e9;">
                            <div class="pos-metric-label">Cash In</div>
                            <div class="pos-metric-value" style="color: #388e3c; font-size: 14px;">{self._format_currency(cash_summary['cash_in'])}</div>
                        </div>
                        <div class="pos-metric" style="background: #ffebee;">
                            <div class="pos-metric-label">Cash Out</div>
                            <div class="pos-metric-value" style="color: #d32f2f; font-size: 14px;">{self._format_currency(cash_summary['cash_out'])}</div>
                        </div>
                        <div class="pos-metric" style="background: #f5f5f5;">
                            <div class="pos-metric-label">Net Cash</div>
                            <div class="pos-metric-value" style="color: {'#388e3c' if cash_summary['net'] >= 0 else '#d32f2f'}; font-size: 14px;">{self._format_currency(cash_summary['net'])}</div>
                        </div>
                    </div>
                </div>

            </div>
        </div>
        """

        final_html = html + bills_cash_html
        final_html = final_html.replace("\x00", "")
        return final_html
        
   
    def _get_bills_summary(self):
        """Get Bills summary data for dashboard."""
        date_from, date_to = self._get_date_range()
        datetime_from, datetime_to = self._get_datetime_range_utc()
        
        domain = [
            ("create_date", ">=", datetime_from),
            ("create_date", "<=", datetime_to),
            ("company_id", "in", self.env.companies.ids),
        ]
        if self.pos_config_id:
            domain.append(("config_id", "=", self.pos_config_id.id))
        
        # poskas.bill doesn't have session_id natively, filter ignored for session
        
        bills = self.env["poskas.bill"].search(domain)
        paid_bills = bills.filtered(lambda b: b.state == 'paid')
        open_bills = bills.filtered(lambda b: b.state == 'open')
        
        return {
            'total': len(bills),
            'open': len(open_bills),
            'paid': len(paid_bills),
            'paid_amount': sum(paid_bills.mapped('amount_total')),
            'open_amount': sum(open_bills.mapped('amount_total')),
            'amount': sum(bills.mapped('amount_total')),
        }

    def _get_cash_movement_summary(self):
        """Get Cash Movement summary data for dashboard."""
        date_from, date_to = self._get_date_range()
        datetime_from, datetime_to = self._get_datetime_range_utc()
        
        domain = [
            ("movement_time", ">=", datetime_from),
            ("movement_time", "<=", datetime_to),
        ]
        if self.pos_config_id:
            domain.append(("pos_name", "=", self.pos_config_id.name))
        
        # pos.cash.movement doesn't have session_id, filter ignored
        
        movements = self.env["pos.cash.movement"].search(domain)
        cash_in = sum(movements.filtered(lambda m: m.movement_type == 'cash_in').mapped('amount'))
        cash_out = sum(movements.filtered(lambda m: m.movement_type == 'cash_out').mapped('amount'))
        
        return {
            'cash_in': cash_in,
            'cash_out': cash_out,
            'net': cash_in - cash_out,
        }

    def _render_top_products_html(self, products, total_all=0):
        """Render top products as HTML table."""
        if not products:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data produk</p>"
        
        # 1. Group products by name to identify duplicates
        name_groups = {}
        for p in products:
            name = p.get('name', '')
            if name not in name_groups:
                name_groups[name] = []
            name_groups[name].append(p)
            
        # 2. Assign 'offline' flag to highest qty, 'online' to others for duplicates
        for name, group in name_groups.items():
            if len(group) > 1:
                # Sort descending by qty
                sorted_group = sorted(group, key=lambda x: x.get('qty', 0), reverse=True)
                sorted_group[0]['flag'] = 'offline'
                for p in sorted_group[1:]:
                    p['flag'] = 'online'
            else:
                group[0]['flag'] = None

        rows = ""
        for i, product in enumerate(products, 1):
            flag = product.get('flag')
            flag_html = ""
            if flag == 'online':
                flag_html = ' <span style="background-color: #E0F2FE; color: #0369A1; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; margin-left: 8px; display: inline-block; vertical-align: middle;">Online</span>'
                
            rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{i}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; vertical-align: middle;">{product['name']}{flag_html}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{int(product['qty'])}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{self._format_currency(product['total'])}</td>
            </tr>
            """
        
        limit_text = f" dari {total_all} produk" if total_all > len(products) else ""
        showing_text = f"Menampilkan {len(products)}{limit_text}"
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; font-size: 18px; color: #333;">🏆 Produk Terlaris</h3>
                <span style="font-size: 12px; color: #888;">{showing_text}</span>
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #f8f9fa;">
                        <th style="padding: 12px; text-align: left; font-weight: 600;">#</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Produk</th>
                        <th style="padding: 12px; text-align: right; font-weight: 600;">Qty</th>
                        <th style="padding: 12px; text-align: right; font-weight: 600;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """
        return html

    def _render_hourly_orders_html(self, hourly_data):
        """Render hourly orders as a smooth SVG area chart with peak indicators."""
        max_orders = max(hourly_data.values()) if hourly_data.values() else 1
        has_orders = any(hourly_data.values())

        if not has_orders:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data order per jam</p>"

        # --- Chart geometry ---
        chart_w = 900
        chart_h = 260
        pad_top = 40
        pad_bottom = 50
        pad_left = 45
        pad_right = 20
        plot_w = chart_w - pad_left - pad_right
        plot_h = chart_h - pad_top - pad_bottom

        # Build data points (mulai dari jam 07:00 sampai seterusnya)
        hours = list(range(7, 24)) + list(range(0, 7))
        points = []
        for i, h in enumerate(hours):
            x = pad_left + (i / 23) * plot_w
            count = hourly_data.get(h, 0)
            y = pad_top + plot_h - (count / max_orders * plot_h) if max_orders > 0 else pad_top + plot_h
            points.append((x, y, count, h, i))

        # --- Smooth curve (Catmull-Rom → cubic bezier) ---
        def _smooth_path(pts):
            """Convert points to a smooth SVG cubic bezier path using Catmull-Rom."""
            n = len(pts)
            if n < 2:
                return ""
            d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"
            for i in range(n - 1):
                p0 = pts[max(i - 1, 0)]
                p1 = pts[i]
                p2 = pts[min(i + 1, n - 1)]
                p3 = pts[min(i + 2, n - 1)]
                # Catmull-Rom to cubic bezier control points
                cp1x = p1[0] + (p2[0] - p0[0]) / 6
                cp1y = p1[1] + (p2[1] - p0[1]) / 6
                cp2x = p2[0] - (p3[0] - p1[0]) / 6
                cp2y = p2[1] - (p3[1] - p1[1]) / 6
                d += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
            return d

        xy_pts = [(p[0], p[1]) for p in points]
        line_path = _smooth_path(xy_pts)

        # Area path (close to bottom)
        baseline_y = pad_top + plot_h
        area_path = line_path + f" L {points[-1][0]:.1f},{baseline_y:.1f} L {points[0][0]:.1f},{baseline_y:.1f} Z"

        # --- Find top-3 peak hours ---
        sorted_peaks = sorted(points, key=lambda p: p[2], reverse=True)
        top3_hours = set()
        for p in sorted_peaks:
            if p[2] > 0:
                top3_hours.add(p[3])
            if len(top3_hours) >= 3:
                break

        # --- Y-axis labels ---
        y_axis_labels = ""
        grid_lines = ""
        num_ticks = 5
        for i in range(num_ticks + 1):
            val = int(round(max_orders * i / num_ticks))
            y_pos = pad_top + plot_h - (i / num_ticks * plot_h)
            y_axis_labels += f'<text x="{pad_left - 8}" y="{y_pos + 4}" text-anchor="end" fill="#999" font-size="11" font-family="-apple-system,BlinkMacSystemFont,sans-serif">{val}</text>'
            if i > 0:
                grid_lines += f'<line x1="{pad_left}" y1="{y_pos}" x2="{chart_w - pad_right}" y2="{y_pos}" stroke="#eee" stroke-dasharray="4,4" />'

        # --- X-axis labels ---
        x_axis_labels = ""
        for p in points:
            x, _, _, h, i = p
            # Show every 2 hours to avoid crowding, plus always show the last one
            if i % 2 == 0 or i == 23:
                x_axis_labels += f'<text x="{x}" y="{pad_top + plot_h + 22}" text-anchor="middle" fill="#888" font-size="11" font-family="-apple-system,BlinkMacSystemFont,sans-serif">{h:02d}:00</text>'

        # --- Dot markers + peak labels ---
        markers = ""
        peak_labels = ""
        for p in points:
            x, y, count, h, i = p
            is_peak = h in top3_hours
            r = 5 if is_peak else 3
            dot_fill = "#667eea" if count > 0 else "#ccc"
            stroke_w = 2.5 if is_peak else 1.5
            markers += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{dot_fill}" stroke="white" stroke-width="{stroke_w}" />'

            if is_peak and count > 0:
                # Peak label bubble
                lbl_y = y - 18
                peak_labels += f'''
                <g>
                    <rect x="{x - 26}" y="{lbl_y - 13}" width="52" height="22" rx="11" fill="#667eea" />
                    <text x="{x}" y="{lbl_y + 1}" text-anchor="middle" fill="white" font-size="11" font-weight="bold" font-family="-apple-system,BlinkMacSystemFont,sans-serif">{count} order</text>
                </g>'''

        # --- Tooltip rects (invisible hover targets) ---
        tooltip_rects = ""
        col_w = plot_w / 24
        for p in points:
            x, y, count, h, i = p
            tooltip_rects += f'<rect x="{x - col_w/2:.1f}" y="{pad_top}" width="{col_w:.1f}" height="{plot_h}" fill="transparent"><title>Pukul {h:02d}:00 – {h:02d}:59: {count} Order</title></rect>'

        # --- Assemble SVG ---
        svg = f"""
        <svg viewBox="0 0 {chart_w} {chart_h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
            <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#667eea" stop-opacity="0.35"/>
                    <stop offset="100%" stop-color="#764ba2" stop-opacity="0.03"/>
                </linearGradient>
                <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#667eea"/>
                    <stop offset="100%" stop-color="#764ba2"/>
                </linearGradient>
            </defs>
            <!-- grid -->
            {grid_lines}
            <!-- baseline -->
            <line x1="{pad_left}" y1="{baseline_y}" x2="{chart_w - pad_right}" y2="{baseline_y}" stroke="#ddd" stroke-width="1"/>
            <!-- area fill -->
            <path d="{area_path}" fill="url(#areaGrad)" />
            <!-- line -->
            <path d="{line_path}" fill="none" stroke="url(#lineGrad)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
            <!-- markers -->
            {markers}
            <!-- peak labels -->
            {peak_labels}
            <!-- axes labels -->
            {y_axis_labels}
            {x_axis_labels}
            <!-- tooltip hover areas -->
            {tooltip_rects}
        </svg>
        """

        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                <h3 style="margin: 0; font-size: 18px; color: #333;">⏰ Order per Jam</h3>
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <div style="font-size: 13px; color: #666; background: #e3f2fd; padding: 6px 12px; border-radius: 20px; border: 1px solid #bbdefb;">
                        Tertinggi: <strong style="color: #1976d2;">{max_orders}</strong> Order
                    </div>
                </div>
            </div>
            <div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">
                <div style="min-width: 700px;">
                    {svg}
                </div>
            </div>
        </div>
        """
        return html

    def _render_payment_methods_html(self, payment_data):
        """Render payment methods breakdown."""
        if not payment_data:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data pembayaran</p>"
        
        total = sum(payment_data.values())
        colors = ["#667eea", "#28a745", "#ffc107", "#dc3545", "#17a2b8", "#6f42c1"]
        
        items = ""
        for i, (method, amount) in enumerate(sorted(payment_data.items(), key=lambda x: x[1], reverse=True)):
            color = colors[i % len(colors)]
            percentage = (amount / total * 100) if total > 0 else 0
            items += f"""
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-size: 14px; color: #333;">{method}</span>
                    <span style="font-size: 14px; font-weight: 600; color: #333;">{self._format_currency(amount)} ({percentage:.1f}%)</span>
                </div>
                <div style="height: 8px; background: #eee; border-radius: 4px; overflow: hidden;">
                    <div style="height: 100%; width: {percentage}%; background: {color}; border-radius: 4px;"></div>
                </div>
            </div>
            """
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h3 style="margin: 0 0 16px 0; font-size: 18px; color: #333;">💳 Metode Pembayaran</h3>
            {items}
        </div>
        """
        return html

    def _render_cashier_performance_html(self, cashier_data):
        """Render cashier performance table."""
        if not cashier_data:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data kasir</p>"
        
        # Sort by total sales
        sorted_cashiers = sorted(cashier_data.items(), key=lambda x: x[1]["total"], reverse=True)
        
        rows = ""
        for i, (name, data) in enumerate(sorted_cashiers, 1):
            avg = data["total"] / data["orders"] if data["orders"] > 0 else 0
            rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{i}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{name}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{data['orders']}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{self._format_currency(data['total'])}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{self._format_currency(avg)}</td>
            </tr>
            """
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h3 style="margin: 0 0 16px 0; font-size: 18px; color: #333;">👨‍💼 Performa Kasir</h3>
            <div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">
                <table style="width: 100%; border-collapse: collapse; min-width: 500px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 12px; text-align: left; font-weight: 600;">#</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">Kasir</th>
                            <th style="padding: 12px; text-align: right; font-weight: 600;">Orders</th>
                            <th style="padding: 12px; text-align: right; font-weight: 600;">Total Penjualan</th>
                            <th style="padding: 12px; text-align: right; font-weight: 600;">Rata-rata</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
        """
        return html

    @api.depends("date_from", "date_to", "pos_config_id", "status_filter", "page_size_transactions")
    def _compute_transaction_list(self):
        """Compute transaction list HTML."""
        for record in self:
            orders = record._get_orders()
            # Apply status filter
            if record.status_filter and record.status_filter != "all":
                orders = orders.filtered(lambda o: o.state == record.status_filter)
            limit = int(record.page_size_transactions or '25')
            record.transaction_list_html = record._render_transaction_list_html(orders, limit)

    def _render_transaction_list_html(self, orders, limit=25):
        """Render transaction list as HTML table."""
        if not orders:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada transaksi</p>"
        
        total_all = len(orders)
        tz = pytz.timezone('Asia/Jakarta')
        rows = ""
        sorted_orders = orders.sorted(key=lambda o: o.date_order, reverse=True)
        if limit > 0:
            sorted_orders = sorted_orders[:limit]
            
        for order in sorted_orders:
            # Format date - using Asia/Jakarta timezone
            date_str = self._format_datetime_local(order.date_order)
            
            # Status badge color
            status_colors = {
                "paid": "#28a745",
                "done": "#17a2b8",
                "invoiced": "#6f42c1",
                "draft": "#ffc107",
                "cancel": "#dc3545",
            }
            status_color = status_colors.get(order.state, "#6c757d")
            status_label = dict(order._fields['state'].selection).get(order.state, order.state)
            
            # Customer name
            customer = order.partner_id.name if order.partner_id else "Walk-in Customer"
            
            # POS name
            pos_name = order.config_id.name if order.config_id else "-"
            
            # Order type
            order_type = "Takeaway" if order.takeaway else "Dine-in"
            order_type_color = "#f57c00" if order.takeaway else "#388e3c"
            
            rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 12px; font-weight: 500;">{order.name or order.pos_reference or '-'}</td>
                <td style="padding: 12px;">{date_str}</td>
                <td style="padding: 12px;">{customer}</td>
                <td style="padding: 12px;">{pos_name}</td>
                <td style="padding: 12px;">
                    <span style="background: {order_type_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{order_type}</span>
                </td>
                <td style="padding: 12px; text-align: right; font-weight: 600;">{self._format_currency(order.amount_total)}</td>
                <td style="padding: 12px;">
                    <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{status_label}</span>
                </td>
            </tr>
            """
        
        displayed = min(limit, total_all)
        showing_text = f"Menampilkan {displayed} dari {total_all} transaksi" if total_all > limit else f"Menampilkan {total_all} transaksi"
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; font-size: 18px; color: #333;">📋 Daftar Transaksi ({total_all} order)</h3>
                <span style="font-size: 12px; color: #888;">{showing_text}</span>
            </div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; min-width: 800px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 12px; text-align: left; font-weight: 600;">No. Order</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">Tanggal</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">Pelanggan</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">POS</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">Tipe</th>
                            <th style="padding: 12px; text-align: right; font-weight: 600;">Total</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
        """
        return html

    # ==================== BILLS (POSKAS) ====================
    @api.depends("date_from", "date_to", "pos_config_id", "page_size_bills")
    def _compute_bills(self):
        """Compute Bills HTML from poskas.bill model."""
        for record in self:
            date_from, date_to = record._get_date_range()
            datetime_from, datetime_to = record._get_datetime_range_utc()
            limit = int(record.page_size_bills or '25')
            
            domain = [
                ("create_date", ">=", datetime_from),
                ("create_date", "<=", datetime_to),
                ("config_id.company_id", "in", record.env.companies.ids),
            ]
            
            if record.pos_config_id:
                domain.append(("config_id", "=", record.pos_config_id.id))
                
            total_count = record.env["poskas.bill"].search_count(domain)
            if limit > 0:
                bills = record.env["poskas.bill"].search(domain, order="id desc", limit=limit)
            else:
                bills = record.env["poskas.bill"].search(domain, order="id desc")
            record.bills_html = record._render_bills_html(bills, total_count)

    def _render_bills_html(self, bills, total_all=0):
        """Render Bills as HTML table."""
        if not bills:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data bills</p>"
        
        # Summary stats
        displayed = len(bills)
        open_count = len(bills.filtered(lambda b: b.state == "open"))
        paid_count = len(bills.filtered(lambda b: b.state == "paid"))
        total_amount = sum(bills.mapped("amount_total"))
        
        tz = pytz.timezone('Asia/Jakarta')
        rows = ""
        for bill in bills:
            date_str = self._format_datetime_local(bill.create_date)
            
            status_colors = {"open": "#17a2b8", "paid": "#28a745", "cancel": "#dc3545"}
            status_color = status_colors.get(bill.state, "#6c757d")
            
            table_name = bill.table_id.display_name if bill.table_id else (bill.table_ref or "-")
            
            rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px; font-weight: 500;">{bill.name or '-'}</td>
                <td style="padding: 10px;">{date_str}</td>
                <td style="padding: 10px;">{bill.config_id.name if bill.config_id else '-'}</td>
                <td style="padding: 10px;">{table_name}</td>
                <td style="padding: 10px; text-align: right;">{self._format_currency(bill.amount_total)}</td>
                <td style="padding: 10px;">
                    <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;">{bill.state.upper()}</span>
                </td>
            </tr>
            """
        
        showing_text = f"Menampilkan {displayed} dari {total_all} bills" if total_all > displayed else f"Menampilkan {displayed} bills"
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; font-size: 18px; color: #333;">🧾 Bills</h3>
                <span style="font-size: 12px; color: #888;">{showing_text}</span>
            </div>
            
            <!-- Summary -->
            <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
                <div style="background: #e3f2fd; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 100px;">
                    <div style="font-size: 11px; color: #1976d2;">Total Bills</div>
                    <div style="font-size: 18px; font-weight: 600; color: #1976d2;">{total_all}</div>
                </div>
                <div style="background: #e8f5e9; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 100px;">
                    <div style="font-size: 11px; color: #388e3c;">Paid</div>
                    <div style="font-size: 18px; font-weight: 600; color: #388e3c;">{paid_count}</div>
                </div>
                <div style="background: #fff3e0; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 100px;">
                    <div style="font-size: 11px; color: #f57c00;">Open</div>
                    <div style="font-size: 18px; font-weight: 600; color: #f57c00;">{open_count}</div>
                </div>
                <div style="background: #f3e5f5; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 100px;">
                    <div style="font-size: 11px; color: #7b1fa2;">Total</div>
                    <div style="font-size: 16px; font-weight: 600; color: #7b1fa2;">{self._format_currency(total_amount)}</div>
                </div>
            </div>
            
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; min-width: 600px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Nama</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Tanggal</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">POS</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Meja</th>
                            <th style="padding: 10px; text-align: right; font-weight: 600;">Total</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
        """
        return html

    # ==================== CASH IN/OUT ====================
    @api.depends("date_from", "date_to", "pos_config_id", "page_size_cash")
    def _compute_cash_movement(self):
        """Compute Cash Movement HTML from pos.cash.movement model."""
        for record in self:
            date_from, date_to = record._get_date_range()
            datetime_from, datetime_to = record._get_datetime_range_utc()
            limit = int(record.page_size_cash or '25')
            
            domain = [
                ("movement_time", ">=", datetime_from),
                ("movement_time", "<=", datetime_to),
            ]
            
            # Filter by POS name if config is selected
            if record.pos_config_id:
                domain.append(("pos_name", "=", record.pos_config_id.name))
                
            total_count = record.env["pos.cash.movement"].search_count(domain)
            if limit > 0:
                movements = record.env["pos.cash.movement"].search(domain, order="id desc", limit=limit)
            else:
                movements = record.env["pos.cash.movement"].search(domain, order="id desc")
            record.cash_movement_html = record._render_cash_movement_html(movements, total_count)

    def _render_cash_movement_html(self, movements, total_all=0):
        """Render Cash Movement as HTML table."""
        if not movements:
            return "<p style='color: #666; text-align: center; padding: 20px;'>Tidak ada data cash in/out</p>"
        
        # Summary stats
        cash_in = movements.filtered(lambda m: m.movement_type == "cash_in")
        cash_out = movements.filtered(lambda m: m.movement_type == "cash_out")
        total_in = sum(cash_in.mapped("amount"))
        total_out = sum(cash_out.mapped("amount"))
        net_cash = total_in - total_out
        
        tz = pytz.timezone('Asia/Jakarta')
        rows = ""
        for mv in movements:
            date_str = self._format_datetime_local(mv.movement_time)
            
            type_color = "#28a745" if mv.movement_type == "cash_in" else "#dc3545"
            type_label = "Cash In" if mv.movement_type == "cash_in" else "Cash Out"
            
            rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px; font-weight: 500;">{mv.name or '-'}</td>
                <td style="padding: 10px;">{date_str}</td>
                <td style="padding: 10px;">{mv.pos_name or '-'}</td>
                <td style="padding: 10px;">
                    <span style="background: {type_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;">{type_label}</span>
                </td>
                <td style="padding: 10px; text-align: right; font-weight: 600; color: {type_color};">{self._format_currency(mv.amount)}</td>
                <td style="padding: 10px;">{mv.reason or '-'}</td>
            </tr>
            """
        
        net_color = "#28a745" if net_cash >= 0 else "#dc3545"
        
        displayed = len(movements)
        showing_text = f"Menampilkan {displayed} dari {total_all} data" if total_all > displayed else f"Menampilkan {displayed} data"
        
        html = f"""
        <div style="background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; font-size: 18px; color: #333;">💵 Cash In/Out</h3>
                <span style="font-size: 12px; color: #888;">{showing_text}</span>
            </div>
            
            <!-- Summary -->
            <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
                <div style="background: #e8f5e9; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 120px;">
                    <div style="font-size: 11px; color: #388e3c;">Total Cash In</div>
                    <div style="font-size: 18px; font-weight: 600; color: #388e3c;">{self._format_currency(total_in)}</div>
                    <div style="font-size: 11px; color: #666;">{len(cash_in)} transaksi</div>
                </div>
                <div style="background: #ffebee; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 120px;">
                    <div style="font-size: 11px; color: #d32f2f;">Total Cash Out</div>
                    <div style="font-size: 18px; font-weight: 600; color: #d32f2f;">{self._format_currency(total_out)}</div>
                    <div style="font-size: 11px; color: #666;">{len(cash_out)} transaksi</div>
                </div>
                <div style="background: #f5f5f5; padding: 12px 16px; border-radius: 8px; flex: 1; min-width: 120px;">
                    <div style="font-size: 11px; color: #333;">Net Cash</div>
                    <div style="font-size: 18px; font-weight: 600; color: {net_color};">{self._format_currency(net_cash)}</div>
                </div>
            </div>
            
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; min-width: 600px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; font-weight: 600;">ID</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Waktu</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">POS</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Tipe</th>
                            <th style="padding: 10px; text-align: right; font-weight: 600;">Jumlah</th>
                            <th style="padding: 10px; text-align: left; font-weight: 600;">Alasan</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
        """
        return html

    # ==================== EXPORT TO EXCEL ====================
    def action_export_excel(self):
        """Export dashboard data to Excel file."""
        self.ensure_one()
        
        try:
            import xlsxwriter
        except ImportError:
            raise ValueError("xlsxwriter library is required. Install with: pip install xlsxwriter")
        
        # Create workbook in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Formats
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#667eea', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter'
        })
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'
        })
        money_format = workbook.add_format({'num_format': '#,##0', 'align': 'right', 'border': 1, 'valign': 'vcenter'})
        percent_format = workbook.add_format({'num_format': '0.00%', 'align': 'right', 'border': 1, 'valign': 'vcenter'})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy hh:mm', 'align': 'center', 'border': 1, 'valign': 'vcenter'})
        cell_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        number_format = workbook.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter'})
        
        # Get data
        orders = self._get_orders()
        period_label = self._get_period_label()
        date_from, date_to = self._get_date_range()
        
        # ========== SHEET 1: SUMMARY ==========
        ws_summary = workbook.add_worksheet('Ringkasan')
        ws_summary.set_column('A:A', 40)
        ws_summary.set_column('B:B', 20)
        
        ws_summary.merge_range('A1:B1', f'POS Owner Dashboard - {period_label}', title_format)
        ws_summary.write('A2', f'Periode: {date_from} - {date_to}')
        ws_summary.write('A3', f'POS: {self.pos_config_id.name if self.pos_config_id else "Semua POS"}')
        
        # Sales Summary
        row = 5
        ws_summary.write(row, 0, 'RINGKASAN', header_format)
        ws_summary.write(row, 1, '', header_format)
        row += 1
        ws_summary.write(row, 0, 'Total Penjualan', cell_format)
        ws_summary.write(row, 1, self.total_sales, money_format)
        row += 1
        ws_summary.write(row, 0, 'Total Order', cell_format)
        ws_summary.write(row, 1, self.total_orders, number_format)
        row += 1
        ws_summary.write(row, 0, 'Rata-rata per Order', cell_format)
        ws_summary.write(row, 1, self.average_order_value, money_format)
        row += 1
        ws_summary.write(row, 0, 'Total Pajak', cell_format)
        ws_summary.write(row, 1, self.total_tax, money_format)
        
        # Financial Metrics
        row += 2
        ws_summary.write(row, 0, 'METRIK KEUANGAN', header_format)
        ws_summary.write(row, 1, '', header_format)
        row += 1
        ws_summary.write(row, 0, 'Total Margin', cell_format)
        ws_summary.write(row, 1, self.total_margin, money_format)
        row += 1
        ws_summary.write(row, 0, 'Rata-rata Margin (%)', cell_format)
        ws_summary.write(row, 1, self.average_margin_percent / 100 if self.average_margin_percent else 0, percent_format)
        row += 1
        ws_summary.write(row, 0, 'Total Diskon', cell_format)
        ws_summary.write(row, 1, self.total_discount, money_format)
        
        # Customer Metrics
        row += 2
        ws_summary.write(row, 0, 'METRIK PELANGGAN', header_format)
        ws_summary.write(row, 1, '', header_format)
        row += 1
        ws_summary.write(row, 0, 'Pelanggan Unik', cell_format)
        ws_summary.write(row, 1, self.unique_customers, number_format)
        row += 1
        ws_summary.write(row, 0, 'Total Tamu', cell_format)
        ws_summary.write(row, 1, self.total_guests, number_format)
        row += 1
        ws_summary.write(row, 0, 'Order Dine-in', cell_format)
        ws_summary.write(row, 1, self.dine_in_count, number_format)
        row += 1
        ws_summary.write(row, 0, 'Order Takeaway', cell_format)
        ws_summary.write(row, 1, self.takeaway_count, number_format)
        
        # Bills Summary
        bills_summary = self._get_bills_summary()
        row += 2
        ws_summary.write(row, 0, 'BILLS', header_format)
        ws_summary.write(row, 1, '', header_format)
        row += 1
        ws_summary.write(row, 0, 'Total Bills', cell_format)
        ws_summary.write(row, 1, bills_summary['total'], number_format)
        row += 1
        ws_summary.write(row, 0, 'Bills Paid', cell_format)
        ws_summary.write(row, 1, bills_summary['paid'], number_format)
        row += 1
        ws_summary.write(row, 0, 'Bills Open', cell_format)
        ws_summary.write(row, 1, bills_summary['open'], number_format)
        row += 1
        ws_summary.write(row, 0, 'Bills Total Amount', cell_format)
        ws_summary.write(row, 1, bills_summary['amount'], money_format)
        
        # Cash In/Out Summary
        cash_summary = self._get_cash_movement_summary()
        row += 2
        ws_summary.write(row, 0, 'CASH IN/OUT', header_format)
        ws_summary.write(row, 1, '', header_format)
        row += 1
        ws_summary.write(row, 0, 'Total Cash In', cell_format)
        ws_summary.write(row, 1, cash_summary['cash_in'], money_format)
        row += 1
        ws_summary.write(row, 0, 'Total Cash Out', cell_format)
        ws_summary.write(row, 1, cash_summary['cash_out'], money_format)
        row += 1
        ws_summary.write(row, 0, 'Net Cash', cell_format)
        ws_summary.write(row, 1, cash_summary['net'], money_format)
        
        if not self.pos_config_id:
            row += 2
            ws_summary.set_column('A:E', 20)  # Expand columns for breakdown
            ws_summary.write(row, 0, 'POS', header_format)
            ws_summary.write(row, 1, 'Total Penjualan', header_format)
            ws_summary.write(row, 2, 'Total Order', header_format)
            ws_summary.write(row, 3, 'Rata-rata per Order', header_format)
            ws_summary.write(row, 4, 'Margin', header_format)
            
            # Group orders by POS
            pos_data = {}
            for order in orders:
                pos_name = order.config_id.name if order.config_id else 'Unknown'
                if pos_name not in pos_data:
                    pos_data[pos_name] = {
                        'sales': 0,
                        'orders': 0,
                        'margin': 0,
                        'tax': 0,
                        'guests': 0,
                        'dine_in': 0,
                        'takeaway': 0,
                    }
                pos_data[pos_name]['sales'] += order.amount_total
                pos_data[pos_name]['orders'] += 1
                pos_data[pos_name]['margin'] += order.margin
                pos_data[pos_name]['tax'] += order.amount_tax
                pos_data[pos_name]['guests'] += order.customer_count
                if order.takeaway:
                    pos_data[pos_name]['takeaway'] += 1
                else:
                    pos_data[pos_name]['dine_in'] += 1
            
            # Write POS breakdown
            for pos_name, data in sorted(pos_data.items(), key=lambda x: x[1]['sales'], reverse=True):
                row += 1
                avg_order = data['sales'] / data['orders'] if data['orders'] > 0 else 0
                ws_summary.write(row, 0, pos_name, cell_format)
                ws_summary.write(row, 1, data['sales'], money_format)
                ws_summary.write(row, 2, data['orders'], number_format)
                ws_summary.write(row, 3, avg_order, money_format)
                ws_summary.write(row, 4, data['margin'], money_format)
            
            # Grand Total row
            row += 1
            total_sales = sum(d['sales'] for d in pos_data.values())
            total_orders = sum(d['orders'] for d in pos_data.values())
            total_margin = sum(d['margin'] for d in pos_data.values())
            grand_avg = total_sales / total_orders if total_orders > 0 else 0
            ws_summary.write(row, 0, 'GRAND TOTAL', header_format)
            ws_summary.write(row, 1, total_sales, money_format)
            ws_summary.write(row, 2, total_orders, number_format)
            ws_summary.write(row, 3, grand_avg, money_format)
            ws_summary.write(row, 4, total_margin, money_format)
        
        # ========== SHEET 2: TOP PRODUCTS ==========
        ws_products = workbook.add_worksheet('Top Produk')
        ws_products.set_column('A:A', 5)
        ws_products.set_column('B:B', 40)
        ws_products.set_column('C:D', 15)
        
        # Aggregate product sales
        product_sales = {}
        for order in orders:
            for line in order.lines:
                product_id = line.product_id.id
                if product_id not in product_sales:
                    product_sales[product_id] = {
                        "name": line.product_id.name,
                        "qty": 0,
                        "total": 0,
                    }
                product_sales[product_id]["qty"] += line.qty
                product_sales[product_id]["total"] += line.price_subtotal_incl
        
        sorted_products = sorted(product_sales.values(), key=lambda x: x["qty"], reverse=True)
        
        ws_products.write(0, 0, '#', header_format)
        ws_products.write(0, 1, 'Produk', header_format)
        ws_products.write(0, 2, 'Qty', header_format)
        ws_products.write(0, 3, 'Total', header_format)
        
        for i, product in enumerate(sorted_products, 1):
            ws_products.write(i, 0, i, number_format)
            ws_products.write(i, 1, product['name'], cell_format)
            ws_products.write(i, 2, int(product['qty']), number_format)
            ws_products.write(i, 3, product['total'], money_format)
        
        # ========== SHEET 3: HOURLY ORDERS ==========
        ws_hourly = workbook.add_worksheet('Order per Jam')
        ws_hourly.set_column('A:B', 15)
        
        hourly_data = {h: 0 for h in range(24)}
        for order in orders:
            if order.date_order:
                hour = order.date_order.hour
                hourly_data[hour] += 1
        
        ws_hourly.write(0, 0, 'Jam', header_format)
        ws_hourly.write(0, 1, 'Jumlah Order', header_format)
        
        for hour in range(24):
            ws_hourly.write(hour + 1, 0, f'{hour:02d}:00', cell_format)
            ws_hourly.write(hour + 1, 1, hourly_data[hour], number_format)
        
        # ========== SHEET 4: PAYMENT METHODS ==========
        ws_payment = workbook.add_worksheet('Metode Pembayaran')
        ws_payment.set_column('A:A', 30)
        ws_payment.set_column('B:C', 15)
        
        payment_data = {}
        for order in orders:
            for payment in order.payment_ids:
                method_name = payment.payment_method_id.name
                if method_name not in payment_data:
                    payment_data[method_name] = 0
                payment_data[method_name] += payment.amount
        
        ws_payment.write(0, 0, 'Metode Pembayaran', header_format)
        ws_payment.write(0, 1, 'Total', header_format)
        ws_payment.write(0, 2, 'Persentase', header_format)
        
        total_payment = sum(payment_data.values())
        row = 1
        for method, amount in sorted(payment_data.items(), key=lambda x: x[1], reverse=True):
            ws_payment.write(row, 0, method, cell_format)
            ws_payment.write(row, 1, amount, money_format)
            ws_payment.write(row, 2, amount / total_payment if total_payment > 0 else 0, percent_format)
            row += 1
        
        # ========== SHEET 5: CASHIER PERFORMANCE ==========
        ws_cashier = workbook.add_worksheet('Performa Kasir')
        ws_cashier.set_column('A:A', 5)
        ws_cashier.set_column('B:B', 30)
        ws_cashier.set_column('C:E', 15)
        
        cashier_data = {}
        for order in orders:
            user_name = order.user_id.name or "Unknown"
            if user_name not in cashier_data:
                cashier_data[user_name] = {"orders": 0, "total": 0}
            cashier_data[user_name]["orders"] += 1
            cashier_data[user_name]["total"] += order.amount_total
        
        ws_cashier.write(0, 0, '#', header_format)
        ws_cashier.write(0, 1, 'Kasir', header_format)
        ws_cashier.write(0, 2, 'Jumlah Order', header_format)
        ws_cashier.write(0, 3, 'Total Penjualan', header_format)
        ws_cashier.write(0, 4, 'Rata-rata', header_format)
        
        row = 1
        for i, (name, data) in enumerate(sorted(cashier_data.items(), key=lambda x: x[1]["total"], reverse=True), 1):
            avg = data["total"] / data["orders"] if data["orders"] > 0 else 0
            ws_cashier.write(row, 0, i, number_format)
            ws_cashier.write(row, 1, name, cell_format)
            ws_cashier.write(row, 2, data["orders"], number_format)
            ws_cashier.write(row, 3, data["total"], money_format)
            ws_cashier.write(row, 4, avg, money_format)
            row += 1
        
        # ========== SHEET 6: TRANSACTION LIST ==========
        ws_trans = workbook.add_worksheet('Transaksi')
        ws_trans.set_column('A:A', 15)
        ws_trans.set_column('B:B', 18)
        ws_trans.set_column('C:C', 25)
        ws_trans.set_column('D:D', 15)
        ws_trans.set_column('E:F', 12)
        ws_trans.set_column('G:G', 10)
        
        ws_trans.write(0, 0, 'No. Order', header_format)
        ws_trans.write(0, 1, 'Tanggal', header_format)
        ws_trans.write(0, 2, 'Pelanggan', header_format)
        ws_trans.write(0, 3, 'POS', header_format)
        ws_trans.write(0, 4, 'Tipe', header_format)
        ws_trans.write(0, 5, 'Total', header_format)
        ws_trans.write(0, 6, 'Status', header_format)
        
        row = 1
        for order in orders.sorted(key=lambda o: o.date_order, reverse=True):
            ws_trans.write(row, 0, order.name or order.pos_reference or '-', cell_format)
            ws_trans.write(row, 1, self._format_datetime_local(order.date_order), cell_format)
            ws_trans.write(row, 2, order.partner_id.name if order.partner_id else 'Walk-in Customer', cell_format)
            ws_trans.write(row, 3, order.config_id.name if order.config_id else '-', cell_format)
            ws_trans.write(row, 4, 'Takeaway' if order.takeaway else 'Dine-in', cell_format)
            ws_trans.write(row, 5, order.amount_total, money_format)
            ws_trans.write(row, 6, order.state, cell_format)
            row += 1
        
        # ========== SHEET 7: BILLS ==========
        ws_bills = workbook.add_worksheet('Bills')
        ws_bills.set_column('A:A', 20)
        ws_bills.set_column('B:B', 18)
        ws_bills.set_column('C:C', 20)
        ws_bills.set_column('D:D', 15)
        ws_bills.set_column('E:E', 15)
        ws_bills.set_column('F:F', 10)
        
        # Get bills data
        bills_summary = self._get_bills_summary()
        date_from, date_to = self._get_date_range()
        datetime_from, datetime_to = self._get_datetime_range_utc()
        
        bills_domain = [
            ("create_date", ">=", datetime_from),
            ("create_date", "<=", datetime_to),
        ]
        if self.pos_config_id:
            bills_domain.append(("config_id", "=", self.pos_config_id.id))
            
        bills = self.env["poskas.bill"].search(bills_domain, order="id desc")
        
        # Bills Detail Table
        row = 0
        ws_bills.write(row, 0, 'Nama', header_format)
        ws_bills.write(row, 1, 'Tanggal', header_format)
        ws_bills.write(row, 2, 'POS', header_format)
        ws_bills.write(row, 3, 'Meja', header_format)
        ws_bills.write(row, 4, 'Total', header_format)
        ws_bills.write(row, 5, 'Status', header_format)
        
        row = 1
        for bill in bills:
            ws_bills.write(row, 0, bill.name or '-', cell_format)
            ws_bills.write(row, 1, self._format_datetime_local(bill.create_date), cell_format)
            ws_bills.write(row, 2, bill.config_id.name if bill.config_id else '-', cell_format)
            table_name = bill.table_id.display_name if bill.table_id else (bill.table_ref or '-')
            ws_bills.write(row, 3, table_name, cell_format)
            ws_bills.write(row, 4, bill.amount_total, money_format)
            ws_bills.write(row, 5, bill.state.upper() if bill.state else '-', cell_format)
            row += 1
        
        # ========== SHEET 8: CASH IN/OUT ==========
        ws_cash = workbook.add_worksheet('Cash In Out')
        ws_cash.set_column('A:A', 25)
        ws_cash.set_column('B:B', 18)
        ws_cash.set_column('C:C', 20)
        ws_cash.set_column('D:D', 12)
        ws_cash.set_column('E:E', 15)
        ws_cash.set_column('F:F', 30)
        
        # Get cash movement data
        cash_summary = self._get_cash_movement_summary()
        cash_domain = [
            ("movement_time", ">=", datetime_from),
            ("movement_time", "<=", datetime_to),
        ]
        if self.pos_config_id:
            cash_domain.append(("pos_name", "=", self.pos_config_id.name))
            
        movements = self.env["pos.cash.movement"].search(cash_domain, order="id desc")
        
        # Cash Movement Detail Table
        row = 0
        ws_cash.write(row, 0, 'ID', header_format)
        ws_cash.write(row, 1, 'Waktu', header_format)
        ws_cash.write(row, 2, 'POS', header_format)
        ws_cash.write(row, 3, 'Tipe', header_format)
        ws_cash.write(row, 4, 'Jumlah', header_format)
        ws_cash.write(row, 5, 'Alasan', header_format)
        
        row = 1
        for mv in movements:
            ws_cash.write(row, 0, mv.name or '-', cell_format)
            ws_cash.write(row, 1, self._format_datetime_local(mv.movement_time), cell_format)
            ws_cash.write(row, 2, mv.pos_name or '-', cell_format)
            ws_cash.write(row, 3, 'Cash In' if mv.movement_type == 'cash_in' else 'Cash Out', cell_format)
            ws_cash.write(row, 4, mv.amount, money_format)
            ws_cash.write(row, 5, mv.reason or '-', cell_format)
            row += 1
        
        workbook.close()
        output.seek(0)
        
        # Create attachment
        filename = f"POS_Dashboard_{period_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
