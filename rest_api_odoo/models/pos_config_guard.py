from odoo import models

class PosConfig(models.Model):
    _inherit = "pos.config"

    def _compute_last_session_closing_cash(self):
        # WAJIB: assign default dulu untuk semua record
        for config in self:
            config.last_session_closing_cash = 0.0

        # lalu coba hitung dari last closed session kalau ada
        Session = self.env["pos.session"]
        for config in self:
            s = Session.search(
                [
                    ("config_id", "=", config.id),
                    ("state", "=", "closed"),
                ],
                order="stop_at desc, id desc",
                limit=1,
            )
            if not s:
                continue

            # ambil value cash closing yang paling “masuk akal” (tergantung versi Odoo)
            val = 0.0
            if hasattr(s, "cash_register_balance_end_real") and s.cash_register_balance_end_real:
                val = s.cash_register_balance_end_real
            elif hasattr(s, "cash_register_balance_end") and s.cash_register_balance_end:
                val = s.cash_register_balance_end

            config.last_session_closing_cash = float(val or 0.0)
