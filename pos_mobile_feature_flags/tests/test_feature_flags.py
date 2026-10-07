from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestMobileFeatureFlags(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({'name': 'Flag Test POS'})

    def _payload(self):
        return self.config._mobile_feature_flags_payload()

    def test_seed_and_plan_defaults(self):
        self.assertEqual(len(self.env['pos.mobile.feature'].search([])), 72)
        self.config.mobile_plan = 'lite'
        self.config.action_apply_mobile_plan()
        flags = self._payload()['flags']
        self.assertTrue(flags['cashier.split_bill'])
        self.assertFalse(flags['table.merge'])       # Medium+
        self.assertFalse(flags['delivery.tracking'])  # Enterprise only

    def test_override_and_master(self):
        self.config.mobile_plan = 'enterprise'
        self.config.action_apply_mobile_plan()
        line = self.config.mobile_flag_ids.filtered(
            lambda l: l.feature_id.key == 'cashier.split_bill')
        line.enabled = False
        self.assertFalse(self._payload()['flags']['cashier.split_bill'])
        self.assertTrue(self._payload()['flags']['cashier.void'])
        self.config.mobile_module_flag_ids.filtered(
            lambda l: l.module_id.code == 'cashier').enabled = False
        data = self._payload()
        self.assertFalse(data['modules']['module.cashier'])
        self.assertFalse(data['flags']['cashier.void'])

    def test_new_feature_propagates(self):
        module = self.env.ref('pos_mobile_feature_flags.module_cashier')
        feat = self.env['pos.mobile.feature'].create({
            'name': 'Tip', 'key': 'cashier.tip', 'module_id': module.id,
            'plan_medium': True})
        self.assertIn(feat, self.config.mobile_flag_ids.feature_id)

    def test_key_rules(self):
        module = self.env.ref('pos_mobile_feature_flags.module_cashier')
        with self.assertRaises(ValidationError):
            self.env['pos.mobile.feature'].create({
                'name': 'x', 'key': 'table.x', 'module_id': module.id})
        feat = self.env.ref('pos_mobile_feature_flags.feature_cashier_split_bill')
        with self.assertRaises(ValidationError):
            feat.key = 'cashier.split'
