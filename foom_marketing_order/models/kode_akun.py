# -*- coding: utf-8 -*-

from odoo import models, fields, api

class AnalyticAccInherit(models.Model):
    _inherit = 'account.analytic.account'

    tags = fields.Selection([('MKT', 'Marketing'),], string='Tags')
