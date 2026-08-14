# -*- coding: utf-8 -*-
from ..domain.entities.user import UserEntity

class UserRepository:
    def __init__(self, env):
        self.env = env

    def find_active_by_email(self, email):
        user = self.env['res.users'].sudo().search([
            '|',
            ('login', '=', email),
            ('email', '=', email),
            ('active', '=', True),
        ], limit=1)

        if not user:
            return None

        # Look up linked employee
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', user.id),
            '|',
            ('active', '=', True),
            ('active', '=', False),
        ], limit=1)

        return UserEntity(
            user_id=user.id,
            login=user.login,
            name=user.name,
            email=user.email or user.login,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else None
        )

    def find_employee_by_email(self, email):
        employees = self.env['hr.employee'].sudo().search([
            ('user_id', '!=', False),
            ('work_email', '=', email)
        ])
        if not employees:
            return None
        
        # If there are multiple employee records, prioritize the one matching the user's default company
        if len(employees) > 1:
            user = self.env['res.users'].sudo().search([
                ('login', '=', email),
                ('active', '=', True)
            ], limit=1)
            if user:
                matching_emp = employees.filtered(lambda e: e.company_id.id == user.company_id.id)
                if matching_emp:
                    return matching_emp[0]
        
        return employees[0]

    def find_by_id(self, user_id):
        user = self.env['res.users'].sudo().browse(user_id)
        if user.exists() and user.active:
            return UserEntity(
                user_id=user.id,
                login=user.login,
                name=user.name,
                email=user.email or user.login
            )
        return None

    def find_head_users_by_company(self, company_id):
        company = self.env['res.company'].sudo().browse(company_id)
        if company.exists() and company.head_user_id and company.head_user_id.active:
            return company.head_user_id
        return self.env['res.users']
