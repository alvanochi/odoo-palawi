# -*- coding: utf-8 -*-
{
    'name': 'POS Order Kitchen States',
    'version': '18.0.2.1.0',
    'category': 'Point of Sale',
    'summary': 'Status memasak per hidangan pada baris POS Order '
               '(pending -> cooking -> ready -> served)',
    'description': """
POS Order Kitchen States
========================
Melacak progres dapur di tingkat BARIS pesanan, bukan di pos.order.state.

Status per baris (pos.order.line.kitchen_state):

- Pending : belum dimasak
- Cooking : sedang dimasak
- Ready   : siap diantar
- Served  : sudah diantar

Dapur multi-stasiun menyelesaikan tiap hidangan pada waktu berbeda, sehingga
satu status untuk seluruh pesanan tidak cukup: minuman bisa siap sementara
masakan panas masih dikerjakan.

pos.order.kitchen_state DITURUNKAN dari baris-barisnya dan tidak pernah
di-set langsung. Baris reward (potongan harga) dikecualikan karena bukan
makanan.

pos.order.state dibiarkan sepenuhnya bawaan Odoo. Versi 1.x menambahkan
processing/ready/delivered ke sana, dan ongkosnya mahal: pos.order.write()
bawaan menolak perpindahan state keluar dari 'paid', sehingga modul harus
mem-bypass seluruh rantai write() termasuk override modul lain, dan setiap
view atau filter Odoo yang mencari 'paid' kehilangan pesanan tersebut.
Versi 2.0.0 menghapus keduanya.

Field pendukung per baris:

- cooking_started_at : titik awal hitung mundur layar dapur
- ready_at : waktu ditandai siap
- ready_source : 'staff' (ditandai petugas) atau 'timer' (hitung mundur habis)

Hitung mundur yang habis adalah perkiraan, bukan bukti makanan sudah jadi.
Memisahkan keduanya lewat ready_source memungkinkan estimated_time diperbaiki
dari durasi masak yang sebenarnya.
""",
    'author': 'Alvano Hastagina',
    # pos_loyalty menyediakan pos.order.line.is_reward_line, yang dipakai
    # _compute_kitchen_state untuk mengecualikan baris potongan harga dari
    # status dapur. Tanpa dependensi ini modul memuat dengan baik selama
    # pos_loyalty kebetulan terpasang, lalu menggagalkan registry di database
    # yang tidak memasangnya.
    'depends': ['point_of_sale', 'pos_loyalty'],
    'data': [
        'views/pos_order_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
