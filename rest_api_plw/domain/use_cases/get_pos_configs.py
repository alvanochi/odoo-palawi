# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class GetPosConfigsUseCase:
    def __init__(self, pos_config_repo):
        self.pos_config_repo = pos_config_repo

    def execute(self, company_id, include_inactive=False):
        try:
            configs = self.pos_config_repo.find_configs_by_company(company_id, include_inactive)
            return {"success": True, "data": [config.to_dict() for config in configs]}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
