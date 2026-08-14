# -*- coding: utf-8 -*-

class MailService:
    def __init__(self, env):
        self.env = env

    def send_otp_email(self, recipient_email, recipient_name, employee_name, otp_code, duration_minutes):
        body_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; color: #333333;">
                <p>Dear <strong>{recipient_name}</strong>,</p>
                <p>Employee <strong>{employee_name}</strong> is requesting to log in to the POS system.</p>
                <p>Please provide them with the following login OTP code:</p>
                <div style="background-color: #f5f5f5; padding: 15px; text-align: center; border-radius: 4px; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #279CB4;">{otp_code}</span>
                </div>
                <p>This code is valid for <strong>{duration_minutes} minutes</strong>.</p>
                <p style="font-size: 12px; color: #888888; margin-top: 30px;">This is an automated security notification from POS Odoo PLW.</p>
            </div>
        """
        mail_values = {
            'subject': f'POS Login OTP for {employee_name}',
            'body_html': body_html,
            'email_to': recipient_email,
        }
        # Create and send the mail record
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()
