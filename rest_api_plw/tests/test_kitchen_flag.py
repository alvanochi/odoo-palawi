# -*- coding: utf-8 -*-
"""product.is_kitchen dan efeknya pada antrean KDS.

Kasus nyata yang mendorong perubahan ini: beberapa produk yang dipesan (mis.
air mineral kemasan) tidak perlu diproses dapur, tapi ikut membuat tiket
tersangkut karena baris itu tidak akan pernah ditandai selesai oleh siapa
pun -- kitchen_state-nya diam di 'pending' selamanya dan menyeret status
seluruh order.

Catatan verifikasi: database produksi ini punya banyak modul kustom lain
(pos_order_extra_states, product_estimated_time, dll). Jika pos.session/
pos.order di instance Anda punya field wajib tambahan di luar yang dibuat
di sini, sesuaikan _open_session()/_create_order() -- prinsip yang sama
seperti catatan verifikasi di table_layout_api/tests/test_table_layout_api.py.
"""
from odoo.tests import TransactionCase, tagged

from ..repositories.pos_order_repository import PosOrderRepository


@tagged('post_install', '-at_install')
class TestKitchenFlag(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({
            'name': 'Kitchen Flag Test Shop',
            'module_pos_restaurant': False,
        })
        cls.nasi = cls._product('Nasi Goreng Kampung', 35000.0)
        cls.air = cls._product('Air Mineral 600ml', 8000.0, is_kitchen=False)
        cls.repo = PosOrderRepository(cls.env)

    @classmethod
    def _product(cls, name, price, is_kitchen=None):
        vals = {
            'name': name,
            'type': 'consu',
            'list_price': price,
            'available_in_pos': True,
        }
        if is_kitchen is not None:
            vals['is_kitchen'] = is_kitchen
        return cls.env['product.product'].create(vals)

    def _session(self):
        session = self.env['pos.session'].create({
            'config_id': self.config.id,
            'user_id': self.env.uid,
        })
        # Wizard cash control tidak ada hubungannya dengan pengujian ini.
        session.write({'state': 'opened'})
        return session

    def _order(self, session, lines):
        order = self.env['pos.order'].create({
            'company_id': self.env.company.id,
            'session_id': session.id,
            'amount_tax': 0.0,
            'amount_total': sum(price * qty for _p, qty, price in lines),
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'state': 'paid',
        })
        for product, qty, price in lines:
            self.env['pos.order.line'].create({
                'order_id': order.id,
                'product_id': product.id,
                'qty': qty,
                'price_unit': price,
                'price_subtotal': price * qty,
                'price_subtotal_incl': price * qty,
            })
        return order

    # -- field --------------------------------------------------------------

    def test_is_kitchen_defaults_to_true(self):
        """Upgrade tidak boleh membuat produk lama diam-diam hilang dari dapur."""
        product = self._product('Produk Tanpa Nilai Eksplisit', 10000.0)
        self.assertTrue(product.is_kitchen)

    # -- flag per baris -------------------------------------------------------

    def test_line_carries_the_is_kitchen_flag(self):
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 2, 8000.0)])

        payload = self.repo.find_order(order.id).to_dict()
        by_product = {line['product_id']: line for line in payload['lines']}

        self.assertTrue(by_product[self.nasi.id]['is_kitchen'])
        self.assertFalse(by_product[self.air.id]['is_kitchen'])

    # -- ringkasan status dapur -----------------------------------------------

    def test_order_kitchen_state_ignores_non_kitchen_lines(self):
        """Air mineral yang tidak pernah disentuh dapur tidak boleh menyeret
        seluruh tiket tetap terlihat 'pending' setelah makanannya selesai."""
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        nasi_line = order.lines.filtered(lambda l: l.product_id == self.nasi)
        nasi_line.set_kitchen_state('cooking')
        nasi_line.set_kitchen_state('ready')
        nasi_line.set_kitchen_state('served')

        payload = self.repo.find_order(order.id).to_dict()

        self.assertEqual(payload['kitchen_state'], 'served',
                         "air mineral yang masih 'pending' tidak boleh menahan status")

    def test_order_with_only_non_kitchen_lines_has_no_kitchen_state(self):
        session = self._session()
        order = self._order(session, [(self.air, 3, 8000.0)])

        payload = self.repo.find_order(order.id).to_dict()

        self.assertIsNone(payload['kitchen_state'])

    # -- antrean KDS ------------------------------------------------------

    def test_order_of_only_non_kitchen_items_is_not_queued(self):
        """Pesanan yang isinya cuma air mineral tidak boleh muncul sebagai
        tiket kosong di layar dapur."""
        session = self._session()
        self._order(session, [(self.air, 2, 8000.0)])

        orders = self.repo.find_orders(
            session_id=session.id, states=['paid'],
            kitchen_states=['pending', 'cooking', 'ready'])

        self.assertEqual(orders, [])

    def test_order_with_at_least_one_kitchen_item_is_still_queued(self):
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        orders = self.repo.find_orders(
            session_id=session.id, states=['paid'],
            kitchen_states=['pending', 'cooking', 'ready'])

        self.assertEqual([o.id for o in orders], [order.id])
