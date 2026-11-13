import base64
import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

VALID_STATES = ("paid", "done", "invoiced")

# Odoo taxes are classified by name, e.g. "PBJT 10% Upas" -> PB1, "PNBP 2.5% Upas" -> PNBP.
PNBP_KEYWORDS = ("PNBP",)
PB1_KEYWORDS = ("PBJT", "PB1")


def tax_kind(tax_name):
    """'pnbp', 'pb1' or None for an Odoo tax name."""
    name = (tax_name or "").upper()
    if any(word in name for word in PNBP_KEYWORDS):
        return "pnbp"
    if any(word in name for word in PB1_KEYWORDS):
        return "pb1"
    return None

MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# (row key, Excel header, kind). Order = column order in the Excel file.
COLUMNS = [
    ("sequence", "No", "int"),
    ("klaster", "Nama Klaster", "text"),
    ("lokasi", "Nama Lokasi", "text"),
    ("tenant", "Nama Tenant", "text"),
    ("kasir", "Nama Kasir", "text"),
    ("customer", "Nama Customer", "text"),
    ("no_transaksi", "No Transaksi", "text"),
    ("tanggal_transaksi", "Tanggal Transaksi", "date"),
    ("waktu", "Waktu", "text"),
    ("jenis_pembayaran", "Jenis Pembayaran", "text"),
    ("total_kotor", "Total Kotor", "money"),
    ("diskon", "Diskon", "money"),
    ("biaya_penanganan", "Biaya Penanganan", "money"),
    ("pb1", "Tax/PB1", "money"),
    ("pnbp", "Pnbp", "money"),
    ("pajak", "Pajak (PB1+Pnbp)", "money"),
    ("pendapatan", "Pendapatan", "money"),
    ("tanggal_pembayaran", "Tanggal Pembayaran", "date"),
    ("pendapatan_minus_pb1", "Pendapatan (-) Tax", "money"),
    ("netto", "Pendapatan (-) Pnbp+PB1 atau Netto", "money"),
]
MONEY_KEYS = [key for key, _header, kind in COLUMNS if kind == "money"]


def format_date_id(value):
    """date -> '01 Oktober 2026'."""
    if not value:
        return ""
    return "%02d %s %d" % (value.day, MONTHS_ID[value.month - 1], value.year)


