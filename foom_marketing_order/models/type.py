# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Type(models.Model):

    _name = 'marketing.order.type'
    _description = 'Foom Marketing Order Type'

    @api.onchange('subtype', 'type')
    def onchage_name(self):
        for this in self:
            this.name = ''
            if this.subtype or this.type:
                this.name= '{} - {}'.format(this.subtype, this.type)

    id_type = fields.Char('ID Type', default='New', readonly=True, copy=False)
    name = fields.Char('Name', copy=False, store=True)
    subtype = fields.Selection([
        ('KOL', 'KOL'),
        ('SC', 'Support Customer'),
        ('SP', 'Sample Internal'),
        ('HP', 'Hampers'),
        ('EV', 'Event'),
        ('GI', 'Free Gift/Sample Extenal'),], string='Sub Type', copy=False, required=True)
    type = fields.Char('Type Name',copy=False, required=True, store=True)

    def get_name(self):
        for this in self:
            this.name = ''
            if this.subtype:
                this.name= '{} - {}'.format(this.subtype, this.type)
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('id_type', 'New') == 'New':
                seq_number = self.env['ir.sequence'].next_by_code('marketing.order') or 'New'
                vals['id_type'] = '%s' % (seq_number)
        return super(Type, self).create(vals_list)

    @api.constrains('type', 'subtype')
    def _check_existing_request(self):
        TypeSudo = self.env['marketing.order.type'].sudo()
        for r in self:
            if r.type and r.subtype:
                tipe = TypeSudo.search([('id', '!=', r.id), ('type', '=', r.type), ('subtype', '=', r.subtype)], limit=1)
                if tipe:
                    raise ValidationError("Type already exists")

    # def name_get(self):
    #     result = []
    #     for record in self:
    #         name = record.name or ''
    #         if record.subtype:
    #             subtype = dict(record._fields['subtype'].selection).get(record.subtype)
    #             name += subtype + ' - ' + str(record.type)
    #         result.append((record.id, name))
    #     return result

