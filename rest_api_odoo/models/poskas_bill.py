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

    
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for r in recs:
            r._notify_bill_state()
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
        return res

    def unlink(self):
        for bill in self:
            if bill.state == 'paid':
                raise ValidationError("Data bill dengan status 'Paid' tidak dapat dihapus.")
        return super().unlink()