# -*- coding:utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Ayana KP (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
import uuid
from odoo import fields, models


class ResUsers(models.Model):
    """This class is used to inherit users and add api key generation"""
    _inherit = 'res.users'

    api_key = fields.Char(string="API Key", readonly=True,
                          help="Api key for connecting with the "
                               "Database.The key will be "
                               "generated when authenticating "
                               "rest api.")

    def generate_api(self, username):
        """This function is used to generate api-key for each user"""
        users = self.env['res.users'].sudo().search([('login', '=', username)])
        if not users.api_key:
            users.api_key = str(uuid.uuid4())
            key = users.api_key
        else:
            key = users.api_key
        return key



    def _get_user_roles(self):
        """Balikin list role user dari Job Position (Employee) + groups."""
        self.ensure_one()
        roles = []

        # 1. Ambil employee dari user
        employee = self.employee_id
        if not employee:
            employee = self.env["hr.employee"].sudo().search(
                [("user_id", "=", self.id)],
                limit=1,
            )

        # 2. Ambil role dari Job Position (hr.job)
        if employee and employee.job_id:
            job = employee.job_id

            # pakai code kalau ada (lebih stabil buat API)
            if hasattr(job, "code") and job.code:
                roles.append(job.code)
            else:
                roles.append(job.name)

        # 3. System override (opsional tapi umum)
        if self.has_group("base.group_system"):
            roles.append("admin")

        if self.has_group("base.group_user"):
            roles.append("internal_user")

        # hapus duplikat, jaga urutan
        roles = list(dict.fromkeys(roles))
        return roles
