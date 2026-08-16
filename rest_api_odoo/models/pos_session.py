# -*- coding: utf-8 -*-
import logging
from odoo import models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    def _kas_force_cash_statement_opening(self):
        for session in self:
            # ambil amount dari field session
            amount = 0.0
            if "cash_register_balance_start_real" in session._fields and session.cash_register_balance_start_real:
                amount = session.cash_register_balance_start_real
            elif "cash_register_balance_start" in session._fields and session.cash_register_balance_start:
                amount = session.cash_register_balance_start

            try:
                amount = float(amount or 0.0)
            except Exception:
                amount = 0.0

            # cash_register_id dulu
            st = getattr(session, "cash_register_id", False)
            if st:
                vals = {}
                if "balance_start" in st._fields:
                    vals["balance_start"] = amount
                if "balance_start_real" in st._fields:
                    vals["balance_start_real"] = amount
                if vals:
                    _logger.warning("[KAS_OPENING_OVERRIDE] FORCE cash_register_id session=%s st=%s vals=%s",
                                    session.id, st.id, vals)
                    st.sudo().write(vals)

            # fallback statement_ids
            statements = getattr(session, "statement_ids", False)
            if statements:
                try:
                    cash_statements = statements.filtered(
                        lambda s: getattr(getattr(s, "journal_id", None), "type", "") == "cash"
                    ) or statements
                except Exception:
                    cash_statements = statements

                for s in cash_statements:
                    vals = {}
                    if "balance_start" in s._fields:
                        vals["balance_start"] = amount
                    if "balance_start_real" in s._fields:
                        vals["balance_start_real"] = amount
                    if vals:
                        _logger.warning("[KAS_OPENING_OVERRIDE] FORCE statement_ids session=%s st=%s vals=%s",
                                        session.id, s.id, vals)
                        s.sudo().write(vals)

            if not st and not statements:
                _logger.warning("[KAS_OPENING_OVERRIDE] session=%s no statements yet (cash_register_id/statement_ids empty)", session.id)

    

    def action_pos_session_open(self):
        res = super().action_pos_session_open()
        try:
            self._kas_force_cash_statement_opening()
        except Exception:
            _logger.exception("[KAS_OPENING_OVERRIDE] failed after action_pos_session_open()")
        return res
