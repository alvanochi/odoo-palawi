import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosMobileModule(models.Model):
    _name = 'pos.mobile.module'
    _description = 'POS Mobile Module (master flag)'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        string='Module Key', required=True, index=True,
        help="snake_case key, e.g. 'cashier'. Master flag key becomes 'module.<code>'.")
    master_key = fields.Char(compute='_compute_master_key', store=True)
    sequence = fields.Integer(default=10)
    description = fields.Char()
    active = fields.Boolean(default=True)
    feature_ids = fields.One2many('pos.mobile.feature', 'module_id', string='Features')
    feature_count = fields.Integer(compute='_compute_feature_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Module key must be unique.'),
    ]

    @api.depends('code')
    def _compute_master_key(self):
        for rec in self:
            rec.master_key = 'module.%s' % rec.code if rec.code else False

    @api.depends('feature_ids')
    def _compute_feature_count(self):
        for rec in self:
            rec.feature_count = len(rec.feature_ids)

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', rec.code or ''):
                raise ValidationError(
                    "Module key must be lowercase snake_case (e.g. 'digital_order').")

    def write(self, vals):
        if 'code' in vals:
            for rec in self:
                if rec.code and rec.code != vals['code'] and rec.feature_ids:
                    raise ValidationError(
                        "Keys are stable once released. Archive this module and create "
                        "a new one instead of renaming '%s'." % rec.code)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['pos.config'].sudo().search([])._mobile_sync_flag_lines()
        return records
