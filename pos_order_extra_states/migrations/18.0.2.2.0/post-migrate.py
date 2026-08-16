# -*- coding: utf-8 -*-
"""Normalisasi baris lama setelah realtime KDS ditambahkan."""
import logging
import uuid

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE pos_order_line
           SET kitchen_state = CASE
               WHEN is_reward_line IS TRUE THEN 'served'
               ELSE 'pending'
           END
         WHERE kitchen_state IS NULL
    """)
    _logger.info(
        "pos_order_extra_states: %s kitchen state kosong dinormalisasi",
        cr.rowcount,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    configs = env['pos.config'].sudo().search([
        ('kds_realtime_token', '=', False),
    ])
    for config in configs:
        config.kds_realtime_token = uuid.uuid4().hex
    _logger.info(
        "pos_order_extra_states: %s token realtime KDS dibuat", len(configs))
