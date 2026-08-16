# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
import re
from odoo import api, Command, fields, models


class GroupByRegistry(models.Model):
    """Stores and manages group_by filters from search views."""
    _name = 'groupby.registry'
    _description = 'GroupBy Registry'

    name = fields.Char(string='GroupBy Name', required=True)
    context = fields.Char(string='Context')
    string = fields.Char(string='Display Name')
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade')
    view_ids = fields.Many2many('ir.ui.view', string='View')

    @api.model
    def _register_hook(self):
        """Triggers group_by extraction during module initialization."""
        super()._register_hook()
        self.get_all_groupby()
        return True

    def _extract_groupby_attributes(self, filter_tag):
        """Extract attributes from a group_by filter tag."""
        name_match = re.search(r'name="([^"]*)"', filter_tag)
        context_match = re.search(r'context="([^"]*)"', filter_tag)
        string_match = re.search(r'string="([^"]*)"', filter_tag)

        technical_name = name_match.group(1) if name_match else ''
        display_name = string_match.group(1) if string_match else ''

        return {
            'name': technical_name,
            'context': context_match.group(1) if context_match else '',
            'string': display_name
        }

    def get_all_groupby(self):
        """Collect all group_by filters defined in search views."""
        search_views = self.env['ir.ui.view'].search([('type', '=', 'search')])
        groupby_model = {}
        for view in search_views:
            if not view.arch:
                continue
            model_name = view.model
            if not model_name:
                continue
            if model_name not in groupby_model:
                groupby_model[model_name] = {
                    'groupby': [],
                    'view_ids': []
                }
            groupby_tags = re.findall(
                r'<filter[^>]+?context="[^"]*group_by[^"]*"[^>]*?/>', view.arch)
            for groupby_tag in groupby_tags:
                attributes = self._extract_groupby_attributes(groupby_tag)
                if not attributes['name']:
                    continue
                groupby_info = {
                    'name': attributes['name'],
                    'context': attributes['context'],
                    'string': attributes['string']
                }
                if groupby_info not in groupby_model[model_name]['groupby']:
                    groupby_model[model_name]['groupby'].append(groupby_info)
            if view.id not in groupby_model[model_name]['view_ids']:
                groupby_model[model_name]['view_ids'].append(view.id)

        # Batch-fetch all model IDs to avoid N+1 queries
        models_to_search = [m for m in groupby_model.keys() if m]
        model_records = self.env['ir.model'].search([('model', 'in', models_to_search)])
        model_map = {m.model: m.id for m in model_records}

        # Batch-fetch all existing groupby.registry records to avoid N+1 queries
        existing_groupbys = self.search([])
        existing_map = {(g.name, g.model_id.id): g for g in existing_groupbys}

        for model_name, data in groupby_model.items():
            model_id = model_map.get(model_name)
            if not model_id:
                continue
            for groupby_info in data['groupby']:
                name = groupby_info['name']
                context = groupby_info['context']
                string = groupby_info['string']
                display_name = string if string else name
                
                existing_groupby = existing_map.get((display_name, model_id))
                view_ids = data['view_ids']
                
                vals = {
                    'name': display_name,
                    'model_id': model_id,
                    'context': context,
                    'string': string,
                }
                
                if existing_groupby:
                    existing_views = set(existing_groupby.view_ids.ids)
                    incoming_views = set(view_ids)
                    if (existing_groupby.context != context or 
                        existing_groupby.string != string or 
                        existing_views != incoming_views):
                        vals['view_ids'] = [Command.set(view_ids)]
                        existing_groupby.write(vals)
                else:
                    vals['view_ids'] = [Command.link(view) for view in view_ids]
                    self.create(vals)
        return groupby_model

    def _create_or_update_groupby(self, name, model_id, view_ids, context, string):
        """Create or update a groupby registry record."""
        display_name = string if string else name
        existing_groupby = self.search([
            ('name', '=', display_name),
            ('model_id', '=', model_id)
        ], limit=1)
        vals = {
            'name': display_name,
            'model_id': model_id,
            'context': context,
            'string': string
        }
        if existing_groupby:
            existing_views = set(existing_groupby.view_ids.ids)
            incoming_views = set(view_ids)
            if (existing_groupby.context != context or 
                existing_groupby.string != string or 
                existing_views != incoming_views):
                vals['view_ids'] = [Command.set(view_ids)]
                existing_groupby.write(vals)
        else:
            vals['view_ids'] = [Command.link(view) for view in view_ids]
            self.create(vals)
