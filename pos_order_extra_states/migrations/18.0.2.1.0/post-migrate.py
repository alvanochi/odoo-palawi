# -*- coding: utf-8 -*-
"""Pindahkan status dapur sepenuhnya ke baris pesanan.

Versi 2.1.0 membuang dua field turunan di pos.order:

- kitchen_state       : informasinya sudah ada di baris, dan menyimpan salinan
                        turunan berarti ada dua tempat yang bisa berbeda isi
- processing_started_at : hanya min() dari cooking_started_at baris, jadi API
                        bisa menghitungnya sendiri tanpa kolom di database

Odoo tidak menghapus kolom milik field yang dibuang, jadi keduanya dibersihkan
di sini agar tabel pos_order tidak menyimpan data yatim.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Baris reward tidak dimasak siapa pun. Selama masih 'pending', pesanan
    # berpromo akan cocok dengan domain antrean dapur selamanya.
    cr.execute("""
        UPDATE pos_order_line
           SET kitchen_state = 'served'
         WHERE is_reward_line IS TRUE
           AND kitchen_state != 'served'
    """)
    _logger.info(
        "pos_order_extra_states: %s baris reward ditandai 'served'", cr.rowcount)

    for column in ('kitchen_state', 'processing_started_at'):
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'pos_order' AND column_name = %s
        """, (column,))
        if cr.fetchone():
            cr.execute('ALTER TABLE pos_order DROP COLUMN "%s"' % column)
            _logger.info(
                "pos_order_extra_states: kolom pos_order.%s dihapus", column)
