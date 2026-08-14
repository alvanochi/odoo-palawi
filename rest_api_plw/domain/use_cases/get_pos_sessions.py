# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class GetPosSessionsUseCase:
    def __init__(self, pos_config_repo):
        self.pos_config_repo = pos_config_repo

    def execute(self, pos_config_id, states=None, date_str=None, limit=20, tz_name='UTC'):
        try:
            sessions = self.pos_config_repo.find_sessions(
                pos_config_id=pos_config_id,
                states=states,
                date_str=date_str,
                limit=limit,
                tz_name=tz_name,
            )
            return {"success": True, "data": [session.to_dict() for session in sessions]}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class GetActivePosSessionUseCase:
    def __init__(self, pos_config_repo):
        self.pos_config_repo = pos_config_repo

    def execute(self, pos_config_id, require_today=False, tz_name='UTC'):
        try:
            result = self.pos_config_repo.find_active_session(
                pos_config_id=pos_config_id,
                require_today=require_today,
                tz_name=tz_name,
            )
            # Having no open session is a normal business state, not an error:
            # the client shows "open a session first" and stays on 200.
            return {"success": True, "data": result}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
