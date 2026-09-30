# -*- coding: utf-8 -*-
import base64
from odoo.tests import TransactionCase, tagged
from ..repositories.pos_order_repository import PosOrderRepository
from ..domain.use_cases.save_order_evidence import SaveOrderEvidenceUseCase


@tagged('post_install', '-at_install')
class TestPosOrderEvidence(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({
            'name': 'Evidence Test Shop',
            'module_pos_restaurant': False,
        })
        cls.session = cls.env['pos.session'].create({
            'config_id': cls.config.id,
            'user_id': cls.env.uid,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Coffee',
            'type': 'consu',
            'list_price': 25000.0,
            'available_in_pos': True,
        })

    def _create_pos_order(self, state='draft'):
        return self.env['pos.order'].create({
            'session_id': self.session.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 25000.0,
                'price_subtotal': 25000.0,
                'price_subtotal_incl': 25000.0,
            })],
            'amount_total': 25000.0,
            'amount_tax': 0.0,
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'state': state,
        })

    def test_evidence_field_on_pos_order(self):
        """Field evidence exists on pos.order and stores binary data."""
        order = self._create_pos_order()
        sample_img = base64.b64encode(b"fake-image-bytes").decode('utf-8')
        order.write({'evidence': sample_img})
        self.assertTrue(bool(order.evidence))

    def test_save_evidence_and_mark_paid_repo(self):
        """Repository saves evidence and transitions order to 'paid'."""
        order = self._create_pos_order(state='draft')
        self.assertEqual(order.state, 'draft')

        sample_img = base64.b64encode(b"photo-evidence").decode('utf-8')
        repo = PosOrderRepository(self.env)
        updated_order = repo.save_evidence_and_mark_paid(order.id, sample_img)

        self.assertEqual(updated_order.state, 'paid')
        self.assertTrue(bool(updated_order.evidence))

    def test_save_order_evidence_use_case(self):
        """Use case validates input and executes repository successfully."""
        order = self._create_pos_order(state='draft')
        repo = PosOrderRepository(self.env)
        use_case = SaveOrderEvidenceUseCase(repo)

        # Missing order_id
        res_no_id = use_case.execute(order_id=None, evidence_data="base64")
        self.assertFalse(res_no_id['success'])
        self.assertEqual(res_no_id['status'], 400)

        # Missing evidence
        res_no_ev = use_case.execute(order_id=order.id, evidence_data="")
        self.assertFalse(res_no_ev['success'])
        self.assertEqual(res_no_ev['status'], 400)

        # Success execution
        sample_img = base64.b64encode(b"photo-evidence-success").decode('utf-8')
        res_success = use_case.execute(order_id=order.id, evidence_data=sample_img)
        self.assertTrue(res_success['success'])
        self.assertEqual(res_success['data']['state'], 'paid')
        self.assertEqual(res_success['data']['pos_order_id'], order.id)
        self.assertEqual(order.state, 'paid')

    def test_compress_image_bytes(self):
        """Image compression should ensure file size is within 1MB."""
        import io
        from PIL import Image
        from ..controllers.utils import compress_image_bytes

        # Small image (less than 1MB) remains untouched
        small_img = Image.new('RGB', (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        small_img.save(buf, format='JPEG')
        small_bytes = buf.getvalue()
        self.assertLessEqual(len(compress_image_bytes(small_bytes)), 1024 * 1024)
