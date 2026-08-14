# -*- coding: utf-8 -*-
from odoo import models, fields

class RestApiPlwOtp(models.Model):
    _name = 'rest_api_plw.otp'
    _description = 'REST API PLW Login OTP Store'
    _order = 'create_date desc'

    employee_email = fields.Char(string='Employee Email', required=True, index=True)
    otp_code = fields.Char(string='OTP Code', required=True, size=6)
    expired_at = fields.Datetime(string='Expiration Time', required=True)
    is_used = fields.Boolean(string='Is Used', default=False)
