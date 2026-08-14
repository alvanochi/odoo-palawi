# -*- coding: utf-8 -*-
"""Hitung ulang field turunan setelah migrasi status dapur.

pre-migrate 2.0.0 menulis pos_order_line.kitchen_state lewat SQL mentah,
karena pada tahap itu definisi model baru belum dimuat. Konsekuensinya
pos.order.kitchen_state dan pos.order.processing_started_at -- keduanya
computed + stored -- tidak ikut terpicu, sehingga pesanan yang seluruh
hidangannya sudah 'served' tetap terbaca 'pending' di level order.

Skrip ini berjalan setelah registry siap, jadi ORM bisa diminta menghitung
ulang keduanya.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['pos.order'].sudo().search([])
    if not orders:
        return

    for field_name in ('kitchen_state', 'processing_started_at'):
        field = orders._fields.get(field_name)
        if field:
            env.add_to_compute(field, orders)

    env.flush_all()
    _logger.info(
        "pos_order_extra_states: field turunan dihitung ulang untuk %s pesanan",
        len(orders),
    )
