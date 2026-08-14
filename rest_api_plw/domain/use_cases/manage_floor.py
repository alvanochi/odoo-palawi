# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

class CreateFloorUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, pos_config_id, name, floor_type=None, background_color=None):
        if not pos_config_id:
            return {"success": False, "error": "pos_config_id is required", "status": 400}
        if not name:
            return {"success": False, "error": "name is required", "status": 400}

        try:
            floor_id = self.table_repo.create_floor(pos_config_id, name, floor_type, background_color)
            return {"success": True, "floor_id": floor_id}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class UpdateFloorUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, floor_id, data):
        if not floor_id:
            return {"success": False, "error": "floor_id is required", "status": 400}

        try:
            success = self.table_repo.update_floor(floor_id, data)
            if not success:
                return {"success": False, "error": "Floor not found", "status": 404}
            return {"success": True}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class DeleteFloorUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, floor_id):
        if not floor_id:
            return {"success": False, "error": "floor_id is required", "status": 400}

        try:
            success = self.table_repo.delete_floor(floor_id)
            if not success:
                return {"success": False, "error": "Floor not found", "status": 404}
            return {"success": True}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
