# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class GetPosOrdersUseCase:
    def __init__(self, pos_order_repo):
        self.pos_order_repo = pos_order_repo

    def execute(self, session_id=None, pos_config_id=None, states=None,
                table_id=None, limit=100, offset=0, kitchen_states=None):
        if not session_id and not pos_config_id:
            return {
                "success": False,
                "error": "Missing required parameter 'pos_session_id' (or 'pos_config_id')",
                "status": 400,
            }

        try:
            orders = self.pos_order_repo.find_orders(
                session_id=session_id,
                pos_config_id=pos_config_id,
                states=states,
                table_id=table_id,
                limit=limit,
                offset=offset,
                kitchen_states=kitchen_states,
            )
            return {"success": True, "data": [order.to_dict() for order in orders]}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class GetPosOrderDetailUseCase:
    def __init__(self, pos_order_repo):
        self.pos_order_repo = pos_order_repo

    def execute(self, order_id):
        try:
            order = self.pos_order_repo.find_order(order_id)
            return {"success": True, "data": order.to_dict()}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 404}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
