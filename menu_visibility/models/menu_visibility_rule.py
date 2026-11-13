from odoo import api, fields, models


class MenuVisibilityRule(models.Model):
    _name = 'menu.visibility.rule'
    _description = 'Menu Visibility Rule'
    _order = 'menu_id'

    menu_id = fields.Many2one(
        'ir.ui.menu', string='Menu', required=True, ondelete='cascade',
        help='This menu and all of its sub menus will be hidden.')
    apply_to = fields.Selection(
        [('all', 'Everyone (except administrators)'),
         ('groups', 'Selected groups'),
         ('users', 'Selected users')],
        string='Hide For', required=True, default='groups')
    group_ids = fields.Many2many(
        'res.groups', 'menu_visibility_rule_group_rel', 'rule_id', 'group_id',
        string='Groups')
    user_ids = fields.Many2many(
        'res.users', 'menu_visibility_rule_user_rel', 'rule_id', 'user_id',
        string='Users')
    active = fields.Boolean(default=True)
    note = fields.Char()

    @api.depends('menu_id')
    def _compute_display_name(self):
        for rule in self:
            rule.display_name = rule.menu_id.complete_name or ''

    def _clear_menu_cache(self):
        self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._clear_menu_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._clear_menu_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self._clear_menu_cache()
        return res