class PosTenantReportWizard(models.TransientModel):
    _name = "pos.tenant.report.wizard"
    _description = "POS Tenant Transaction Report"

    date_from = fields.Date(
        string="Dari Tanggal", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string="Sampai Tanggal", required=True, default=fields.Date.context_today)
    company_ids = fields.Many2many(
        "res.company", string="Company",
        default=lambda self: self.env.companies,
        help="Kosong = semua company yang sedang aktif dipilih.")
    config_ids = fields.Many2many(
        "pos.config", string="Point of Sale",
        help="Kosong = semua POS di company terpilih.")
    handling_product_ids = fields.Many2many(
        "product.product", string="Produk Biaya Penanganan",
        help="Baris order dengan produk ini masuk kolom Biaya Penanganan, "
             "bukan Total Kotor. Kosongkan kalau tidak ada.")
    line_ids = fields.One2many("pos.tenant.report.line", "wizard_id")
    xlsx_file = fields.Binary(readonly=True, attachment=False)
    xlsx_filename = fields.Char(readonly=True)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_("Tanggal awal tidak boleh setelah tanggal akhir."))

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Jakarta")

    def _to_local(self, value):
        if not value:
            return None
        return pytz.utc.localize(value).astimezone(self._tz())

    def _get_orders(self):
        self.ensure_one()
        tz = self._tz()
        start = tz.localize(datetime.combine(self.date_from, time.min))
        end = tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        companies = self.company_ids or self.env.companies
        domain = [
            ("state", "in", VALID_STATES),
            ("date_order", ">=", start.astimezone(pytz.utc).replace(tzinfo=None)),
            ("date_order", "<", end.astimezone(pytz.utc).replace(tzinfo=None)),
            ("company_id", "in", companies.ids),
        ]
        if self.config_ids:
            domain.append(("config_id", "in", self.config_ids.ids))
        return self.env["pos.order"].search(domain, order="date_order, id")

    @staticmethod
    def _is_discount_line(line):
        """Reward / global discount lines count as discount, not gross."""
        if "is_reward_line" in line._fields and line.is_reward_line:
            return True
        config = line.order_id.config_id
        return bool(
            "discount_product_id" in config._fields
            and config.discount_product_id
            and line.product_id == config.discount_product_id
        )

    def _order_row(self, order, sequence):
        currency = order.currency_id
        partner = order.partner_id

        gross = subtotal = handling = pb1 = pnbp = 0.0
        for line in order.lines:
            taxes = line.tax_ids_after_fiscal_position
            if line.product_id in self.handling_product_ids:
                handling += line.price_subtotal
            else:
                subtotal += line.price_subtotal
                if not self._is_discount_line(line):
                    if taxes:
                        gross += taxes.compute_all(
                            line.price_unit, currency, line.qty,
                            product=line.product_id, partner=partner,
                        )["total_excluded"]
                    else:
                        gross += line.price_unit * line.qty
            if taxes:
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                res = taxes.compute_all(
                    price, currency, line.qty, product=line.product_id, partner=partner)
                for tax in res["taxes"]:
                    kind = tax_kind(tax["name"])
                    if kind == "pb1":
                        pb1 += tax["amount"]
                    elif kind == "pnbp":
                        pnbp += tax["amount"]

        pendapatan = order.amount_total
        payments = order.payment_ids
        method_names = list(dict.fromkeys(payments.mapped("payment_method_id.name")))
        payment_dates = [d for d in payments.mapped("payment_date") if d]
        order_dt = self._to_local(order.date_order)
        payment_dt = self._to_local(max(payment_dates)) if payment_dates else None

        kasir = order.user_id
        if "employee_id" in order._fields and order.employee_id:
            kasir = order.employee_id
        company = order.company_id

        row = {
            "sequence": sequence,
            "order_id": order.id,
            "currency_id": currency.id,
            "klaster": company.parent_id.name or "",
            "lokasi": company.name or "",
            "tenant": order.config_id.name or "",
            "kasir": kasir.name or "",
            "customer": partner.name or "",
            "no_transaksi": order.pos_reference or order.name or "",
            "tanggal_transaksi": order_dt.date() if order_dt else False,
            "waktu": order_dt.strftime("%H:%M:%S") if order_dt else "",
            "jenis_pembayaran": ", ".join(method_names),
            "total_kotor": gross,
            "diskon": gross - subtotal,
            "biaya_penanganan": handling,
            "pb1": pb1,
            "pnbp": pnbp,
            "pajak": pb1 + pnbp,
            "pendapatan": pendapatan,
            "tanggal_pembayaran": payment_dt.date() if payment_dt else False,
            "pendapatan_minus_pb1": pendapatan - pb1,
            "netto": pendapatan - pb1 - pnbp,
        }
        for key in MONEY_KEYS:
            row[key] = currency.round(row[key])
        return row

    def _build_rows(self):
        self.ensure_one()
        orders = self._get_orders()
        if not orders:
            raise UserError(_("Tidak ada transaksi POS pada periode dan filter ini."))
        return [self._order_row(order, seq) for seq, order in enumerate(orders, 1)]

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def action_view_lines(self):
        self.ensure_one()
        rows = self._build_rows()
        self.line_ids.unlink()
        self.env["pos.tenant.report.line"].create(
            [dict(row, wizard_id=self.id) for row in rows])
        return {
            "type": "ir.actions.act_window",
            "name": _("Laporan Transaksi Tenant %(start)s - %(end)s",
                      start=format_date_id(self.date_from), end=format_date_id(self.date_to)),
            "res_model": "pos.tenant.report.line",
            "view_mode": "list",
            "domain": [("wizard_id", "=", self.id)],
            "context": {"pos_tenant_report_wizard_id": self.id},
            "target": "current",
        }

    def action_export_xlsx(self):
        self.ensure_one()
        content = self._render_xlsx(self._build_rows())
        filename = "Laporan_Transaksi_Tenant_%s_%s.xlsx" % (self.date_from, self.date_to)
        self.write({"xlsx_file": base64.b64encode(content), "xlsx_filename": filename})
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%s&field=xlsx_file&filename_field=xlsx_filename&download=true"
                   % (self._name, self.id),
            "target": "self",
        }

    def _render_xlsx(self, rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Transaksi")

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#FFFF00", "border": 1,
            "align": "center", "valign": "vcenter", "text_wrap": True,
        })
        text_fmt = workbook.add_format({"border": 1})
        center_fmt = workbook.add_format({"border": 1, "align": "center"})
        money_fmt = workbook.add_format({"border": 1, "num_format": '#,##0;-#,##0;"-"'})
        total_label_fmt = workbook.add_format({"border": 1, "bold": True, "bg_color": "#D9D9D9"})
        total_money_fmt = workbook.add_format({
            "border": 1, "bold": True, "bg_color": "#D9D9D9", "num_format": '#,##0;-#,##0;"-"',
        })

        widths = {"int": 6, "text": 22, "date": 18, "money": 15}
        for col, (key, header, kind) in enumerate(COLUMNS):
            sheet.set_column(col, col, 26 if key == "netto" else widths[kind])
            sheet.write(0, col, header, header_fmt)
        sheet.set_row(0, 30)
        sheet.freeze_panes(1, 0)

        for r, row in enumerate(rows, 1):
            for col, (key, _header, kind) in enumerate(COLUMNS):
                value = row.get(key)
                if kind == "money":
                    sheet.write_number(r, col, value or 0.0, money_fmt)
                elif kind == "date":
                    sheet.write(r, col, format_date_id(value), center_fmt)
                elif kind == "int":
                    sheet.write_number(r, col, value, center_fmt)
                else:
                    sheet.write(r, col, value or "", text_fmt)

        total_row = len(rows) + 1
        for col, (key, _header, kind) in enumerate(COLUMNS):
            if kind == "money":
                sheet.write_number(
                    total_row, col, sum(row[key] for row in rows), total_money_fmt)
            else:
                sheet.write(total_row, col, "TOTAL" if col == 0 else "", total_label_fmt)
        sheet.autofilter(0, 0, len(rows), len(COLUMNS) - 1)

        workbook.close()
        return output.getvalue()


