# -*- coding: utf-8 -*-
from odoo import models, fields

class PosOrderPaymentEvidence(models.Model):
    _name = 'pos.order.payment.evidence'
    _description = 'Payment Gateway Transaction Evidence'
    _order = 'create_date desc'

    order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        required=True,
        ondelete='cascade',
        index=True
    )
    payload = fields.Text(string='Raw Response Payload')
