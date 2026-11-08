# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError

class MarketingOrderCust(models.Model):
    _name = 'marketing.order.cust'
    _description = 'Foom Marketing Order Customer'

    def _default_country(self):
        cn_id = self.env['res.country'].sudo().search([('id', '=', 100)], limit=1)
        return cn_id

    name = fields.Char('Customer', required=True)
    street = fields.Text('Alamat', required=True)
    city = fields.Char('Kota', required=True)
    kecamatan = fields.Char('Kecamatan', required=True)
    country_id = fields.Many2one('res.country', default=_default_country, string='Negara')
    state_id = fields.Many2one('res.country.state', domain="[('country_id', '=', country_id)]", string='Provinsi')
    zip = fields.Char('Kode Pos', required=True)
    mobile = fields.Char('No HP')
    type_id = fields.Many2one('marketing.order.type', string='Tipe', required=True)
    # complete_street = fields.Char('Alamat Lengkap', compute='_compute_complete_street')
    store_id = fields.Char('Store ID')

    @api.constrains('name', 'street', 'zip', 'type_id')
    def _check_existing_request(self):
        CustSudo = self.env['marketing.order.cust'].sudo()
        for r in self:
            if r.name and r.type_id or r.street:
                tipe = CustSudo.search([('id', '!=', r.id), ('name', '=', r.name), ('street', '=', r.street),('zip', '=', r.zip),('type_id', '=', r.type_id.id)], limit=1)
                if tipe:
                    raise ValidationError("Type already exists")
