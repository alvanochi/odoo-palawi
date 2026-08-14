# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError, AccessError
from ...repositories.checkout_repository import TableOccupiedException

class MoveBillTableUseCase:
    def __init__(self, checkout_repo):
        self.checkout_repo = checkout_repo

    def execute(self, config_pos_id, bill_id, table_id):
        if not config_pos_id:
            return {"success": False, "error": "Missing required parameter 'config_pos_id'", "status": 400}
        if not bill_id:
            return {"success": False, "error": "Missing required parameter 'bill_id'", "status": 400}
        if not table_id:
            return {"success": False, "error": "Missing required parameter 'table_id'", "status": 400}

        try:
            config_pos_id = int(config_pos_id)
        except ValueError:
            return {"success": False, "error": "Invalid 'config_pos_id'", "status": 400}

        # Handle potential prefixes like BILL- or T
        bill_id_str = str(bill_id).strip()
        if bill_id_str.upper().startswith("BILL-"):
            bill_id_raw = bill_id_str[5:]
        else:
            bill_id_raw = bill_id_str

        table_id_str = str(table_id).strip()
        if table_id_str.upper().startswith("T"):
            table_id_raw = table_id_str[1:]
        else:
            table_id_raw = table_id_str

        try:
            bill_id_val = int(bill_id_raw)
        except ValueError:
            return {"success": False, "error": f"Invalid 'bill_id' value: {bill_id}", "status": 400}

        try:
            # We check if it is a valid integer for table_id database browse
            table_id_val = int(table_id_raw)
        except ValueError:
            # If not an integer, we treat it as table_ref string
            table_id_val = table_id_str

        try:
            serialized_bill = self.checkout_repo.move_bill_table(
                config_pos_id=config_pos_id,
                bill_id=bill_id_val,
                raw_table_id=table_id_val
            )
            return {
                "success": True,
                "message": "Bill table moved successfully",
                "data": serialized_bill
            }
        except TableOccupiedException as e:
            return {
                "success": False,
                "error": str(e),
                "code": "TABLE_OCCUPIED",
                "existing_bill_id": e.existing_bill_id,
                "status": 409
            }
        except (UserError, ValidationError, AccessError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
