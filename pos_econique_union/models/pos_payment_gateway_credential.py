from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.econique_client import EconiqueClient, EconiqueError

MANAGER_GROUP = "pos_payment_gateway.group_pos_payment_gateway_manager"
GATEWAY_CODE = "econique"


class PosPaymentGatewayCredential(models.Model):
    """Pengaturan integrasi Union Kuliner Econique, disimpan di credential.

    client_id = username, client_secret = password API Econique. Field di
    bawah hanya dipakai bila gateway credential-nya `econique`.
    """

    _inherit = "pos.payment.gateway.credential"

    # --- Identitas tenant -------------------------------------------------
    econique_tenant_code = fields.Char(
        string="Tenant Code", help="Dikirim sebagai tenant_code. Contoh: TN00001."
    )
    econique_tenant_name = fields.Char(
        string="Tenant Name", help="Dikirim sebagai tenant_name. Contoh: Cafe Pubin."
    )

    # --- Pengiriman -------------------------------------------------------
    econique_auto_send = fields.Boolean(
        string="Kirim Otomatis",
        default=True,
        help="Kirim transaksi ke Econique otomatis begitu order di POS ini lunas "
        "(baik dari kasir maupun dari REST API).",
    )
    econique_api_version = fields.Char(string="API Version", default="1.0.0")
    econique_max_attempts = fields.Integer(
        string="Maks Percobaan", default=5,
        help="Setelah sebanyak ini gagal sementara (jaringan/5xx), transaksi ditandai Failed.",
    )
    econique_timeout = fields.Integer(string="Timeout (detik)", default=20)
    econique_login_basic_auth = fields.Boolean(
        string="Login pakai Basic Auth",
        default=True,
        help="Dokumentasi menyebut endpoint login memakai Basic Auth. Bila aktif, header "
        "Basic dikirim dengan username/password yang sama (override lewat Extra "
        "Parameters: basic_auth_user, basic_auth_password).",
    )

    # --- Aturan pemetaan --------------------------------------------------
    econique_invoice_source = fields.Selection(
        [("pos_reference", "POS Reference"), ("name", "Order Name")],
        string="Sumber invoice_number",
        default="pos_reference",
    )
    econique_product_code_source = fields.Selection(
        [("default_code", "Internal Reference"), ("barcode", "Barcode"), ("id", "Product ID")],
        string="Sumber product_code",
        default="default_code",
        help="Bila kosong di produk, dipakai urutan: Internal Reference, Barcode, Product ID.",
    )
    econique_price_from_pricelist = fields.Boolean(
        string="price_code dari Pricelist",
        help="Aktif: price_code = ID pricelist order, price_name = nama pricelist. "
        "Nonaktif: pakai nilai tetap di bawah.",
    )
    econique_price_code = fields.Char(string="price_code tetap", default="STANDARD")
    econique_price_name = fields.Char(string="price_name tetap", default="Standard Price")
    econique_service_fee_percent = fields.Float(
        string="Service Fee (%)", default=0.0,
        help="Persen dari (bruto - diskon). Isi 0 bila tidak ada service charge.",
    )
    econique_default_issuer = fields.Char(
        string="Default payment_issuer", default="PT PHI",
        help="Dokumentasi: untuk pembayaran tunai isi 'PT PHI'. Bisa ditimpa per metode "
        "pembayaran di tabel pemetaan.",
    )
    econique_send_payment_vendor = fields.Boolean(
        string="Kirim juga payment_vendor",
        default=True,
        help="Contoh request di dokumentasi memakai 'payment_vendor' sedangkan tabel field "
        "memakai 'payment_issuer'. Aktif: keduanya dikirim.",
    )
    econique_payment_map_ids = fields.One2many(
        "pos.econique.payment.map", "credential_id", string="Pemetaan Metode Pembayaran"
    )

    # --- Token (cache) ----------------------------------------------------
    # Tidak di-tracking dan hanya terbaca grup manager.
    econique_token = fields.Char(groups=MANAGER_GROUP, copy=False)
    econique_token_date = fields.Datetime(groups=MANAGER_GROUP, copy=False)

    @api.constrains(
        "gateway_code", "econique_auto_send", "econique_tenant_code", "econique_tenant_name"
    )
    def _check_econique_tenant(self):
        for rec in self:
            if rec.gateway_code != GATEWAY_CODE or not rec.econique_auto_send:
                continue
            if not (rec.econique_tenant_code and rec.econique_tenant_name):
                raise ValidationError(
                    _("Tenant Code dan Tenant Name wajib diisi untuk pengiriman otomatis Econique.")
                )

    def _econique_client(self):
        self.ensure_one()
        cred = self.sudo()
        params = {p.key: p.value or "" for p in cred.extra_param_ids}
        basic_auth = None
        if cred.econique_login_basic_auth:
            basic_auth = (
                params.get("basic_auth_user") or cred.client_id,
                params.get("basic_auth_password") or cred.client_secret,
            )
        return EconiqueClient(
            base_url=cred.base_url,
            username=cred.client_id,
            password=cred.client_secret,
            basic_auth=basic_auth,
            timeout=cred.econique_timeout or 20,
        )

    def _econique_login(self, client=None):
        """Login ke Econique, simpan token, dan kembalikan token-nya."""
        self.ensure_one()
        cred = self.sudo()
        client = client or cred._econique_client()
        token = client.login()
        cred.write({"econique_token": token, "econique_token_date": fields.Datetime.now()})
        return token

    def action_econique_test_login(self):
        self.ensure_one()
        if self.gateway_code != GATEWAY_CODE:
            raise ValidationError(_("Hanya untuk credential gateway Econique."))
        try:
            self._econique_login()
        except EconiqueError as e:
            kind, message, sticky = "danger", str(e), True
        else:
            kind, message, sticky = "success", _("Login berhasil, token tersimpan."), False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Test Login Econique"),
                "message": message,
                "type": kind,
                "sticky": sticky,
            },
        }
