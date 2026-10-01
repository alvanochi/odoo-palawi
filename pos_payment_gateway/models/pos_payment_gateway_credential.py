import os

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MANAGER_GROUP = "pos_payment_gateway.group_pos_payment_gateway_manager"


def _normalize_url(url):
    return (url or "").strip().rstrip("/")


class PosPaymentGatewayCredential(models.Model):
    _name = "pos.payment.gateway.credential"
    _description = "POS Payment Gateway Credential"
    _inherit = ["mail.thread"]
    _order = "pos_config_id, gateway_id, id"

    gateway_id = fields.Many2one(
        "pos.payment.gateway",
        string="Payment Gateway",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    gateway_code = fields.Char(related="gateway_id.code", store=True)
    pos_config_id = fields.Many2one(
        "pos.config",
        string="POS Config",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        related="pos_config_id.company_id", store=True, readonly=True
    )
    base_url = fields.Char(
        string="Base URL",
        compute="_compute_base_url",
        store=True,
        readonly=False,
        precompute=True,
        required=True,
        tracking=True,
    )
    client_id = fields.Char(string="Client ID / Key", required=True, tracking=True)
    # Sengaja TIDAK di-tracking supaya nilai secret tidak masuk chatter/log.
    client_secret = fields.Char(
        string="Client Secret", required=True, groups=MANAGER_GROUP, copy=False
    )
    extra_param_ids = fields.One2many(
        "pos.payment.gateway.credential.param",
        "credential_id",
        string="Extra Parameters",
        copy=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    note = fields.Text()

    # ------------------------------------------------------------------ #
    # Compute / display / normalisasi
    # ------------------------------------------------------------------ #
    @api.depends("gateway_id")
    def _compute_base_url(self):
        for rec in self:
            if rec.gateway_id.default_base_url:
                rec.base_url = _normalize_url(rec.gateway_id.default_base_url)
            else:
                rec.base_url = rec.base_url or False

    @api.depends("gateway_id", "pos_config_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s - %s" % (
                rec.gateway_id.name or "",
                rec.pos_config_id.display_name or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("base_url"):
                vals["base_url"] = _normalize_url(vals["base_url"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("base_url"):
            vals["base_url"] = _normalize_url(vals["base_url"])
        res = super().write(vals)
        if "client_secret" in vals:
            for rec in self:
                rec.message_post(body=_("Client secret diperbarui."))
        return res

    # ------------------------------------------------------------------ #
    # Constraints
    # ------------------------------------------------------------------ #
    @api.constrains("base_url")
    def _check_base_url(self):
        for rec in self:
            if not (rec.base_url or "").startswith("https://"):
                raise ValidationError(_("Base URL harus diawali https://"))

    @api.constrains("pos_config_id", "gateway_id", "active")
    def _check_unique_active(self):
        for rec in self.filtered("active"):
            dup = self.sudo().search_count(
                [
                    ("id", "!=", rec.id),
                    ("pos_config_id", "=", rec.pos_config_id.id),
                    ("gateway_id", "=", rec.gateway_id.id),
                    ("active", "=", True),
                ]
            )
            if dup:
                raise ValidationError(
                    _(
                        "POS config %(pos)s sudah punya credential %(gw)s yang aktif.",
                        pos=rec.pos_config_id.display_name,
                        gw=rec.gateway_id.name,
                    )
                )

    def init(self):
        # Pengaman di level DB: 1 credential aktif per (POS config, gateway).
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS pos_pg_credential_active_uniq
            ON pos_payment_gateway_credential (pos_config_id, gateway_id)
            WHERE active
            """
        )

    # ------------------------------------------------------------------ #
    # Helper
    # ------------------------------------------------------------------ #
    def _to_api_dict(self):
        self.ensure_one()
        return {
            "gateway": self.gateway_id.code,
            "gateway_name": self.gateway_id.name,
            "pos_config_id": self.pos_config_id.id,
            "pos_config_name": self.pos_config_id.name,
            "base_url": self.base_url,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "extra_params": {p.key: p.value or "" for p in self.extra_param_ids},
            "write_date": fields.Datetime.to_string(self.write_date),
        }

    @api.model
    def get_credential(self, pos_config_id, gateway_code, fallback_env=True):
        """Ambil credential gateway untuk sebuah POS config (backend only).

        Berjalan dengan sudo: JANGAN kirim hasilnya ke browser / frontend POS.

        Fallback env var (masa transisi): <CODE>_BASE_URL, <CODE>_CLIENT_ID,
        <CODE>_CLIENT_SECRET, contoh PAPER_CLIENT_ID untuk gateway 'paper'.

        :return: dict atau None
        """
        cred = self.sudo().search(
            [
                ("pos_config_id", "=", int(pos_config_id)),
                ("gateway_code", "=", gateway_code),
            ],
            limit=1,
        )
        if cred:
            res = cred._to_api_dict()
            res["source"] = "database"
            return res

        if fallback_env:
            prefix = (gateway_code or "").upper()
            client_id = os.environ.get(f"{prefix}_CLIENT_ID")
            client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET")
            if client_id and client_secret:
                gateway = self.env["pos.payment.gateway"].sudo().search(
                    [("code", "=", gateway_code)], limit=1
                )
                return {
                    "gateway": gateway_code,
                    "gateway_name": gateway.name or gateway_code,
                    "pos_config_id": int(pos_config_id),
                    "base_url": _normalize_url(
                        os.environ.get(f"{prefix}_BASE_URL") or gateway.default_base_url
                    ),
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "extra_params": {},
                    "source": "env",
                }
        return None


class PosPaymentGatewayCredentialParam(models.Model):
    """Parameter tambahan per gateway (mis. webhook token, merchant code)."""

    _name = "pos.payment.gateway.credential.param"
    _description = "POS Payment Gateway Credential Extra Parameter"
    _order = "credential_id, id"

    credential_id = fields.Many2one(
        "pos.payment.gateway.credential", required=True, ondelete="cascade", index=True
    )
    key = fields.Char(required=True)
    value = fields.Char()

    _sql_constraints = [
        ("key_uniq", "unique(credential_id, key)", "Key parameter harus unik per credential."),
    ]
