# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError


class PromotionRepository:
    def __init__(self, env):
        self.env = env

    def get_active_programs_for_company(self, company):
        today = fields.Date.today()
        # 'sale_ok' is only added by the sale_loyalty module, so filtering on it
        # crashes on databases without it. These endpoints serve POS anyway.
        domain = [
            ('active', '=', True),
            ('pos_ok', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)
        ]
        programs = self.env['loyalty.program'].with_company(company).sudo().search(domain)

        # Filter by validity date range
        active_programs = []
        for program in programs:
            if program.date_from and program.date_from > today:
                continue
            if program.date_to and program.date_to < today:
                continue
            active_programs.append(program)

        return active_programs

    def _resolve_config(self, pos_config_id):
        config = self.env['pos.config'].sudo().browse(pos_config_id)
        if not config.exists():
            raise UserError(f"POS Config ID {pos_config_id} does not exist")
        return config

    def get_programs_for_pos_config(self, pos_config_id, program_types=None):
        """Programs available on a POS, straight from Odoo's own engine.

        pos.config._get_program_ids() (addons/pos_loyalty) already applies
        pos_ok, the pos_config_ids restriction, the date range, the pricelist
        restriction and max_usage, so none of that is re-implemented here.
        """
        config = self._resolve_config(pos_config_id)
        programs = config.sudo()._get_program_ids().filtered('active')
        if program_types:
            programs = programs.filtered(lambda p: p.program_type in program_types)
        return programs

    def validate_coupon_code(self, pos_config_id, code, partner_id=False, pricelist_id=False):
        """Delegate to core pos.config.use_coupon_code, which checks expiry,
        partner ownership, points, pricelist and program validity."""
        config = self._resolve_config(pos_config_id)
        result = config.sudo().use_coupon_code(
            code,
            fields.Datetime.now().isoformat(),
            partner_id or False,
            pricelist_id or False,
        )

        if not result.get('successful'):
            return {
                'valid': False,
                'code': code,
                'message': result.get('payload', {}).get('error_message', 'Invalid coupon'),
            }

        payload = result.get('payload', {})
        coupon = self.env['loyalty.card'].sudo().browse(payload.get('coupon_id'))
        program = self.env['loyalty.program'].sudo().browse(payload.get('program_id'))
        points = payload.get('points', 0.0)

        return {
            'valid': True,
            'code': code,
            'program_id': program.id,
            'program_name': program.name,
            'program_type': program.program_type,
            'coupon_id': coupon.id,
            'coupon_partner_id': payload.get('coupon_partner_id'),
            'points': points,
            'expiration_date': coupon.expiration_date.isoformat() if coupon.expiration_date else False,
            'has_source_order': payload.get('has_source_order'),
            # Only rewards the coupon actually has enough points for
            'claimable_reward_ids': [
                reward.id for reward in program.reward_ids if reward.required_points <= points
            ],
        }

    def get_rewards(self, reward_ids):
        rewards = self.env['loyalty.reward'].sudo().browse(reward_ids).exists()
        if len(rewards) != len(set(reward_ids or [])):
            raise UserError("One or more reward_id does not exist")
        return rewards
