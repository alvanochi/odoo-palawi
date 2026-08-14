# -*- coding: utf-8 -*-

class GetTableLayoutUseCase:
    def __init__(self, table_repo):
        self.table_repo = table_repo

    def execute(self, pos_config_id):
        if not pos_config_id:
            return {"success": False, "error": "pos_config_id is required", "status": 400}
        
        try:
            floors = self.table_repo.find_layout_by_pos_config(pos_config_id)
            return {
                "success": True,
                "data": [floor.to_dict() for floor in floors]
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