class PosTenantReportLine(models.TransientModel):
    _name = "pos.tenant.report.line"
    _description = "POS Tenant Transaction Report Line"
    _order = "sequence"

    wizard_id = fields.Many2one("pos.tenant.report.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(string="No")
    order_id = fields.Many2one("pos.order", string="Order", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    klaster = fields.Char(string="Nama Klaster")
    lokasi = fields.Char(string="Nama Lokasi")
    tenant = fields.Char(string="Nama Tenant")
    kasir = fields.Char(string="Nama Kasir")
    customer = fields.Char(string="Nama Customer")
    no_transaksi = fields.Char(string="No Transaksi")
    tanggal_transaksi = fields.Date(string="Tanggal Transaksi")
    waktu = fields.Char(string="Waktu")
    jenis_pembayaran = fields.Char(string="Jenis Pembayaran")
    total_kotor = fields.Monetary(string="Total Kotor")
    diskon = fields.Monetary(string="Diskon")
    biaya_penanganan = fields.Monetary(string="Biaya Penanganan")
    pb1 = fields.Monetary(string="Tax/PB1")
    pnbp = fields.Monetary(string="Pnbp")
    pajak = fields.Monetary(string="Pajak (PB1+Pnbp)")
    pendapatan = fields.Monetary(string="Pendapatan")
    tanggal_pembayaran = fields.Date(string="Tanggal Pembayaran")
    pendapatan_minus_pb1 = fields.Monetary(string="Pendapatan (-) Tax")
    netto = fields.Monetary(string="Netto")

    def action_export_xlsx(self):
        wizard = self.env["pos.tenant.report.wizard"].browse(
            self.env.context.get("pos_tenant_report_wizard_id")).exists()
        if not wizard:
            raise UserError(_("Buka ulang report dari menu Laporan Transaksi Tenant."))
        return wizard.action_export_xlsx()
