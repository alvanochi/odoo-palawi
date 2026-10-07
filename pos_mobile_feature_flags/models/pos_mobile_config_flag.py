from odoo import api, fields, models


class PosMobileConfigModule(models.Model):
    _name = 'pos.mobile.config.module'
    _description = 'POS Mobile Master Flag per POS'
    _order = 'config_id, module_sequence, id'

    config_id = fields.Many2one('pos.config', required=True, ondelete='cascade', index=True)
    module_id = fields.Many2one('pos.mobile.module', required=True, ondelete='cascade')
    module_sequence = fields.Integer(related='module_id.sequence', store=True)
    master_key = fields.Char(related='module_id.master_key')
    enabled = fields.Boolean(default=True)

    _sql_constraints = [
        ('config_module_uniq', 'unique(config_id, module_id)',
         'Only one master flag per module and POS.'),
    ]


class PosMobileConfigFlag(models.Model):
    _name = 'pos.mobile.config.flag'
    _description = 'POS Mobile Feature Flag per POS'
    _order = 'config_id, module_sequence, feature_sequence, id'

    config_id = fields.Many2one('pos.config', required=True, ondelete='cascade', index=True)
    feature_id = fields.Many2one('pos.mobile.feature', required=True, ondelete='cascade')
    module_id = fields.Many2one(related='feature_id.module_id', store=True, index=True)
    module_sequence = fields.Integer(related='feature_id.module_id.sequence', store=True)
    feature_sequence = fields.Integer(related='feature_id.sequence', store=True)
    key = fields.Char(related='feature_id.key')
    android_status = fields.Selection(related='feature_id.android_status')
    enabled = fields.Boolean(default=True)
    default_enabled = fields.Boolean(
        compute='_compute_default_enabled', string='Plan Default')
    overridden = fields.Boolean(compute='_compute_default_enabled', string='Overridden')

    _sql_constraints = [
        ('config_feature_uniq', 'unique(config_id, feature_id)',
         'Only one flag per feature and POS.'),
    ]

    @api.depends('config_id.mobile_plan', 'feature_id', 'enabled')
    def _compute_default_enabled(self):
        for rec in self:
            default = rec.feature_id.default_for_plan(rec.config_id.mobile_plan)
            rec.default_enabled = default
            rec.overridden = default != rec.enabled
