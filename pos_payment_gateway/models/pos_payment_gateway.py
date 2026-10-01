import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosPaymentGateway(models.Model):
    """Master data payment gateway (Paper.id, Midtrans, Xendit, ...).

    Gateway baru cukup ditambah lewat UI; kode integrasinya mencari
    credential berdasarkan `code`.
    """

    _name = "pos.payment.gateway"
    _description = "POS Payment Gateway"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        help="Kode teknis unik, huruf kecil/angka/underscore. Contoh: paper, midtrans, xendit. "
        "Dipakai di API (?gateway=<code>) dan fallback env var <CODE>_CLIENT_ID, dst.",
    )
    sequence = fields.Integer(default=10)
    default_base_url = fields.Char(
        string="Default Base URL", help="Diisikan otomatis saat membuat credential baru."
    )
    active = fields.Boolean(default=True)
    credential_ids = fields.One2many(
        "pos.payment.gateway.credential", "gateway_id", string="Credentials"
    )
    credential_count = fields.Integer(compute="_compute_credential_count")

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Kode payment gateway harus unik."),
    ]

    @api.depends("credential_ids")
    def _compute_credential_count(self):
        for rec in self:
            rec.credential_count = len(rec.credential_ids)

    @api.constrains("code")
    def _check_code(self):
        for rec in self:
            if not re.fullmatch(r"[a-z0-9_]+", rec.code or ""):
                raise ValidationError(
                    _("Kode hanya boleh huruf kecil, angka, dan underscore (contoh: paper).")
                )

    @api.constrains("default_base_url")
    def _check_default_base_url(self):
        for rec in self:
            if rec.default_base_url and not rec.default_base_url.startswith("https://"):
                raise ValidationError(_("Default Base URL harus diawali https://"))

    def action_view_credentials(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "pos_payment_gateway.pos_payment_gateway_credential_action"
        )
        action["domain"] = [("gateway_id", "=", self.id)]
        action["context"] = {"default_gateway_id": self.id}
        return action
