import hashlib
import json

from odoo import api, fields, models

from .pos_mobile_feature import PLANS


class PosConfig(models.Model):
    _inherit = 'pos.config'

    mobile_plan = fields.Selection(
        PLANS, string='Mobile Plan', default='medium', required=True,
        help="Default feature set for the Android app. Use 'Apply Plan Defaults' to reset "
             "the flags below to this plan, then toggle individual flags as needed.")
    mobile_module_flag_ids = fields.One2many(
        'pos.mobile.config.module', 'config_id', string='Mobile Master Flags')
    mobile_flag_ids = fields.One2many(
        'pos.mobile.config.flag', 'config_id', string='Mobile Feature Flags')

    # ------------------------------------------------------------------ lines
    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        configs._mobile_sync_flag_lines()
        return configs

    def _mobile_sync_flag_lines(self):
        """Create the missing flag lines (plan default) for every active module/feature."""
        Module = self.env['pos.mobile.config.module'].sudo()
        Flag = self.env['pos.mobile.config.flag'].sudo()
        modules = self.env['pos.mobile.module'].sudo().search([])
        features = self.env['pos.mobile.feature'].sudo().search([])
        for config in self.sudo():
            have_m = set(config.mobile_module_flag_ids.module_id.ids)
            have_f = set(config.mobile_flag_ids.feature_id.ids)
            Module.create([
                {'config_id': config.id, 'module_id': m.id, 'enabled': True}
                for m in modules if m.id not in have_m])
            Flag.create([
                {'config_id': config.id, 'feature_id': f.id,
                 'enabled': f.default_for_plan(config.mobile_plan)}
                for f in features if f.id not in have_f])

    def action_apply_mobile_plan(self):
        """Reset every flag of the POS to the defaults of the selected plan."""
        self._mobile_sync_flag_lines()
        for config in self.sudo():
            config.mobile_module_flag_ids.write({'enabled': True})
            for line in config.mobile_flag_ids:
                line.enabled = line.feature_id.default_for_plan(config.mobile_plan)
        return True

    # -------------------------------------------------------------------- API
    def _mobile_feature_flags_payload(self, detail=False):
        """Effective flags = master(module) AND feature."""
        self.ensure_one()
        config = self.sudo()
        config._mobile_sync_flag_lines()
        modules = {
            l.module_id.id: l.enabled for l in config.mobile_module_flag_ids}
        flags, master, items = {}, {}, []
        for line in config.mobile_flag_ids.filtered(
                lambda l: l.feature_id.active and l.module_id.active):
            module = line.module_id
            module_on = modules.get(module.id, True)
            master[module.master_key] = module_on
            effective = bool(module_on and line.enabled)
            flags[line.feature_id.key] = effective
            if detail:
                items.append({
                    'key': line.feature_id.key,
                    'name': line.feature_id.name,
                    'module': module.code,
                    'enabled': line.enabled,
                    'effective': effective,
                    'android_status': line.feature_id.android_status,
                })
        data = {
            'pos_config_id': config.id,
            'pos_config_name': config.name,
            'plan': config.mobile_plan,
            'modules': master,
            'flags': flags,
        }
        data['version'] = hashlib.sha1(
            json.dumps([master, flags], sort_keys=True).encode()).hexdigest()[:16]
        if detail:
            data['features'] = items
        return data
