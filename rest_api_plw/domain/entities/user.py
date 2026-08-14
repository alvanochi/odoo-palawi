# -*- coding: utf-8 -*-

class UserEntity:
    def __init__(self, user_id, login, name, email, employee_id=None, employee_name=None):
        self.id = user_id
        self.login = login
        self.name = name
        self.email = email
        self.employee_id = employee_id
        self.employee_name = employee_name
