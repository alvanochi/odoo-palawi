from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = set(super()._visible_menu_ids(debug=debug))
        hidden = self._menu_visibility_hidden_ids()
        return visible - hidden if hidden else visible

    @api.model
    def _menu_visibility_hidden_ids(self):
        user = self.env.user
        # Administrators are never restricted, so nobody can lock themselves out.
        if self.env.su or user.has_group('base.group_system'):
            return set()
        rules = self.env['menu.visibility.rule'].sudo().search([])
        user_groups = user.groups_id
        menus = self.env['ir.ui.menu'].sudo()
        for rule in rules:
            if (
                rule.apply_to == 'all'
                or (rule.apply_to == 'users' and user in rule.user_ids)
                or (rule.apply_to == 'groups' and rule.group_ids & user_groups)
            ):
                menus |= rule.menu_id
        if not menus:
            return set()
        hidden = self.env['ir.ui.menu'].sudo().with_context(
            active_test=False).search([('id', 'child_of', menus.ids)])
        return set(hidden.ids)
