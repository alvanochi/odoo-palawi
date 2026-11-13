from odoo import fields, models


class PosEconiquePaymentMap(models.Model):
    """Pemetaan metode pembayaran Odoo ke payment_type/provider/issuer Econique."""

    _name = "pos.econique.payment.map"
    _description = "Econique Payment Method Mapping"
    _order = "credential_id, id"

    credential_id = fields.Many2one(
        "pos.payment.gateway.credential", required=True, ondelete="cascade", index=True
    )
    payment_method_id = fields.Many2one(
        "pos.payment.method", string="Metode Pembayaran", required=True, ondelete="cascade"
    )
    payment_type = fields.Char(
        required=True, help="Dikirim sebagai payment_type. Contoh: Cash, QRIS, Debit."
    )
    payment_provider = fields.Char(
        help="Dikirim sebagai payment_provider. Contoh: Gopay, BCA. "
        "Bila kosong dipakai nama metode pembayaran."
    )
    payment_issuer = fields.Char(
        help="Dikirim sebagai payment_issuer. Contoh: Paper.id, doku. "
        "Bila kosong dipakai Default payment_issuer pada credential."
    )

    _sql_constraints = [
        (
            "method_uniq",
            "unique(credential_id, payment_method_id)",
            "Metode pembayaran hanya boleh dipetakan sekali per credential.",
        ),
    ]
