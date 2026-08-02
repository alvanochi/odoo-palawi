# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PartnerContract(models.Model):
    """Kontrak mitra / tenant dengan penagihan berkala."""
    _name = 'partner.contract'
    _description = 'Kontrak Mitra / Tenant'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Nomor Kontrak', default=lambda self: _('New'),
        copy=False, readonly=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Mitra / Tenant', required=True, tracking=True)
    contract_type = fields.Selection(
        [('mitra', 'Mitra'), ('tenant', 'Tenant')],
        string='Tipe Kontrak', default='tenant', required=True, tracking=True)
    date_start = fields.Date(
        string='Tanggal Mulai', required=True,
        default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(string='Tanggal Berakhir', tracking=True)
    fee_type = fields.Selection(
        [('flat', 'Flat'), ('percentage', 'Persentase')],
        string='Jenis Biaya', default='flat', required=True, tracking=True)
    fixed_amount = fields.Monetary(
        string='Nominal Flat', currency_field='currency_id', tracking=True)
    percentage = fields.Float(
        string='Persentase (%)', digits=(5, 2), tracking=True)
    base_amount = fields.Monetary(
        string='Dasar Perhitungan (Omzet)', currency_field='currency_id',
        tracking=True,
        help='Nilai dasar untuk biaya persentase, misalnya omzet per '
             'periode. Biaya = Dasar Perhitungan x Persentase.')
    fee_amount = fields.Monetary(
        string='Biaya per Periode', currency_field='currency_id',
        compute='_compute_fee_amount', store=True)
    billing_period = fields.Selection(
        [('monthly', 'Bulanan'), ('yearly', 'Tahunan')],
        string='Periode Penagihan', default='monthly', required=True,
        tracking=True)
    next_billing_date = fields.Date(
        string='Tanggal Tagihan Berikutnya', copy=False,
        help='Tanggal pembuatan tagihan periode berikutnya. '
             'Diisi otomatis dari Tanggal Mulai saat kontrak dibuat.')
    state = fields.Selection(
        [('draft', 'Draft'), ('running', 'Berjalan'),
         ('expired', 'Berakhir'), ('cancelled', 'Dibatalkan')],
        string='Status', default='draft', copy=False, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Perusahaan', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Mata Uang')
    notes = fields.Text(string='Catatan')
    invoice_ids = fields.One2many(
        'account.move', 'contract_id', string='Tagihan')
    invoice_count = fields.Integer(
        string='Jumlah Tagihan', compute='_compute_invoice_totals')
    amount_invoiced = fields.Monetary(
        string='Total Ditagihkan', currency_field='currency_id',
        compute='_compute_invoice_totals')
    amount_due = fields.Monetary(
        string='Sisa Tagihan', currency_field='currency_id',
        compute='_compute_invoice_totals')
    payment_status = fields.Selection(
        [('no_invoice', 'Belum Ada Tagihan'),
         ('unpaid', 'Belum Lunas'),
         ('paid', 'Lunas')],
        string='Status Pembayaran', compute='_compute_payment_status',
        store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'partner.contract') or _('New')
            if not vals.get('next_billing_date') and vals.get('date_start'):
                vals['next_billing_date'] = vals['date_start']
        return super().create(vals_list)

    @api.depends('fee_type', 'fixed_amount', 'percentage', 'base_amount')
    def _compute_fee_amount(self):
        for contract in self:
            if contract.fee_type == 'flat':
                contract.fee_amount = contract.fixed_amount
            else:
                contract.fee_amount = \
                    contract.base_amount * contract.percentage / 100.0

    @api.depends('invoice_ids', 'invoice_ids.state',
                 'invoice_ids.payment_state', 'invoice_ids.amount_total',
                 'invoice_ids.amount_residual')
    def _compute_invoice_totals(self):
        for contract in self:
            invoices = contract.invoice_ids.filtered(
                lambda m: m.state != 'cancel')
            posted = invoices.filtered(lambda m: m.state == 'posted')
            contract.invoice_count = len(invoices)
            contract.amount_invoiced = sum(posted.mapped('amount_total'))
            contract.amount_due = sum(posted.mapped('amount_residual'))

    @api.depends('invoice_ids', 'invoice_ids.state',
                 'invoice_ids.payment_state')
    def _compute_payment_status(self):
        for contract in self:
            invoices = contract.invoice_ids.filtered(
                lambda m: m.state != 'cancel')
            if not invoices:
                contract.payment_status = 'no_invoice'
            elif any(m.state == 'draft'
                     or m.payment_state in ('not_paid', 'partial')
                     for m in invoices):
                contract.payment_status = 'unpaid'
            else:
                contract.payment_status = 'paid'

    @api.constrains('percentage', 'fee_type')
    def _check_percentage(self):
        for contract in self:
            if contract.fee_type == 'percentage' and \
                    not 0 <= contract.percentage <= 100:
                raise ValidationError(
                    _('Persentase harus di antara 0 dan 100.'))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError(
                    _('Tanggal Berakhir tidak boleh lebih awal dari '
                      'Tanggal Mulai.'))

    def action_confirm(self):
        for contract in self:
            if contract.state != 'draft':
                continue
            if not contract.next_billing_date:
                contract.next_billing_date = contract.date_start
            contract.state = 'running'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_set_to_draft(self):
        self.write({'state': 'draft'})

    def action_expire(self):
        self.write({'state': 'expired'})

    def _get_period_label(self, billing_date):
        self.ensure_one()
        if self.billing_period == 'monthly':
            return billing_date.strftime('%m/%Y')
        return billing_date.strftime('%Y')

    def _create_period_invoice(self):
        """Buat satu tagihan (draft) untuk periode berjalan dan majukan
        tanggal tagihan berikutnya."""
        self.ensure_one()
        if self.currency_id.is_zero(self.fee_amount):
            raise UserError(_(
                'Biaya per periode kontrak %s masih 0. Isi Nominal Flat '
                'atau Persentase + Dasar Perhitungan terlebih dahulu.',
                self.name))
        billing_date = self.next_billing_date or fields.Date.context_today(
            self)
        product = self.env.ref(
            'partner_contract.product_contract_fee',
            raise_if_not_found=False)
        line_name = _('%(contract)s - Biaya kontrak periode %(period)s',
                      contract=self.name,
                      period=self._get_period_label(billing_date))
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': billing_date,
            'invoice_origin': self.name,
            'contract_id': self.id,
            'company_id': self.company_id.id,
            'invoice_line_ids': [Command.create({
                'product_id': product.id if product else False,
                'name': line_name,
                'quantity': 1.0,
                'price_unit': self.fee_amount,
            })],
        })
        delta = relativedelta(months=1) if self.billing_period == 'monthly' \
            else relativedelta(years=1)
        self.next_billing_date = billing_date + delta
        self.message_post(body=_(
            'Tagihan %(invoice)s dibuat untuk periode %(period)s.',
            invoice=invoice.name or invoice.id,
            period=self._get_period_label(billing_date)))
        return invoice

    def action_create_invoice(self):
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_(
                'Tagihan hanya bisa dibuat untuk kontrak berstatus '
                'Berjalan. Konfirmasi kontrak terlebih dahulu.'))
        invoice = self._create_period_invoice()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tagihan'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tagihan %s', self.name),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {
                'default_move_type': 'out_invoice',
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
            },
        }

    @api.model
    def _cron_generate_invoices(self):
        """Cron harian: tandai kontrak kedaluwarsa dan buat tagihan untuk
        kontrak yang sudah jatuh tempo penagihannya."""
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'running'),
            ('date_end', '!=', False),
            ('date_end', '<', today),
        ])
        expired.write({'state': 'expired'})
        contracts = self.search([
            ('state', '=', 'running'),
            ('next_billing_date', '!=', False),
            ('next_billing_date', '<=', today),
        ])
        for contract in contracts:
            guard = 0
            while (contract.state == 'running'
                   and contract.next_billing_date
                   and contract.next_billing_date <= today
                   and (not contract.date_end
                        or contract.next_billing_date <= contract.date_end)
                   and guard < 36):
                try:
                    contract._create_period_invoice()
                except UserError:
                    break
                guard += 1
