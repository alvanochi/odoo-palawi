# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from datetime import datetime, timedelta
import pytz
import logging
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

class MarketingOrder(models.Model):
    _name = 'marketing.order'
    _description = 'Foom Marketing Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_warehouse(self):
        wh_id = self.env['stock.warehouse'].sudo().search([('id', '=', 47)], limit=1)
        return wh_id

    def _default_pricelist(self):
        price_id = self.env['product.pricelist'].sudo().search([('id', '=', 59)], limit=1)
        return price_id

    @api.depends('picking_mv_ids.state')
    def compute_move_state(self):
        for this in self:
            this.delivery_state = 'draft'
            done_move_ids = this.picking_mv_ids.filtered(lambda m: m.state == 'done')
            move_process_ids = this.picking_mv_ids.filtered(lambda m: m.state != 'done')
            if done_move_ids:
                this.delivery_state = 'partially'
                if not move_process_ids:
                    this.delivery_state = 'done'

    name = fields.Char('No MO', default='New', readonly=True, copy=False, tracking=True)
    requestor = fields.Selection([
        ('CE', 'CEO Office'),
        ('TM', 'Trade Marketing'),
        ('SL', 'Sales'),
        ('DM', 'Digital Marketing'),
        ('EV', 'Event/Marketing Lainnya'),
        ('HR', 'HR'),
        ('FS', 'Foom Store'),
        ('RD', 'Research & Development')], string='Requestor', copy=False, required=True,  tracking=True)
    tujuan = fields.Selection([
        ('KOL', 'KOL'),
        ('SC', 'Support Customer'),
        ('SP', 'Sample Internal'),
        ('EV', 'Event'),
        ('HP', 'Hampers'),
        ('GI', 'Free Gift/Sample Extenal'),], string='Tujuan', compute='_compute_tujuan')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('confirm', 'Confirmed'),
        ('reject', 'Rejected'),], string='Status', default='draft', required=True, copy=False,  tracking=True)
    res_partner_id = fields.Many2one('res.partner', string='Customer', copy=False)
    cust_id = fields.Many2one('marketing.order.cust', string='Customer', copy=False)
    nama_tujuan = fields.Char('Nama Tujuan', store=True, readonly=True, copy=False)
    alamat_tujuan = fields.Text('Alamat Tujuan',store=True, copy=False)
    no_hp_tujuan = fields.Char('No HP Tujuan',store=True, copy=False)
    line_ids = fields.One2many('marketing.order.line', 'marketing_id', string='Product', copy=False)
    amount_total = fields.Float('Total', compute="_calc_total", store=True, copy=False)
    amount_total2 = fields.Float('Total', compute="_calc_total", store=True, copy=False)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', default=_default_warehouse, domain="[('is_marketing_order', '=', True)]", copy=False, required=True)
    count_do = fields.Integer(string='Delivery', compute='_compute_do')
    count_mv = fields.Integer(string='Move', compute='_compute_move')
    type_id = fields.Many2one('marketing.order.type', string='Tipe', tracking=True, required=True)
    analytic_id = fields.Many2one('account.analytic.account', domain="[('tags', '=', 'MKT')]", copy=False, required=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', default=_default_pricelist, readonly=True)
    account_mv_ids = fields.One2many('account.move', 'mkt_id')
    picking_mv_ids = fields.One2many('stock.picking', 'mkt_id')
    notes = fields.Text('Notes')
    delivery_state = fields.Selection(string='Delivery state', selection=[('draft', 'Not Yet'), ('partially', 'Partially'), ('done', 'Done'), ('cancel', 'Cancelled')], compute=compute_move_state, store=True)

    def unlink(self):
        for this in self:
            if this.picking_mv_ids:
                for mv_id in this.picking_mv_ids:
                    if mv_id.state != 'done':
                        mv_id.action_cancel()
                        mv_id.unlink()
                    else:
                        raise UserError('Ada Delivery yang sudah done')
            return super(MarketingOrder, self).unlink()
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                seq_number = self.env['ir.sequence'].next_by_code('marketing.order') or 'New'
                now = datetime.now()
                if vals.get('requestor') == 'TM':
                    vals['name'] = '%s/MKT/TM/%s/%s' % ( seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'SL':
                    vals['name'] = '%s/MKT/SALES/%s/%s' % ( seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'DM':
                    vals['name'] = '%s/MKT/DM/%s/%s' % ( seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'EV':
                    vals['name'] = '%s/MKT/EV/%s/%s' % ( seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'HR':
                    vals['name'] = '%s/MKT/HR/%s/%s' % ( seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'FS':
                    vals['name'] = '%s/MKT/FS/%s/%s' % (seq_number, now.strftime("%m"), now.strftime("%y"))
                elif vals.get('requestor') == 'RD':
                    vals['name'] = '%s/MKT/RD/%s/%s' % (seq_number, now.strftime("%m"), now.strftime("%y"))
        return super(MarketingOrder, self).create(vals_list)

    # def copy(self, default=None):
    #     raise exceptions.UserError("Duplicating records is not allowed.")

    @api.onchange('res_partner_id', 'cust_id')
    def _onchange_vendor(self):
        for rec in self:
            if rec.res_partner_id:
                rec.nama_tujuan = rec.res_partner_id.name
                rec.alamat_tujuan = rec.res_partner_id.street
                rec.no_hp_tujuan = rec.res_partner_id.mobile
            elif rec.cust_id:
                rec.nama_tujuan = rec.cust_id.name
                rec.alamat_tujuan = rec.cust_id.street
                rec.no_hp_tujuan = rec.cust_id.mobile
            else:
                rec.nama_tujuan = False
                rec.alamat_tujuan = False
                rec.no_hp_tujuan = False

    @api.depends('line_ids.subtotal','line_ids.subtotal2')
    def _calc_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('subtotal'))
            rec.amount_total2 = sum(rec.line_ids.mapped('subtotal2'))

    def appr_action_submit(self):
        for rec in self:
            rec.state = 'submit'
            rec._check_unit_price()

    def appr_action_appr(self):
        for rec in self:
            rec.state = 'confirm'
            rec.create_picking()
            # rec.create_acc_move()

    def appr_action_reject(self):
        for rec in self:
            rec.state = 'reject'

    def appr_action_set_to_draft(self):
        for rec in self:
            rec.check_picking()

    def create_picking(self):
        self.ensure_one()
        existing_picking = self.line_ids.picking_id
        prod = []
        wh = self.warehouse_id.sudo()
        if not wh:
            raise UserError(
                "Warehouse belum diisi.\n\n"
                "Buka tab \"Other Info\", pilih Warehouse, lalu Confirm ulang."
            )
        if not wh.lot_stock_id:
            raise UserError(
                "Warehouse \"%s\" belum punya Stock Location.\n\n"
                "Minta admin melengkapi konfigurasi warehouse ini di "
                "Inventory > Configuration > Warehouses sebelum Confirm."
                % wh.display_name
            )
        if not wh.out_type_id:
            raise UserError(
                "Warehouse \"%s\" belum punya Operation Type untuk pengiriman.\n\n"
                "Minta admin melengkapi konfigurasi warehouse ini sebelum Confirm."
                % wh.display_name
            )
        loc = wh.lot_stock_id.id
        # Scrap Location => Sample => Inventory Loss => 7.01.01.08 Beban Product Sample
        scrap_param = self.env['ir.config_parameter'].sudo().get_param('foom_marketing_order.sample_location_id')
        if not scrap_param:
            raise UserError(
                "Lokasi Sample belum di-set.\n\n"
                "Minta admin mengisinya di Marketing Order > Configuration > Settings."
            )
        # Lokasi harus benar-benar ada. Tanpa cek ini, referensi ke lokasi yang
        # sudah terhapus lolos ke database dan gagal sebagai foreign key
        # violation (stock_picking_location_dest_id_fkey) dengan pesan
        # menyesatkan soal "record being deleted".
        scrap_location = self.env['stock.location'].sudo().browse(int(scrap_param)).exists()
        if not scrap_location:
            raise UserError(
                "Lokasi Sample yang di-set (ID %s) sudah tidak ada di database.\n\n"
                "Minta admin memilih ulang lokasinya di "
                "Marketing Order > Configuration > Settings." % scrap_param
            )
        scrap_location_id = scrap_location.id

        for po in self.line_ids:
            if po.picking_id:
                # Update existing product in stock.picking
                move = po.picking_id.move_ids_without_package.filtered(lambda m: m.product_id == po.product_id)
                move.write({
                    'product_uom_qty': po.qty,
                })
            else:
                # Add new product to stock.picking
                prod.append((0, 0, {
                    'product_id': po.product_id.id,
                    'product_uom_qty': po.qty,
                    'name': po.product_id.name,
                    'product_uom': po.product_id.uom_id.id,
                    'location_id': loc,
                    'location_dest_id': scrap_location_id,
                }))

        sample = self.env['res.partner'].sudo().search([('id', '=', 485)], limit=1).id
        partner = self.res_partner_id.id if self.type_id.subtype in ['SC', 'HP'] else sample
        vals = {
            'partner_id': partner,
            'mkt_id': self.id,
            'name_tujuan': self.cust_id.name if self.type_id.subtype not in ['SC', 'HP'] else '',
            'street': self.cust_id.street if self.type_id.subtype not in ['SC', 'HP'] else '',
            'city': self.cust_id.city if self.type_id.subtype not in ['SC', 'HP'] else '',
            'kecamatan': self.cust_id.kecamatan if self.type_id.subtype not in ['SC', 'HP'] else '',
            'state_id': self.cust_id.state_id.id if self.type_id.subtype not in ['SC', 'HP'] and self.cust_id.state_id else False,
            'zip': self.cust_id.zip if self.type_id.subtype not in ['SC', 'HP'] else '',
            'mobile': self.cust_id.mobile if self.type_id.subtype not in ['SC', 'HP'] else '',
            'origin': self.name.replace("MKT", "SAMPLE"),
            'picking_type_id': self.warehouse_id.out_type_id.id,
            'location_id': loc,
            'location_dest_id': scrap_location_id,
        }

        if prod:
            vals['move_ids_without_package'] = prod

        if existing_picking:
            # Update moves in existing picking
            for move in existing_picking.move_ids_without_package:
                order_line = self.line_ids.filtered(lambda line: line.product_id == move.product_id)
                if order_line:
                    move.write({
                        'product_uom_qty': order_line.qty,
                    })
                else:
                    move.sudo().unlink()

            existing_picking.write(vals)
        else:
            picking = self.env['stock.picking'].sudo().create(vals)
            # Update the picking reference in the marketing order
            self.line_ids.picking_id = picking.id
            self.picking_mv_ids |= picking

        self.count_do = len(self.picking_mv_ids)

    def create_acc_move(self):
        acc = []
        if self.count_mv == 0:
            for po in self.picking_mv_ids:
                if po.state == 'done':
                    for move in po.move_ids_without_package:
                        acc.append((0, 0, {
                            'account_id': move.product_id.categ_id.property_stock_valuation_account_id.id,
                            'name': move.product_id.name,
                            'analytic_account_id': self.analytic_id.id,
                            'debit': 0,
                            'credit': move.product_uom_qty * move.product_id.standard_price,
                        }))
                        acc.append((0, 0, {
                            'account_id': self.env['account.account'].sudo().search([('id', '=', '1617')], limit=1).id,
                            'name': move.product_id.name,
                            'debit': move.product_uom_qty * move.product_id.standard_price,
                            'analytic_account_id': self.analytic_id.id,
                            'credit': 0,
                        }))
        else:
            #get id picking yang belum terbuat journal
            pick = self.picking_mv_ids[0]
            print(pick)
            print(self.picking_mv_ids)
            # raise ValidationError('Ts')
            for move in pick.move_ids_without_package:
                acc.append((0, 0, {
                    'account_id': move.product_id.categ_id.property_stock_valuation_account_id.id,
                    'name': move.product_id.name,
                    'analytic_account_id': self.analytic_id.id,
                    'debit': 0,
                    'credit': move.product_uom_qty * move.product_id.standard_price,
                }))
                acc.append((0, 0, {
                    'account_id': self.env['account.account'].sudo().search([('id', '=', '1617')], limit=1).id,
                    'name': move.product_id.name,
                    'debit': move.product_uom_qty * move.product_id.standard_price,
                    'analytic_account_id': self.analytic_id.id,
                    'credit': 0,
                }))
        print(acc)
        if acc:
            vals = {
                'ref': self.name.replace("MKT", "SAMPLE"),
                'mkt_id': self.id,
                'date': fields.Date.today(),
                'journal_id': self.env['account.journal'].sudo().search([('code', '=', 'MISC')], limit=1).id,
                'line_ids': acc,
            }
            move = self.env['account.move'].sudo().create(vals)
            self.account_mv_ids |= move
            print('Acc ids',self.account_mv_ids)

    @api.depends('line_ids.picking_id', 'picking_mv_ids')
    def _compute_do(self):
        for rec in self:
            # count = self.env['stock.picking'].search_count([('id', 'in', rec.line_ids.mapped('picking_id').ids)])
            # count = self.env['stock.picking'].search_count([('origin', '=', str(self.name.replace("MKT", "SAMPLE")))])
            rec.count_do = len(rec.picking_mv_ids)

    def open_do(self):
        do_ids = []
        # for line in self.line_ids:
        #     if line.picking_id:
        #         do_ids.append(line.picking_id.id)
        for picking_id in self.picking_mv_ids:
            if picking_id:
                do_ids.append(picking_id.id)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Delivery',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            # 'domain': [('origin', '=', str(self.name.replace("MKT", "SAMPLE")))],
            'domain': [('id', 'in', do_ids)],
        }

    @api.depends('line_ids')
    def _compute_move(self):
        count = self.env['account.move'].search_count([('ref', '=', str(self.name.replace("MKT", "SAMPLE")))])
        self.count_mv = count

    def open_move(self):
        move_ids = []
        for line in self.line_ids:
            if line.move_id:
                move_ids.append(line.move_id.id)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Account Move',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('ref', '=', str(self.name.replace("MKT", "SAMPLE")))],
        }

    @api.depends('type_id')
    def _compute_tujuan(self):
        self.tujuan = self.type_id.subtype

    def check_picking(self):
        for order in self:
            if order.line_ids.picking_id:
                picking = order.line_ids.picking_id
                if picking.state != 'draft':
                    raise ValidationError(
                        "Cannot reset to draft. The associated picking is already %s." % picking.state)

                if picking.state == 'done':
                    raise ValidationError("Cannot reset to draft. The associated picking is already delivered.")

                if picking.state == 'assigned':
                    # Check if the demand (product_uom_qty) is different from quantity_done
                    for move in picking.move_lines:
                        if move.product_uom_qty != move.quantity_done:
                            raise ValidationError(
                                "Cannot reset to draft. The associated picking is partially delivered.")
                # Reset the picking to draft state
                if picking.state == 'draft':
                    order.write({'state': 'draft'})
            else:
                order.write({'state': 'draft'})

    def _check_unit_price(self):
        for rec in self.line_ids:
            if rec.unit_price == 0:
                raise ValidationError('Unit Price cannot be 0!')

class ProductInherit(models.Model):
    _name = 'marketing.order.line'
    _description = 'Foom Marketing Order Line'

    picking_id = fields.Many2one('stock.picking', string='Picking', readonly=True)
    product_id = fields.Many2one('product.product', required=True)
    marketing_id = fields.Many2one('marketing.order')
    move_id = fields.Many2one('account.move')
    barcode = fields.Char('Barcode', related="product_id.barcode")
    qty = fields.Float('Qty')
    uom_id = fields.Many2one('uom.uom', string='UoM', store=True)
    unit_price = fields.Float('Unit Price')
    cost_price = fields.Float('Cost Price')
    subtotal = fields.Float('Subtotal', compute="campute_subtotal", store=True)
    subtotal2 = fields.Float('Subtotal Cost', compute="campute_subtotal", store=True)
    variant_ids = fields.Many2many('product.template.attribute.value', readonly=True, related="product_id.product_template_variant_value_ids")

    @api.onchange('product_id')
    def onchange_product(self):
        for rec in self:
            if rec.product_id:
                rec.uom_id = rec.product_id.uom_id
                rec.cost_price = rec.product_id.standard_price
                rec.uom_id = rec.product_id.uom_id

    @api.depends('qty', 'unit_price')
    def campute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.qty * rec.unit_price
            rec.subtotal2 = rec.qty * rec.cost_price

    @api.onchange('product_id')
    def get_pricelist(self):
        self.ensure_one()
        for rec in self:
            product_obj = self.env['product.product'].sudo().browse(rec.product_id.id)
            for price in rec.marketing_id.pricelist_id.item_ids:
                if rec.variant_ids:
                    if price.name == 'Variant: '+ str(product_obj.display_name):
                        rec.unit_price = price.fixed_price
                        if rec.unit_price < 1:
                            raise ValidationError('Unit Price cannot be 0. Please check unit price in Pricelist!')
                else:
                    if price.name == 'Product: ' + str(product_obj.display_name):
                        rec.unit_price = price.fixed_price
                        if rec.unit_price < 1:
                            raise ValidationError('Unit Price cannot be 0. Please check unit price in Pricelist!')