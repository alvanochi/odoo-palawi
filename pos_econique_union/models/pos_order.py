import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

PAID_STATES = ("paid", "done", "invoiced")


class PosOrder(models.Model):
    _inherit = "pos.order"

    # The hook lives on the model, not in the POS UI or a controller: orders
    # paid from the cashier screen and orders paid through the REST API
    # (rest_api_odoo) both write state 'paid' to pos.order, so both are caught here.

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.filtered(lambda o: o.state in PAID_STATES)._econique_enqueue()
        return orders

    def write(self, vals):
        newly_paid = self.browse()
        if vals.get("state") in PAID_STATES:
            newly_paid = self.filtered(lambda o: o.state not in PAID_STATES)
        res = super().write(vals)
        if newly_paid:
            newly_paid._econique_enqueue()
        return res

    def _econique_enqueue(self):
        """Queue orders for Econique. Never makes a payment fail."""
        Transaction = self.env["pos.econique.transaction"].sudo()
        queued = False
        for order in self.sudo():
            try:
                with self.env.cr.savepoint():
                    queued = Transaction._enqueue_order(order) or queued
            except Exception:
                _logger.exception("Econique: failed to queue order %s", order.id)
        if queued:
            try:
                Transaction._trigger_cron()
            except Exception:
                _logger.exception("Econique: failed to trigger the send cron")
