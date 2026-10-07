import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

PLANS = [('lite', 'Lite'), ('medium', 'Medium'), ('enterprise', 'Enterprise')]


class PosMobileFeature(models.Model):
    _name = 'pos.mobile.feature'
    _description = 'POS Mobile Feature'
    _order = 'module_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    key = fields.Char(
        string='Feature Key', required=True, index=True,
        help="Format <module>.<feature>, lowercase snake_case, e.g. 'cashier.split_bill'. "
             "Stable once released: archive a feature instead of reusing its key.")
    module_id = fields.Many2one(
        'pos.mobile.module', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    android_status = fields.Selection([
        ('done', 'Done'),
        ('partial', 'Partial'),
        ('planned', 'Planned'),
        ('backoffice', 'Back Office'),
        ('known_issue', 'Known Issue'),
    ], default='planned', string='Android Status')
    plan_lite = fields.Boolean(string='Lite')
    plan_medium = fields.Boolean(string='Medium')
    plan_enterprise = fields.Boolean(string='Enterprise')
    note = fields.Char()
    active = fields.Boolean(default=True, help="Archive = deprecated; not sent to the app.")

    _sql_constraints = [
        ('key_uniq', 'unique(key)', 'Feature key must be unique.'),
    ]

    @api.constrains('key', 'module_id')
    def _check_key(self):
        for rec in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*', rec.key or ''):
                raise ValidationError(
                    "Feature key must look like '<module>.<feature>' in lowercase snake_case.")
            if rec.key.split('.', 1)[0] != rec.module_id.code:
                raise ValidationError(
                    "Feature key '%s' must start with its module key '%s.'"
                    % (rec.key, rec.module_id.code))

    def default_for_plan(self, plan):
        self.ensure_one()
        return bool(self['plan_%s' % plan]) if plan in dict(PLANS) else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['pos.config'].sudo().search([])._mobile_sync_flag_lines()
        return records

    def write(self, vals):
        if 'key' in vals and not self.env.context.get('allow_feature_key_change'):
            for rec in self:
                if rec.key != vals['key']:
                    raise ValidationError(
                        "Feature keys are stable once released. Archive '%s' and create a "
                        "new feature instead." % rec.key)
        return super().write(vals)
