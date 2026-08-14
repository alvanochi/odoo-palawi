# -*- coding: utf-8 -*-

class GetCompanyPosConfigUseCase:
    def __init__(self, company_repo):
        self.company_repo = company_repo

    def execute(self, user_id, user_login):
        companies_data = self.company_repo.get_companies_config_by_user_id(user_id)
        return {
            'user_id': user_id,
            'user_login': user_login,
            'companies': companies_data
        }
