from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

class AccMvInherit(models.Model):
    _inherit = 'account.move'

    mkt_id = fields.Many2one('marketing.order')

class StockPickingInherit(models.Model):
    @api.depends('mkt_id', 'scheduled_date', 'partner_id')
    def domain_opration_type(self):
        for this in self:
            opration_obj = self.env['stock.picking.type']
            if this.mkt_id:
                this.domain_picking_type_ids = opration_obj.search([('is_marketing_order', '=', True)]).ids
            else:
                this.domain_picking_type_ids = opration_obj.search(['|', ('code', 'in', ('incoming','outgoing')), ('internal_non_staging', '=', True)]).ids

    _inherit = 'stock.picking'

    street = fields.Text('Alamat', readonly=True)
    city = fields.Char('Kota', readonly=True)
    kecamatan = fields.Char('Kecamatan', readonly=True)
    state_id = fields.Many2one('res.country.state', string='Provinsi', readonly=True)
    zip = fields.Char('Kode Pos', readonly=True)
    mobile = fields.Char('No HP', readonly=True)
    name_tujuan = fields.Char('Customer', readonly=True)
    partner_name = fields.Char('Nama Cust', related='partner_id.name')
    mkt_id = fields.Many2one('marketing.order')
    domain_picking_type_ids = fields.Many2many('stock.picking.type', string='Operation Domain', compute=domain_opration_type)

    # Already checked
    def button_set_to_draft(self):
        for this in self:
            this.action_cancel()
            this.write({'state': 'draft'})
            for move_id in this.move_ids_without_package:
                move_id.write({'state': 'draft'})

    def action_confirm(self):
        res = super(StockPickingInherit, self).action_confirm()
        origin ='1'
        for this in self:
            if this.origin:
                origin = this.origin
            if 'Return' not in origin:
                if this.mkt_id and not this.to_return_location:
                    picking_done = this.mkt_id.picking_mv_ids.filtered(lambda m: m.state == 'done' and 'Return' not in m.origin)
                    picking_done_return = this.mkt_id.picking_mv_ids.filtered(lambda m: m.state == 'done' and 'Return' in m.origin)
                    if picking_done:
                        for line_id in this.move_ids_without_package:
                            line_request = this.mkt_id.line_ids.filtered(lambda m: m.product_id.id == line_id.product_id.id)
                            qty_request = sum(request_id.qty for request_id in line_request)
                            qty_done = 0
                            qty_return = 0
                            for done_id in picking_done:
                                done_line = done_id.move_ids_without_package.filtered(lambda m: m.product_id.id == line_id.product_id.id)
                                qty_done = qty_done + sum(line.quantity_done for line in done_line)
                            if picking_done_return:
                                for return_id in picking_done_return:
                                    line_return = return_id.move_ids_without_package.filtered(lambda m: m.product_id.id == line_id.product_id.id)
                                    qty_return = qty_return + sum(line_id.quantity_done for line_id in line_return)
                            qty_done = qty_done -  qty_return
                            if qty_done + line_id.product_uom_qty > qty_request:
                                raise UserError('Delivery Quantity for {} more than request'.format(line_id.product_id.name))
        return res

    def button_validate(self):
        res = super(StockPickingInherit, self).button_validate()
        if self.state == 'done':
            marketing = self.sudo().mkt_id
            if marketing:
                if not self.backorder_id:
                    unposted_account_moves = self.sudo().mkt_id.account_mv_ids.filtered(
                        lambda move: move.state == 'draft')
                    print(unposted_account_moves)
                    if unposted_account_moves:
                        for acc in self.sudo().mkt_id.account_mv_ids:
                            vals = {
                                'date': datetime.now(),
                            }
                            acc.sudo().write(vals)
                            acc.sudo().action_post()
                    else:
                        # marketing.create_acc_move()
                        for acc in self.sudo().mkt_id.account_mv_ids:
                            vals = {
                                'date': datetime.now(),
                            }
                            acc.sudo().write(vals)
                            acc.sudo().action_post()
                else:
                    # marketing.create_acc_move()
                    for acc in self.sudo().mkt_id.account_mv_ids:
                        if acc.state != 'done' and acc.id:
                            vals = {
                                'date': datetime.now(),
                            }
                            unposted_account_moves = self.sudo().mkt_id.account_mv_ids.filtered(
                                lambda move: move.state != 'posted')
                            unposted_account_moves.sudo().write(vals)
                            unposted_account_moves.sudo().action_post()
        return res


class StockPickingLineInherit(models.Model):
    _inherit = 'stock.move.line'

    mkt_unit_price = fields.Float('Unit Price Marketing', related='picking_id.mkt_id.line_ids.unit_price')

class StockBackorderConfirmationInherit(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    def process(self):
        # Call the parent method to create backorders
        res = super(StockBackorderConfirmationInherit, self).process()
        # Set mkt_id for backorders that are created from pickings with mkt_id
        for picking in self.pick_ids:
            if picking.mkt_id:
                backorder = picking.backorder_id
                if backorder:
                    backorder.mkt_id = picking.mkt_id.id
        return res

class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def create_returns(self):
        res = super(StockReturnPicking, self).create_returns()
        res_id = res['res_id']
        picking_obj = self.env['stock.picking']
        picking_id = picking_obj.search([('id', '=', res_id)])
        if self.picking_id.mkt_id:
            picking_id.write({'mkt_id':self.picking_id.mkt_id.id})
        return res

