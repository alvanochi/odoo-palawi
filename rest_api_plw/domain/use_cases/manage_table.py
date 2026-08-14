# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

class CreateTableUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, floor_id, data):
        if not floor_id:
            return {"success": False, "error": "floor_id is required", "status": 400}
        if not data.get('name'):
            return {"success": False, "error": "name is required", "status": 400}

        if not self.table_repo.floor_exists(floor_id):
            return {"success": False, "error": "Floor not found (Invalid floor_id)", "status": 400}

        try:
            table_id = self.table_repo.create_table(floor_id, data)
            return {"success": True, "table_id": table_id}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class UpdateTableUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, table_id, data):
        if not table_id:
            return {"success": False, "error": "table_id is required", "status": 400}

        try:
            success = self.table_repo.update_table(table_id, data)
            if not success:
                return {"success": False, "error": "Table not found", "status": 404}
            return {"success": True}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class DeleteTableUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, table_id):
        if not table_id:
            return {"success": False, "error": "table_id is required", "status": 400}

        try:
            success = self.table_repo.delete_table(table_id)
            if not success:
                return {"success": False, "error": "Table not found", "status": 404}
            return {"success": True}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
