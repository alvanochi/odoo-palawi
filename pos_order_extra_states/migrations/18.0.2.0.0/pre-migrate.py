# -*- coding: utf-8 -*-
"""Kembalikan pesanan dari state dapur lama ke 'paid'.

Versi 2.0.0 menghapus state custom di pos.order (processing/ready/delivered).
Progres dapur pindah sepenuhnya ke pos.order.line.kitchen_state.

Skrip ini berjalan SEBELUM definisi model baru dimuat, selagi nilai selection
lama masih sah. Tanpa ini, baris yang masih memegang nilai lama akan menjadi
nilai yatim yang tidak dikenali oleh field mana pun.

'paid' adalah tujuan yang benar: pesanan tersebut sudah dibayar dan belum
diposting. Saat sesinya ditutup, Odoo memindahkannya ke 'done' seperti biasa.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_STATES = ('processing', 'ready', 'delivered')


def migrate(cr, version):
    if not version:
        return

    # 1. Tandai baris SEBELUM state order diubah, selagi masih bisa dibedakan
    #    mana yang sudah selesai diantar dan mana yang masih dikerjakan.
    #
    #    'delivered' berarti seluruh pesanan sudah sampai ke pelanggan, dan
    #    'done'/'invoiced' adalah riwayat yang sudah diposting. Keduanya aman
    #    ditandai served supaya tidak muncul kembali sebagai antrean dapur.
    cr.execute("""
        UPDATE pos_order_line l
           SET kitchen_state = 'served'
          FROM pos_order o
         WHERE l.order_id = o.id
           AND o.state IN ('delivered', 'done', 'invoiced')
           AND l.kitchen_state = 'pending'
    """)
    _logger.info(
        "pos_order_extra_states: %s baris dari pesanan selesai ditandai 'served'",
        cr.rowcount,
    )

    # 2. Pesanan yang masih 'processing'/'ready' sengaja TIDAK ditebak per
    #    baris: tidak ada catatan hidangan mana yang sudah jadi, dan menebaknya
    #    berarti mengarang data. Barisnya dibiarkan 'pending' agar dapur
    #    menandainya ulang -- lebih baik menandai dua kali daripada menyatakan
    #    makanan sudah siap padahal belum.
    cr.execute(
        "UPDATE pos_order SET state = 'paid' WHERE state IN %s RETURNING id",
        (OLD_STATES,),
    )
    migrated = cr.fetchall()
    if migrated:
        _logger.info(
            "pos_order_extra_states: %s pesanan dikembalikan dari state dapur "
            "lama ke 'paid': %s",
            len(migrated), [row[0] for row in migrated],
        )
