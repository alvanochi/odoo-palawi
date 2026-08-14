# -*- coding: utf-8 -*-
from odoo import fields

class OtpRepository:
    def __init__(self, env):
        self.env = env

    def deactivate_previous_otps(self, email):
        # Mark all previous OTPs for this employee email as used/inactive
        previous_otps = self.env['rest_api_plw.otp'].sudo().search([
            ('employee_email', '=', email),
            ('is_used', '=', False)
        ])
        if previous_otps:
            previous_otps.write({'is_used': True})

    def create_otp(self, email, code, expired_at):
        # 1. Deactivate old ones first (rule: active until new request)
        self.deactivate_previous_otps(email)

        # 2. Create new OTP record
        otp_rec = self.env['rest_api_plw.otp'].sudo().create({
            'employee_email': email,
            'otp_code': code,
            'expired_at': expired_at,
            'is_used': False
        })
        return otp_rec

    def find_active_otp(self, email, code):
        now = fields.Datetime.now()
        otp_rec = self.env['rest_api_plw.otp'].sudo().search([
            ('employee_email', '=', email),
            ('otp_code', '=', code),
            ('is_used', '=', False),
            ('expired_at', '>', now)
        ], limit=1)
        return otp_rec

    def mark_as_used(self, otp_rec):
        otp_rec.sudo().write({'is_used': True})
