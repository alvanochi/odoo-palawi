from odoo import fields, models


class PosEconiquePaymentMap(models.Model):
    """Maps an Odoo payment method to Econique payment_type/provider/issuer."""

    _name = "pos.econique.payment.map"
    _description = "Econique Payment Method Mapping"
    _order = "config_id, id"

    config_id = fields.Many2one(
        "pos.econique.config", required=True, ondelete="cascade", index=True
    )
    payment_method_id = fields.Many2one(
        "pos.payment.method", string="Payment Method", required=True, ondelete="cascade"
    )
    payment_type = fields.Char(
        required=True, help="Sent as payment_type. Example: Cash, QRIS, Debit."
    )
    payment_provider = fields.Char(
        help="Sent as payment_provider. Example: Gopay, BCA. "
        "When empty, the payment method name is used."
    )
    payment_issuer = fields.Char(
        help="Sent as payment_issuer. Example: Paper.id, doku. "
        "When empty, the configuration's Default payment_issuer is used."
    )

    _sql_constraints = [
        (
            "method_uniq",
            "unique(config_id, payment_method_id)",
            "A payment method can only be mapped once per configuration.",
        ),
    ]
