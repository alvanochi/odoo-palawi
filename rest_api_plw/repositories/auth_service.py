# -*- coding: utf-8 -*-
from odoo.exceptions import AccessDenied

class OdooAuthService:
    def __init__(self, env, session):
        self.env = env
        self.session = session

    def authenticate(self, login, password):
        db = self.env.cr.dbname
        try:
            # 1) Try standard Odoo session authentication
            self.session.authenticate(db, login, password)
            return True
        except Exception:
            # 2) Fallback manual credential checking
            try:
                user = self.env['res.users'].sudo().search([('login', '=', login)], limit=1)
                if not user:
                    return False
                cred = {"type": "password", "password": password}
                user.with_user(user)._check_credentials(cred, {"interactive": True})
                return True
            except AccessDenied:
                return False
