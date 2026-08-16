from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestProfitSharing(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Test Recipient"})
        self.share_type = self.env.ref("profit_sharing.profit_share_type_mitra")

    def test_flat_exact_scope_uses_highest_priority_rule(self):
        common = {
            "share_type_id": self.share_type.id,
            "recipient_id": self.partner.id,
            "company_id": self.env.company.id,
            "computation_type": "flat",
            "source_type": "pos_revenue",
            "period_type": "monthly",
            "date_start": date(2026, 8, 1),
            "state": "confirmed",
        }
        high = self.env["profit.share.rule"].sudo().create(
            {**common, "name": "High Priority", "priority": 20, "flat_amount": 1000000.0}
        )
        self.env["profit.share.rule"].sudo().create(
            {**common, "name": "Low Priority", "priority": 10, "flat_amount": 500000.0}
        )

        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "monthly",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()

        self.assertEqual(len(batch.line_ids), 1)
        self.assertEqual(batch.line_ids.rule_id, high)
        self.assertEqual(batch.line_ids.share_amount, 1000000.0)
        self.assertEqual(batch.line_ids.payment_state, "unpaid")

    def test_flat_rule_keeps_base_as_reference_only(self):
        rule = self.env["profit.share.rule"].sudo().create(
            {
                "name": "Flat Staff Example",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 2000000.0,
                "source_type": "net_profit",
                "period_type": "monthly",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "monthly",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()
        line = batch.line_ids.filtered(lambda item: item.rule_id == rule)
        self.assertTrue(line)
        self.assertEqual(line.share_amount, 2000000.0)
        self.assertEqual(line.flat_amount_applied, 2000000.0)

    def test_floor_zero_applies_only_to_net_profit(self):
        # POS revenue can legitimately become negative after refunds. The "negative net profit"
        # policy must not silently change POS revenue semantics.
        rule = self.env["profit.share.rule"].sudo().create(
            {
                "name": "Negative POS Revenue",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "percentage",
                "percentage": 10.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        self.env["ir.config_parameter"].sudo().set_param("profit_sharing.negative_share_policy", "floor_zero")
        original = type(rule)._compute_base_amount
        try:
            type(rule)._compute_base_amount = lambda rec, date_from, date_to: -100000.0
            batch.sudo().action_recompute()
        finally:
            type(rule)._compute_base_amount = original
        line = batch.line_ids.filtered(lambda item: item.rule_id == rule)
        self.assertEqual(line.share_amount, -10000.0)

    def test_snapshot_names_are_captured(self):
        rule = self.env["profit.share.rule"].sudo().create(
            {
                "name": "Snapshot Rule",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 500000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()
        line = batch.line_ids.filtered(lambda item: item.rule_id == rule)
        self.assertEqual(line.rule_name, "Snapshot Rule")
        self.assertEqual(line.recipient_name, "Test Recipient")
        self.assertEqual(line.share_type_name, self.share_type.display_name)

    def test_rule_change_requires_recompute_before_confirm(self):
        rule = self.env["profit.share.rule"].sudo().create(
            {
                "name": "Rule Change Guard",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 100000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()
        rule.sudo().write({"flat_amount": 200000.0})
        with self.assertRaises(UserError):
            batch.sudo().action_confirm()

    def test_period_change_clears_stale_draft_lines(self):
        self.env["profit.share.rule"].sudo().create(
            {
                "name": "Period Guard",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 100000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()
        self.assertTrue(batch.line_ids)
        batch.sudo().write({"date_to": date(2026, 8, 30)})
        self.assertFalse(batch.line_ids)
        self.assertFalse(batch.rule_set_token)

    def test_batch_with_paid_line_cannot_be_cancelled(self):
        self.env["profit.share.rule"].sudo().create(
            {
                "name": "Cancellation Guard",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 100000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 8, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
            }
        )
        batch.sudo().action_recompute()
        batch.sudo().action_confirm()
        batch.line_ids[:1].sudo().action_mark_paid()
        with self.assertRaises(UserError):
            batch.sudo().action_cancel()


    def test_cancelled_batch_is_preserved_and_correction_gets_new_revision(self):
        self.env["profit.share.rule"].sudo().create(
            {
                "name": "Correction Audit Rule",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 150000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 9, 1),
                "state": "confirmed",
            }
        )
        values = {
            "company_id": self.env.company.id,
            "period_type": "custom",
            "date_from": date(2026, 9, 1),
            "date_to": date(2026, 9, 30),
        }
        original = self.env["profit.share.computation"].sudo().create(values)
        original.sudo().action_recompute()
        original.sudo().action_confirm()
        original_line_ids = original.line_ids.ids
        original.sudo().action_cancel()

        self.assertEqual(original.state, "cancelled")
        self.assertEqual(original.revision, 1)
        self.assertEqual(original.line_ids.ids, original_line_ids)

        correction = self.env["profit.share.computation"].sudo().create(values)
        self.assertEqual(correction.revision, 2)
        self.assertEqual(original.line_ids.ids, original_line_ids)

        with self.assertRaises(ValidationError):
            self.env["profit.share.computation"].sudo().create(values)

    def test_individual_payment_keeps_actual_payment_actor(self):
        self.env["profit.share.rule"].sudo().create(
            {
                "name": "Payment Actor Rule",
                "share_type_id": self.share_type.id,
                "recipient_id": self.partner.id,
                "company_id": self.env.company.id,
                "computation_type": "flat",
                "flat_amount": 100000.0,
                "source_type": "pos_revenue",
                "period_type": "custom",
                "date_start": date(2026, 10, 1),
                "state": "confirmed",
            }
        )
        batch = self.env["profit.share.computation"].sudo().create(
            {
                "company_id": self.env.company.id,
                "period_type": "custom",
                "date_from": date(2026, 10, 1),
                "date_to": date(2026, 10, 31),
            }
        )
        batch.sudo().action_recompute()
        batch.sudo().action_confirm()

        payment_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Profit Share Payment Tester",
                "login": "profit_share_payment_tester",
                "groups_id": [(6, 0, [self.env.ref("profit_sharing.group_profit_share_payment").id])],
                "company_id": self.env.company.id,
                "company_ids": [(6, 0, [self.env.company.id])],
            }
        )
        batch.line_ids.with_user(payment_user).action_mark_paid()
        self.assertEqual(batch.state, "paid")
        self.assertEqual(batch.paid_by_id, payment_user)
