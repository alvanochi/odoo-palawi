# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

from ..services.promotion_matcher import serialize_program


class GetActivePromotionsUseCase:
    """Active promo programs for a POS, for banners and catalogue display."""

    def __init__(self, promotion_repo):
        self.promotion_repo = promotion_repo

    def execute(self, pos_config_id, program_types=None):
        try:
            programs = self.promotion_repo.get_programs_for_pos_config(
                pos_config_id, program_types)
            return {
                "success": True,
                "data": [serialize_program(program) for program in programs],
            }
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
