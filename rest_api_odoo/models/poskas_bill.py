from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

class PoskasBill(models.Model):
    _name = "poskas.bill"
    _description = "POSKAS Bill"

    name = fields.Char(default="Draft Bill")
    name_customer = fields.Char(default="Customer")
    name_waiters = fields.Char(default="Waiters")
    config_id = fields.Many2one("pos.config", required=True, index=True)
    table_ref = fields.Char(string="Meja (Ref)", index=True)  
    table_id = fields.Many2one('restaurant.table', index=True)
    company_id = fields.Many2one(related='config_id.company_id', string='Company', store=True, index=True)
    table_display = fields.Char(string="Meja", compute="_compute_table_display", store=True)
    is_dp = fields.Boolean("Has DP", default=False)
    dp_amount = fields.Float("DP Amount")
    type_order = fields.Selection([
        ("dine_in", "Dine In"),
        ("take_away", "Take Away"),
        ("online", "Online"),
    ], default="dine_in")
    amount_due = fields.Float(compute="_compute_amount_due", store=True)

    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        index=True,
        copy=False
    )
    @api.onchange("dp_amount")
    def _onchange_dp_amount(self):
        self.is_dp = self.dp_amount > 0
    
    @api.depends('table_id', 'table_ref')
    def _compute_table_display(self):
        for bill in self:
            bill.table_display = bill.table_id.display_name if bill.table_id else (bill.table_ref or "-")
    
    state = fields.Selection([
        ("open", "Open"),
        ("paid", "Paid"),
        ("cancel", "Cancel"),
    ], default="open", index=True)

    line_ids = fields.One2many("poskas.bill.line", "bill_id", string="Lines")

    # Diturunkan dari baris, tidak pernah di-set langsung: menyimpan salinan di
    # bill berarti ada dua tempat yang isinya bisa berbeda.
    kitchen_state = fields.Selection([
        ("pending", "Pending"),
        ("cooking", "Cooking"),
        ("ready", "Ready"),
        ("served", "Served"),
    ], string="Kitchen Status", compute="_compute_kitchen_state")

    @api.depends("line_ids.kitchen_state", "line_ids.is_reward_line")
    def _compute_kitchen_state(self):
        for bill in self:
            # Baris promo bukan makanan: potongan harga tidak dimasak siapa pun,
            # dan sejak awal lahir 'served'. Ikut dihitung, ia akan membuat bill
            # yang belum disentuh dapur terbaca seolah sudah mulai dimasak.
            states = [
                (line.kitchen_state or "pending")
                for line in bill.line_ids
                if not line.is_reward_line
            ]
            if not states:
                bill.kitchen_state = False
            elif all(state == "served" for state in states):
                bill.kitchen_state = "served"
            elif all(state in ("ready", "served") for state in states):
                bill.kitchen_state = "ready"
            elif any(state in ("cooking", "ready", "served") for state in states):
                bill.kitchen_state = "cooking"
            else:
                bill.kitchen_state = "pending"

    amount_total = fields.Float(
        string="Total",
        compute="_compute_amount_total",
        store=True,
        readonly=True
    )
    
    
    @api.depends("line_ids.qty", "line_ids.price_unit", "line_ids.discount_percent", "line_ids.subtotal")
    def _compute_amount_total(self):
        for bill in self:
            bill.amount_total = sum((l.subtotal or 0.0) for l in bill.line_ids)
        
    @api.depends("amount_total", "dp_amount")
    def _compute_amount_due(self):
        for bill in self:
            bill.amount_due = max(bill.amount_total - (bill.dp_amount or 0.0), 0.0)
                
            
    def _notify_new_open_bill(self):
        self.ensure_one()
        channel = ("poskas.bill", self.config_id.id)
        payload = {
            "bill_id": self.id,
            "table_id": self.table_id.id if self.table_id else None,
            "table_ref": self.table_ref or "",
            "state": self.state,
            "amount_total": self.amount_total,
            "is_dp": self.is_dp,
            "dp_amount": self.dp_amount,
        }
        _logger.info("BUS SEND channel=%s type=%s payload=%s", channel, "poskas_bill_open", payload)
        self.env["bus.bus"]._sendone(channel, "poskas_bill_open", payload)


    def _notify_bill_state(self):
        self.ensure_one()
        channel = ("poskas.bill", self.config_id.id)
        payload = {
            "bill_id": self.id,
            "table_id": self.table_id.id if self.table_id else None,
            "table_ref": self.table_ref or "",
            "state": self.state,
            "amount_total": self.amount_total,
            "is_dp": self.is_dp,
            "dp_amount": self.dp_amount,
        }
        _logger.info("BUS SEND channel=%s type=%s payload=%s", channel, "poskas_bill_state", payload)
        self.env["bus.bus"]._sendone(channel, "poskas_bill_state", payload)

    
    def _send_kds_realtime(self, event, payload=None):
        """Terbitkan invalidation event bill ke channel KDS milik pos.config.

        Channel-nya disediakan pos_order_extra_states. Modul itu opsional --
        rest_api_odoo tidak boleh mati kalau dapur tidak dipasang -- jadi
        kemampuannya dicek dulu, dan tanpa itu bill hanya diam.
        """
        for bill in self:
            config = bill.config_id
            if not config or not hasattr(config, '_send_kds_realtime'):
                continue
            message = {
                'bill_id': bill.id,
                'bill_state': bill.state,
                'table_id': bill.table_id.id if bill.table_id else None,
                'pos_order_id': bill.pos_order_id.id if bill.pos_order_id else None,
            }
            message.update(payload or {})
            config.sudo()._send_kds_realtime(event, message)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        # Bill.create() ikut membuat baris. Tahan event baris selama proses ini
        # supaya satu open bill tidak membangunkan KDS berkali-kali.
        recs = super(PoskasBill, self.with_context(
            kds_suppress_line_realtime=True)).create(vals_list)
        recs = recs.with_context(kds_suppress_line_realtime=False)
        for r in recs:
            r._notify_bill_state()
        recs._send_kds_realtime('bill.created', {'changed_fields': ['create']})
        return recs




    @api.constrains("dp_amount", "amount_total")
    def _check_dp_amount(self):
        for bill in self:
            if bill.dp_amount < 0:
                raise ValidationError("DP tidak boleh negatif")
            if bill.dp_amount > bill.amount_total:
                raise ValidationError("DP tidak boleh lebih besar dari total bill")
        
    def write(self, vals):
        res = super().write(vals)
        if "state" in vals or "line_ids" in vals or "dp_amount" in vals or "is_dp" in vals:
            for r in self:
                r._notify_bill_state()
        # Antrean dapur ikut berubah begitu bill pindah meja, ditutup, atau
        # ditautkan ke pos.order (yang membuatnya keluar dari antrean bill).
        kds_tracked = {
            "state", "line_ids", "table_id", "table_ref", "config_id",
            "pos_order_id", "name_customer", "name_waiters", "type_order",
        }
        changed = kds_tracked.intersection(vals)
        if changed:
            self._send_kds_realtime('bill.updated', {
                'changed_fields': sorted(changed),
            })
        return res

    def unlink(self):
        for bill in self:
            if bill.state == 'paid':
                raise ValidationError("Data bill dengan status 'Paid' tidak dapat dihapus.")
        snapshots = [(bill.config_id, bill.id, bill.state) for bill in self]
        result = super(PoskasBill, self.with_context(
            kds_suppress_line_realtime=True)).unlink()
        for config, bill_id, state in snapshots:
            if config and hasattr(config, '_send_kds_realtime'):
                config.sudo()._send_kds_realtime('bill.deleted', {
                    'bill_id': bill_id,
                    'bill_state': state,
                    'changed_fields': ['unlink'],
                })
        return result