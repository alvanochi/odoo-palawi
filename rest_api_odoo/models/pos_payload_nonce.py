# -*- coding: utf-8 -*-
from odoo import fields, models


class PosPayloadNonce(models.Model):
    """IV amplop terenkripsi yang sudah dipakai (anti-replay /api/pos/v2/*).

    Satu amplop hanya boleh diproses sekali. Baris yang lebih tua dari jendela
    waktu tidak perlu disimpan karena amplopnya toh sudah ditolak karena
    kedaluwarsa; lihat services/payload_crypto.py.
    """
    _name = "pos.payload.nonce"
    _description = "Used POS encrypted payload nonce"

    iv = fields.Char(required=True, index=True)
    ts = fields.Datetime(required=True, index=True, default=fields.Datetime.now)

    _sql_constraints = [
        ("iv_unique", "unique(iv)", "Encrypted payload already used."),
    ]
