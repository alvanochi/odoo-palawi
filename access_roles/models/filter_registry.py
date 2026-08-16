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
import xml.etree.ElementTree as ET
from odoo import api, Command, fields, models


class FilterRegistry(models.Model):
    """Stores and manages filters from search views."""
    _name = 'filter.registry'
    _description = 'Filter Registry'

    name = fields.Char(string='Filter Name', required=True)
    domain = fields.Char(string='Domain')
    string = fields.Char(string='Display Name')
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade')
    view_ids = fields.Many2many('ir.ui.view', string='View')

    @api.model
    def _register_hook(self):
        """Triggers filter extraction during module initialization."""
        super()._register_hook()
        self.get_all_filters()
        return True

    def _get_filter_elements_from_arch(self, arch):
        """Parse the XML arch and return a list of <filter> elements
           that do not have 'group_by' in their context attribute."""
        try:
            root = ET.fromstring(arch)
        except ET.ParseError:
            return []
        filter_elements = []
        for filter_el in root.iter("filter"):
            context = filter_el.get("context", "")
            if "group_by" in context:
                continue
            filter_elements.append(filter_el)
        return filter_elements

    def _extract_filter_attributes_from_el(self, filter_el):
        """Extract attributes from a filter element."""
        return {
            'name': filter_el.get('name') or '',
            'domain': filter_el.get('domain') or '',
            'string': filter_el.get('string') or '',
        }

    def get_all_filters(self):
        """Collect all filters defined in search views."""
        search_views = self.env['ir.ui.view'].search([('type', '=', 'search')])
        filter_model = {}
        for view in search_views:
            if not view.arch:
                continue
            model_name = view.model
            if not model_name:
                continue
            if model_name not in filter_model:
                filter_model[model_name] = {
                    'filters': [],
                    'view_ids': []
                }
            filter_elements = self._get_filter_elements_from_arch(view.arch)
            for filter_el in filter_elements:
                attributes = self._extract_filter_attributes_from_el(filter_el)
                if not attributes['name']:
                    continue
                filter_info = {
                    'name': attributes['name'],
                    'domain': attributes['domain'],
                    'string': attributes['string']
                }
                if filter_info not in filter_model[model_name]['filters']:
                    filter_model[model_name]['filters'].append(filter_info)
            if view.id not in filter_model[model_name]['view_ids']:
                filter_model[model_name]['view_ids'].append(view.id)

        # Batch-fetch all model IDs to avoid N+1 queries
        models_to_search = [m for m in filter_model.keys() if m]
        model_records = self.env['ir.model'].search([('model', 'in', models_to_search)])
        model_map = {m.model: m.id for m in model_records}

        # Batch-fetch all existing filter.registry records to avoid N+1 queries
        existing_filters = self.search([])
        existing_map = {(f.name, f.model_id.id): f for f in existing_filters}

        for model_name, data in filter_model.items():
            model_id = model_map.get(model_name)
            if not model_id:
                continue
            for filter_info in data['filters']:
                name = filter_info['name']
                domain = filter_info['domain']
                string = filter_info['string']
                display_name = string if string else name
                
                existing_filter = existing_map.get((display_name, model_id))
                view_ids = data['view_ids']
                
                vals = {
                    'name': display_name,
                    'model_id': model_id,
                    'domain': domain,
                    'string': string,
                }
                
                if existing_filter:
                    existing_views = set(existing_filter.view_ids.ids)
                    incoming_views = set(view_ids)
                    if (existing_filter.domain != domain or 
                        existing_filter.string != string or 
                        existing_views != incoming_views):
                        vals['view_ids'] = [Command.set(view_ids)]
                        existing_filter.write(vals)
                else:
                    vals['view_ids'] = [Command.link(view) for view in view_ids]
                    self.create(vals)
        return filter_model

    def _create_or_update_filter(self, name, model_id, view_ids, domain, string):
        """Create or update a filter registry record."""
        display_name = string if string else name
        existing_filter = self.search([
            ('name', '=', display_name),
            ('model_id', '=', model_id)
        ], limit=1)
        vals = {
            'name': display_name,
            'model_id': model_id,
            'domain': domain,
            'string': string
        }
        if existing_filter:
            existing_views = set(existing_filter.view_ids.ids)
            incoming_views = set(view_ids)
            if (existing_filter.domain != domain or 
                existing_filter.string != string or 
                existing_views != incoming_views):
                vals['view_ids'] = [Command.set(view_ids)]
                existing_filter.write(vals)
        else:
            vals['view_ids'] = [Command.link(view) for view in view_ids]
            self.create(vals)
