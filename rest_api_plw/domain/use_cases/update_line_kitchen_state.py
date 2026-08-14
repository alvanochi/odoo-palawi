# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError


class UpdateLineKitchenStateUseCase:
    """Move one dish along pending -> cooking -> ready -> served.

    The order's own kitchen_state is derived from its lines, never set here:
    two independently writable statuses would eventually disagree.

    `source` records whether a human observed the dish was done ('staff') or a
    countdown simply ran out ('timer'). An elapsed estimate is not proof the
    food is ready, so keeping the two apart is what makes it possible to tell
    later how far the estimates actually were from reality.
    """

    def __init__(self, pos_order_repo):
        self.pos_order_repo = pos_order_repo

    def execute(self, order_id, line_id, target_state, source='staff'):
        if not target_state:
            return {
                "success": False,
                "error": "Missing required parameter 'state' (or 'action')",
                "status": 400,
            }

        try:
            order = self.pos_order_repo.set_line_kitchen_state(
                order_id, line_id, target_state, source or 'staff')
            return {
                "success": True,
                "message": f"Kitchen state updated to '{target_state}'",
                "data": order.to_dict(),
            }
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
