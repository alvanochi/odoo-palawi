# -*- coding: utf-8 -*-
from odoo import models


class PosOrderMemberPoints(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        """Override to add member points when order is paid."""
        res = super().action_pos_order_paid()

        for order in self:
            order._add_member_points()

        return res

    def _add_member_points(self):
        """
        Add member points to partner based on member type configuration.
        
        Logic:
        - Partner must have a member_type_id
        - Membership must be active (member_active = True)
        - Order amount_total must be >= earn_value of the member type
        - Points added = floor(amount_total / earn_value) * redeem_value
        
        Example:
        - earn_value = 10,000 (Rp 10.000 untuk mendapat point)
        - redeem_value = 1 (mendapat 1 point)
        - Transaksi Rp 55.000 -> floor(55000/10000) * 1 = 5 points
        """
        self.ensure_one()
        
        partner = self.partner_id
        if not partner:
            return
        
        member_type = partner.member_type_id
        if not member_type:
            return
        
        if not partner.member_active:
            return
        
        earn_value = member_type.earn_value
        redeem_value = member_type.redeem_value
        
        if earn_value <= 0:
            return
        
        # Calculate points: floor(total / earn_value) * redeem_value
        # Only add points if transaction >= earn_value
        if self.amount_total >= earn_value:
            points_to_add = int(self.amount_total // earn_value) * redeem_value
            partner.sudo().write({
                'member_points': partner.member_points + points_to_add
            })
