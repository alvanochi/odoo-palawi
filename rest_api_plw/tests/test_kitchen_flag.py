# -*- coding: utf-8 -*-
"""product.is_kitchen dan efeknya pada antrean KDS -- baik lewat pos.order
maupun lewat open bill (poskas.bill).

Kasus nyata yang mendorong perubahan ini: beberapa produk yang dipesan (mis.
air mineral kemasan) tidak perlu diproses dapur, tapi ikut membuat tiket
tersangkut karena baris itu tidak akan pernah ditandai selesai oleh siapa
pun -- kitchen_state-nya diam di 'pending' selamanya dan menyeret status
seluruh order/bill.

Catatan verifikasi: database produksi ini punya banyak modul kustom lain
(pos_order_extra_states, rest_api_odoo, product_estimated_time, dll). Jika
pos.session/pos.order di instance Anda punya field wajib tambahan di luar
yang dibuat di sini, sesuaikan _session()/_order() -- prinsip yang sama
seperti catatan verifikasi di table_layout_api/tests/test_table_layout_api.py.

Test bagian bill (_BillKitchenFlagMixin) dilewati otomatis kalau modul
rest_api_odoo (pemilik poskas.bill) belum terpasang di database yang
menjalankan test -- rest_api_plw sengaja tidak depend ke situ.
"""
import unittest

from odoo.tests import TransactionCase, tagged

from ..repositories.pos_order_repository import PosOrderRepository
from ..repositories.poskas_bill_repository import PoskasBillRepository


def _product(env, name, price, is_kitchen=None):
    """is_kitchen dikontrol dari kategori produk, bukan dari produknya."""
    vals = {
        'name': name,
        'type': 'consu',
        'list_price': price,
        'available_in_pos': True,
    }
    if is_kitchen is not None:
        category = env['product.category'].create({
            'name': 'Kategori Uji (dapur=%s)' % is_kitchen,
            'is_kitchen': is_kitchen,
        })
        vals['categ_id'] = category.id
    return env['product.product'].create(vals)


@tagged('post_install', '-at_install')
class TestKitchenFlagField(TransactionCase):
    """Sifat dasar field, lepas dari jalur order atau bill."""

    def test_is_kitchen_defaults_to_true(self):
        """Upgrade tidak boleh membuat produk lama diam-diam hilang dari dapur."""
        product = _product(self.env, 'Produk Tanpa Kategori', 10000.0)
        self.assertTrue(product.is_kitchen)

    def test_product_follows_its_category(self):
        product = _product(self.env, 'Produk Ikut Kategori', 10000.0, is_kitchen=False)
        self.assertFalse(product.is_kitchen)
        product.categ_id.is_kitchen = True
        self.assertTrue(product.is_kitchen,
                        "mengubah kategori harus ikut mengubah produk di dalamnya")


@tagged('post_install', '-at_install')
class TestKitchenFlagOnPosOrder(TransactionCase):
    """Jalur pos.order: pesanan yang sudah lewat checkout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({
            'name': 'Kitchen Flag Test Shop (Order)',
            'module_pos_restaurant': False,
        })
        cls.nasi = _product(cls.env, 'Nasi Goreng Kampung', 35000.0)
        cls.air = _product(cls.env, 'Air Mineral 600ml', 8000.0, is_kitchen=False)
        cls.repo = PosOrderRepository(cls.env)

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

    def test_line_carries_the_is_kitchen_flag(self):
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 2, 8000.0)])

        payload = self.repo.find_order(order.id).to_dict()
        by_product = {line['product_id']: line for line in payload['lines']}

        self.assertTrue(by_product[self.nasi.id]['is_kitchen'])
        self.assertFalse(by_product[self.air.id]['is_kitchen'])

    def test_queue_payload_omits_non_kitchen_lines(self):
        """Antrean dapur tidak boleh memuat baris non-dapur sama sekali."""
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        queued = self.repo.find_orders(
            session_id=session.id, states=['paid'],
            kitchen_states=['pending', 'cooking', 'ready'])
        payload = queued[0].to_dict()

        self.assertEqual([line['product_id'] for line in payload['lines']], [self.nasi.id])

    def test_detail_payload_still_lists_every_line(self):
        """Detail order tetap utuh untuk struk dan rekonsiliasi."""
        session = self._session()
        order = self._order(session, [(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        payload = self.repo.find_order(order.id).to_dict()

        self.assertEqual(len(payload['lines']), 2)

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


@tagged('post_install', '-at_install')
class TestKitchenFlagOnBill(TransactionCase):
    """Jalur open bill (poskas.bill): pesanan yang belum di-checkout.

    poskas.bill dimiliki modul rest_api_odoo, yang sengaja bukan dependency
    rest_api_plw. Kalau modul itu tidak terpasang di database yang
    menjalankan test, seluruh kelas ini dilewati -- bukan gagal -- persis
    seperti perilaku PoskasBillRepository.is_available() di kode aslinya.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo = PoskasBillRepository(cls.env)
        if not cls.repo.is_available():
            raise unittest.SkipTest(
                "Module 'rest_api_odoo' (poskas.bill) is not installed")

        cls.config = cls.env['pos.config'].create({
            'name': 'Kitchen Flag Test Shop (Bill)',
            'module_pos_restaurant': False,
        })
        cls.nasi = _product(cls.env, 'Nasi Goreng Kampung (Bill)', 35000.0)
        cls.air = _product(cls.env, 'Air Mineral 600ml (Bill)', 8000.0, is_kitchen=False)

    def _bill(self, lines):
        bill = self.env['poskas.bill'].create({
            'config_id': self.config.id,
            'name_customer': 'Budi',
        })
        for product, qty, price in lines:
            self.env['poskas.bill.line'].create({
                'bill_id': bill.id,
                'product_id': product.id,
                'qty': qty,
                'price_unit': price,
            })
        bill.invalidate_recordset(['line_ids'])
        return bill

    def test_bill_line_carries_the_is_kitchen_flag(self):
        bill = self._bill([(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        payload = self.repo.find_bill(bill.id).to_dict()
        by_product = {line['product_id']: line for line in payload['lines']}

        self.assertTrue(by_product[self.nasi.id]['is_kitchen'])
        self.assertFalse(by_product[self.air.id]['is_kitchen'])

    def test_bill_kitchen_state_ignores_non_kitchen_lines(self):
        bill = self._bill([(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        nasi_line = bill.line_ids.filtered(lambda l: l.product_id == self.nasi)
        nasi_line.set_kitchen_state('cooking')
        nasi_line.set_kitchen_state('ready')
        nasi_line.set_kitchen_state('served')

        payload = self.repo.find_bill(bill.id).to_dict()

        self.assertEqual(payload['kitchen_state'], 'served',
                         "air mineral yang masih 'pending' tidak boleh menahan status bill")

    def test_bill_of_only_non_kitchen_items_is_not_queued(self):
        self._bill([(self.air, 2, 8000.0)])

        bills = self.repo.find_bills(
            pos_config_id=self.config.id,
            kitchen_states=['pending', 'cooking', 'ready'])

        self.assertEqual(bills, [])

    def test_bill_with_at_least_one_kitchen_item_is_still_queued(self):
        bill = self._bill([(self.nasi, 1, 35000.0), (self.air, 1, 8000.0)])

        bills = self.repo.find_bills(
            pos_config_id=self.config.id,
            kitchen_states=['pending', 'cooking', 'ready'])

        self.assertEqual([b.id for b in bills], [bill.id])
