import json
import logging
from datetime import timedelta

import pytz

from odoo import _, api, fields, models

from ..services import union_payload
from ..services.econique_client import EconiqueError, EconiqueLoginError, EconiqueNetworkError

_logger = logging.getLogger(__name__)

CRON_XMLID = "pos_econique_union.ir_cron_econique_send"
# Kode error Econique yang masuk akal dicoba lagi.
RETRYABLE_CODES = {"E.TC.PT.003"}
CRON_BATCH = 50


class PosEconiqueTransaction(models.Model):
    """Antrian + log pengiriman satu order POS ke Econique.

    Dibuat saat order lunas (lihat pos_order.py), dikirim oleh cron. Pengiriman
    tidak pernah memblokir atau menggagalkan pembayaran di POS.
    """

    _name = "pos.econique.transaction"
    _description = "Econique Transaction"
    _order = "id desc"

    order_id = fields.Many2one(
        "pos.order", required=True, ondelete="cascade", index=True, readonly=True
    )
    pos_config_id = fields.Many2one(related="order_id.config_id", store=True, index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    credential_id = fields.Many2one(
        "pos.payment.gateway.credential", required=True, ondelete="restrict", readonly=True
    )
    invoice_number = fields.Char(readonly=True, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        default="pending",
        required=True,
        index=True,
        readonly=True,
    )
    attempts = fields.Integer(readonly=True)
    next_attempt = fields.Datetime(readonly=True)
    sent_date = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    response_code = fields.Char(readonly=True)
    remote_uuid = fields.Char(string="Econique UUID", readonly=True)
    total_netto = fields.Char(string="Total Netto (Econique)", readonly=True)
    request_payload = fields.Text(readonly=True)
    response_payload = fields.Text(readonly=True)

    _sql_constraints = [
        ("order_uniq", "unique(order_id)", "Order ini sudah punya antrian Econique."),
    ]

    # ------------------------------------------------------------------ #
    # Antrian
    # ------------------------------------------------------------------ #
    @api.model
    def _enqueue_order(self, order):
        """Buat antrian untuk order bila POS-nya punya credential Econique aktif.

        :return: True bila ada antrian pending baru (cron perlu dipicu).
        """
        cred = self.env["pos.payment.gateway.credential"].sudo().search(
            [
                ("pos_config_id", "=", order.config_id.id),
                ("gateway_code", "=", "econique"),
                ("econique_auto_send", "=", True),
            ],
            limit=1,
        )
        if not cred or self.search_count([("order_id", "=", order.id)]):
            return False

        vals = {
            "order_id": order.id,
            "credential_id": cred.id,
            "invoice_number": order.pos_reference if cred.econique_invoice_source == "pos_reference"
            and order.pos_reference else order.name,
        }
        if order.amount_total <= 0:
            vals.update(
                state="skipped",
                last_error=_("Order dengan total nol atau negatif (refund) tidak dikirim."),
            )
        self.create(vals)
        return vals.get("state") != "skipped"

    @api.model
    def _trigger_cron(self):
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_process_pending(self):
        now = fields.Datetime.now()
        # active_test=False: credential yang diarsipkan tetap ikut diproses agar
        # antriannya ditandai Failed dengan pesan jelas, bukan menggantung.
        # Kirim Otomatis dimatikan: antrian dibiarkan pending, tidak dikirim.
        recs = self.with_context(active_test=False).search(
            [
                ("state", "=", "pending"),
                ("credential_id.econique_auto_send", "=", True),
                "|",
                ("next_attempt", "=", False),
                ("next_attempt", "<=", now),
            ],
            order="id",
            limit=CRON_BATCH,
        )
        for rec in recs:
            try:
                rec._send()
            except Exception:
                _logger.exception("Econique: error tak terduga pada transaksi %s", rec.id)
                self.env.cr.rollback()
                rec = self.browse(rec.id)
                rec._mark_retry(_("Error tak terduga, lihat log server."))
            self.env.cr.commit()
        if len(recs) == CRON_BATCH:
            self._trigger_cron()

    # ------------------------------------------------------------------ #
    # Tombol
    # ------------------------------------------------------------------ #
    def action_send_now(self):
        for rec in self.filtered(lambda r: r.state in ("pending", "failed")):
            rec._send()
        return True

    def action_reset(self):
        self.filtered(lambda r: r.state in ("failed", "skipped")).write(
            {"state": "pending", "attempts": 0, "next_attempt": False, "last_error": False}
        )
        self._trigger_cron()
        return True

    def action_skip(self):
        self.filtered(lambda r: r.state in ("pending", "failed")).write(
            {"state": "skipped", "last_error": _("Dilewati manual.")}
        )
        return True

    # ------------------------------------------------------------------ #
    # Pengiriman
    # ------------------------------------------------------------------ #
    def _send(self):
        self.ensure_one()
        if self.state in ("sent", "skipped"):
            return
        cred = self.credential_id.sudo()
        if not cred.active:
            return self._mark_failed(_("Credential Econique sudah diarsipkan."))

        try:
            payload = self._build_payload()
        except ValueError as e:
            # Data order belum lengkap (mis. pembayaran belum tercatat): coba lagi nanti.
            return self._mark_retry(str(e))
        except Exception as e:
            _logger.exception("Econique: gagal menyusun payload transaksi %s", self.id)
            return self._mark_failed(_("Gagal menyusun payload: %s") % e)
        self.request_payload = json.dumps(payload, indent=2, ensure_ascii=False)

        client = cred._econique_client()
        try:
            token = cred.econique_token or cred._econique_login(client)
            status, data, text = client.post_transaction(token, payload)
            if status == 401:
                token = cred._econique_login(client)
                status, data, text = client.post_transaction(token, payload)
        except (EconiqueNetworkError, EconiqueLoginError) as e:
            return self._mark_retry(str(e))
        except EconiqueError as e:
            return self._mark_failed(str(e))

        self.response_payload = text[:20000]
        self._handle_response(cred, status, data)

    def _handle_response(self, cred, status, data):
        code = data.get("code") or False
        message = data.get("message") or ""
        if 200 <= status < 300 and str(data.get("status", "")).lower() == "success":
            self.write(
                {
                    "state": "sent",
                    "sent_date": fields.Datetime.now(),
                    "response_code": code,
                    "remote_uuid": data.get("uuid"),
                    "total_netto": data.get("total_netto"),
                    "last_error": False,
                }
            )
            return
        error = "HTTP %s %s %s" % (status, code or "", message)
        self.response_code = code
        if status >= 500 or code in RETRYABLE_CODES:
            return self._mark_retry(error.strip())
        return self._mark_failed(error.strip())

    def _mark_retry(self, error):
        self.ensure_one()
        attempts = self.attempts + 1
        if attempts >= (self.credential_id.sudo().econique_max_attempts or 5):
            return self.write({"state": "failed", "attempts": attempts, "last_error": error})
        delay = min(2 ** attempts, 60)
        self.write(
            {
                "attempts": attempts,
                "last_error": error,
                "next_attempt": fields.Datetime.now() + timedelta(minutes=delay),
            }
        )

    def _mark_failed(self, error):
        self.ensure_one()
        self.write({"state": "failed", "attempts": self.attempts + 1, "last_error": error})

    # ------------------------------------------------------------------ #
    # Payload
    # ------------------------------------------------------------------ #
    def _tz(self, order):
        name = order.company_id.partner_id.tz or "Asia/Jakarta"
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone("Asia/Jakarta")

    @staticmethod
    def _fmt_dt(dt, tz):
        return pytz.UTC.localize(dt).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")

    def _build_payload(self):
        """Kumpulkan data order lalu serahkan ke services.union_payload.

        Override method ini bila aturan pemetaan perlu diubah.
        """
        self.ensure_one()
        order = self.order_id.sudo()
        cred = self.credential_id.sudo()
        tz = self._tz(order)

        pricelist = order.pricelist_id if "pricelist_id" in order._fields else False
        if cred.econique_price_from_pricelist and pricelist:
            price_code, price_name = str(pricelist.id), pricelist.name
        else:
            price_code = cred.econique_price_code or "STANDARD"
            price_name = cred.econique_price_name or "Standard Price"

        lines = []
        voucher_code = False
        for line in order.lines:
            product = line.product_id
            source = cred.econique_product_code_source or "default_code"
            code = (
                (product.id if source == "id" else getattr(product, source, False))
                or product.default_code
                or product.barcode
                or product.id
            )
            is_reward = bool(getattr(line, "is_reward_line", False))
            is_discount = is_reward or (line.price_unit * line.qty) < 0
            if is_discount and not voucher_code:
                coupon = getattr(line, "coupon_id", False)
                voucher_code = (coupon.code if coupon else False) or False
            lines.append(
                {
                    "product_code": code,
                    "product_name": product.display_name,
                    "price_code": price_code,
                    "price_name": price_name,
                    "qty": line.qty,
                    "unit_price": line.price_unit,
                    "discount_percent": line.discount,
                    "is_discount_line": is_discount,
                }
            )

        payments = order.payment_ids.filtered(lambda p: p.amount > 0)
        if not payments:
            raise ValueError(_("Order belum punya pembayaran."))
        pay = max(payments, key=lambda p: p.amount)
        method = pay.payment_method_id
        mapping = cred.econique_payment_map_ids.filtered(lambda m: m.payment_method_id == method)[:1]
        if mapping:
            pay_type = mapping.payment_type
            pay_provider = mapping.payment_provider or method.name
            pay_issuer = mapping.payment_issuer or cred.econique_default_issuer
        else:
            pay_type = "Cash" if method.is_cash_count else method.name
            pay_provider = method.name
            pay_issuer = cred.econique_default_issuer
        pay_date = pay.payment_date or order.date_order

        data = {
            "invoice_number": self.invoice_number or order.name,
            "transaction_date": self._fmt_dt(order.date_order, tz),
            "voucher_code": voucher_code,
            "ppn": order.amount_tax,
            "lines": lines,
            "payment": {
                "issuer": pay_issuer or "PT PHI",
                "transaction_id": (
                    getattr(pay, "transaction_id", False)
                    or pay.name
                    or order.pos_reference
                    or order.name
                ),
                "type": pay_type,
                "provider": pay_provider,
                "status": "success",
                "date": self._fmt_dt(pay_date, tz),
            },
        }
        cfg = {
            "version": cred.econique_api_version,
            "tenant_code": cred.econique_tenant_code,
            "tenant_name": cred.econique_tenant_name,
            "service_fee_percent": cred.econique_service_fee_percent,
            "send_payment_vendor": cred.econique_send_payment_vendor,
        }
        return union_payload.build_payload(data, cfg)
