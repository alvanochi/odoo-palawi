# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Bhagyadev KP (<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
import io
import json
import xlsxwriter
from odoo import api, fields, models


class AgePayableReport(models.TransientModel):
    """For creating Age Payable report"""
    _name = 'age.payable.report'
    _description = 'Aged Payable Report'

    @api.model
    def view_report(self):
        """
        Generate a report with move line data categorized by partner and credit
        difference.
        Returns:
            dict: Dictionary containing move line data categorized by partner
                  names. Each partner's data includes credit amounts and credit
                  differences based on days between maturity date and today. The
                  'partner_totals' key contains summary data for each partner.
        """
        partner_total = {}
        move_line_list = {}
        paid = self.env['account.move.line'].search(
            [('parent_state', '=', 'posted'),
             ('account_type', '=', 'liability_payable'),
             ('reconciled', '=', False)])
        paid = paid.filtered(
            lambda l: abs(l.amount_residual_currency or l.amount_residual) > 0.00001
        )
        currency_id = self.env.company.currency_id.symbol
        partner_groups = [
            {
                'id': partner.id,
                'name': partner.display_name,
            }
            for partner in paid.mapped('partner_id')
        ]

        # Tambahkan kelompok khusus untuk journal item tanpa partner.
        if paid.filtered(lambda line: not line.partner_id):
            partner_groups.append({
                'id': False,
                'name': 'Unknown Partner',
            })

        today = fields.Date.today()

        for partner_group in partner_groups:
            partner_id = partner_group['id']
            partner_name = partner_group['name']

            move_line_ids = paid.filtered(
                lambda line: line.partner_id.id == partner_id
            )

            # Memasukkan field 'debit' ke dalam read()
            move_line_data = move_line_ids.read([
                'id',
                'name',
                'move_name',
                'date',
                'amount_currency',
                'amount_residual',
                'amount_residual_currency',
                'account_id',
                'date_maturity',
                'currency_id',
                'debit',
                'credit',
                'move_id',
            ])

            for val in move_line_data:
                maturity_date = val['date_maturity'] or val['date']
                difference = (today - maturity_date).days

                # Hitung net_amount: Jika debit lebih besar (pengurang), hasilnya otomatis minus (-)
                currency = val.get('currency_id')

                if currency and currency[0] != self.env.company.currency_id.id:
                    net_amount = val.get('amount_residual_currency', 0.0)
                else:
                    net_amount = val.get('amount_residual', 0.0)
                
                val['diff0'] = net_amount if difference <= 0 else 0.0
                val['diff1'] = net_amount if 0 < difference <= 30 else 0.0
                val['diff2'] = net_amount if 30 < difference <= 60 else 0.0
                val['diff3'] = net_amount if 60 < difference <= 90 else 0.0
                val['diff4'] = net_amount if 90 < difference <= 120 else 0.0
                val['diff5'] = net_amount if difference > 120 else 0.0
                
                # Teruskan nilai debit & credit asli ke dictionary agar dibaca oleh fungsi Excel
                val['debit_val'] = val['debit']
                val['credit_val'] = val['credit']

            move_line_list[partner_name] = move_line_data

            # Update kalkulasi sum menggunakan logika (credit - debit)
            partner_total[partner_name] = {
                'credit_sum': sum(
                    val.get('amount_residual_currency')
                    if val.get('currency_id')
                    else val.get('amount_residual')
                    for val in move_line_data
                ),
                'diff0_sum': round(
                    sum(val['diff0'] for val in move_line_data), 2
                ),
                'diff1_sum': round(
                    sum(val['diff1'] for val in move_line_data), 2
                ),
                'diff2_sum': round(
                    sum(val['diff2'] for val in move_line_data), 2
                ),
                'diff3_sum': round(
                    sum(val['diff3'] for val in move_line_data), 2
                ),
                'diff4_sum': round(
                    sum(val['diff4'] for val in move_line_data), 2
                ),
                'diff5_sum': round(
                    sum(val['diff5'] for val in move_line_data), 2
                ),
                'currency_id': currency_id,
                'partner_id': partner_id,
            }
        
        move_line_list['partner_totals'] = partner_total
        return move_line_list
    
    

    @api.model
    def get_filter_values(self, date, partner):
        """
        Retrieve filtered move line data based on date and partner(s).
        """
        partner_total = {}
        move_line_list = {}

        domain = [
            ('parent_state', '=', 'posted'),
            ('account_type', '=', 'liability_payable'),
            ('reconciled', '=', False),
            ('company_id', '=', self.env.company.id),
        ]

        if date:
            domain.append(('date', '<=', date))

        # Gunakan domain yang sudah dibuat
        paid = self.env['account.move.line'].search(domain)
        paid = paid.filtered(
            lambda l: abs(l.amount_residual_currency or l.amount_residual) > 0.00001
        )
        currency_id = self.env.company.currency_id.symbol

        if partner:
            partner_records = self.env['res.partner'].search([
                ('id', 'in', partner)
            ])

            partner_groups = [
                {
                    'id': partner_rec.id,
                    'name': partner_rec.display_name,
                }
                for partner_rec in partner_records
            ]
        else:
            partner_groups = [
                {
                    'id': partner_rec.id,
                    'name': partner_rec.display_name,
                }
                for partner_rec in paid.mapped('partner_id')
            ]

            if paid.filtered(lambda line: not line.partner_id):
                partner_groups.append({
                    'id': False,
                    'name': 'Unknown Partner',
                })

        report_date = fields.Date.to_date(date) if date else fields.Date.today()

        for partner_group in partner_groups:
            partner_id = partner_group['id']
            partner_name = partner_group['name']

            move_line_ids = paid.filtered(
                lambda line: line.partner_id.id == partner_id
            )

            move_line_data = move_line_ids.read([
                'id',
                'name',
                'move_name',
                'date',
                'amount_currency',
                'amount_residual',
                'amount_residual_currency',
                'account_id',
                'date_maturity',
                'currency_id',
                'debit',
                'credit',
                'move_id',
            ])

            for val in move_line_data:
                maturity_date = val['date_maturity'] or val['date']
                maturity_date = fields.Date.to_date(maturity_date)

                difference = (report_date - maturity_date).days

                currency = val.get('currency_id')

                if currency and currency[0] != self.env.company.currency_id.id:
                    net_amount = val.get('amount_residual_currency', 0.0)
                else:
                    net_amount = val.get('amount_residual', 0.0)


                val['diff0'] = net_amount if difference <= 0 else 0.0
                val['diff1'] = net_amount if 0 < difference <= 30 else 0.0
                val['diff2'] = net_amount if 30 < difference <= 60 else 0.0
                val['diff3'] = net_amount if 60 < difference <= 90 else 0.0
                val['diff4'] = net_amount if 90 < difference <= 120 else 0.0
                val['diff5'] = net_amount if difference > 120 else 0.0

            move_line_list[partner_name] = move_line_data

            partner_total[partner_name] = {
                'credit_sum': sum(
                    val.get('amount_residual_currency')
                    if val.get('currency_id')
                    else val.get('amount_residual')
                    for val in move_line_data
                ),
                'diff0_sum': round(sum(val['diff0'] for val in move_line_data), 2),
                'diff1_sum': round(sum(val['diff1'] for val in move_line_data), 2),
                'diff2_sum': round(sum(val['diff2'] for val in move_line_data), 2),
                'diff3_sum': round(sum(val['diff3'] for val in move_line_data), 2),
                'diff4_sum': round(sum(val['diff4'] for val in move_line_data), 2),
                'diff5_sum': round(sum(val['diff5'] for val in move_line_data), 2),
                'currency_id': currency_id,
                'partner_id': partner_id,
            }

        move_line_list['partner_totals'] = partner_total
        return move_line_list
    
    
    @api.model
    def get_xlsx_report(self, data, response, report_name, report_action):
        """
        Generate an Excel report based on the provided data.
        """
        data = json.loads(data)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        end_date = data['filters']['end_date'] if \
            data['filters']['end_date'] else ''
        sheet = workbook.add_worksheet()
        head = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '15px'})
        sub_heading = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px',
             'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_head = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px',
             'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_body = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px'})
        side_heading_sub = workbook.add_format(
            {'align': 'left', 'bold': True, 'font_size': '10px',
             'border': 1,
             'border_color': 'black'})
        side_heading_sub.set_indent(1)
        txt_name = workbook.add_format({'font_size': '10px', 'border': 1})
        txt_name.set_indent(2)
        
        sheet.set_column(5, 5, 12)   # Currency
        sheet.set_column(6, 7, 25)   # Account
        sheet.set_column(8, 9, 15)   # Expected Date
        sheet.set_column(10, 16, 15) # Aging + Total
        
        col = 0
        sheet.write('A1:b1', report_name, head)
        sheet.write('B3:b4', 'Date Range', filter_head)
        sheet.write('B4:b4', 'Partners', filter_head)
        if end_date:
            sheet.merge_range('C3:G3', f"{end_date}", filter_body)
        if data['filters']['partner']:
            display_names = [partner.get('display_name', 'undefined') for
                             partner in data['filters']['partner']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C4:G4', display_names_str, filter_body)
            
        if data:
            if report_action == 'dynamic_accounts_report.action_aged_payable':
                sheet.write(6, col, 'Partner / Vendor', sub_heading)
                sheet.write(6, col + 1, 'Bill Number / Memo', sub_heading)
                sheet.write(6, col + 2, 'Invoice Date', sub_heading)
                sheet.write(6, col + 3, 'Due Date', sub_heading)
                sheet.write(6, col + 4, 'Amount Currency', sub_heading)
                sheet.write(6, col + 5, 'Currency', sub_heading)
                sheet.merge_range(6, col + 6, 6, col + 7, 'Account', sub_heading)
                sheet.merge_range(6, col + 8, 6, col + 9, 'Expected Date', sub_heading)
                sheet.write(6, col + 10, 'At Date', sub_heading)
                sheet.write(6, col + 11, '1-30', sub_heading)
                sheet.write(6, col + 12, '31-60', sub_heading)
                sheet.write(6, col + 13, '61-90', sub_heading)
                sheet.write(6, col + 14, '91-120', sub_heading)
                sheet.write(6, col + 15, 'Older', sub_heading)
                sheet.write(6, col + 16, 'Total', sub_heading)
         
                row = 6
                for move_line in data['move_lines']:
                    for rec in data['data'][move_line]:
                   
                            
                        row += 1

                        amt_currency = (
                            rec.get('amount_residual_currency')
                            if rec.get('currency_id')
                            else rec.get('amount_residual', 0.0)
                        )

                        # Ambil breakdown
                        diff0 = float(rec.get('diff0', 0.0))
                        diff1 = float(rec.get('diff1', 0.0))
                        diff2 = float(rec.get('diff2', 0.0))
                        diff3 = float(rec.get('diff3', 0.0))
                        diff4 = float(rec.get('diff4', 0.0))
                        diff5 = float(rec.get('diff5', 0.0))

                        # Jika backend masih mengirim breakdown positif tetapi amount_currency negatif,
                        # balik seluruh bucket menjadi negatif.
                        if amt_currency < 0:
                            diff0 = -abs(diff0)
                            diff1 = -abs(diff1)
                            diff2 = -abs(diff2)
                            diff3 = -abs(diff3)
                            diff4 = -abs(diff4)
                            diff5 = -abs(diff5)

                        line_total = (
                            diff0 +
                            diff1 +
                            diff2 +
                            diff3 +
                            diff4 +
                            diff5
                        )

                        sheet.write(row, col, move_line, txt_name)
                        sheet.write(row, col + 1, (rec.get('move_name') or '') + (rec.get('name') or ''), txt_name)
                        sheet.write(row, col + 2, rec.get('date'), txt_name)                
                        sheet.write(row, col + 3, rec.get('date_maturity') or '', txt_name)  
                        sheet.write(row, col + 4, amt_currency, txt_name)                   

                        sheet.write(
                            row,
                            col + 5,
                            rec['currency_id'][1] if rec.get('currency_id') else '',
                            txt_name
                        )

                        sheet.merge_range(
                            row,
                            col + 6,
                            row,
                            col + 7,
                            rec['account_id'][1] if rec.get('account_id') else '',
                            txt_name
                        )

                        sheet.merge_range(
                            row,
                            col + 8,
                            row,
                            col + 9,
                            rec.get('expected_date') or '',
                            txt_name
                        )

                        sheet.write(row, col + 10, diff0, txt_name)
                        sheet.write(row, col + 11, diff1, txt_name)
                        sheet.write(row, col + 12, diff2, txt_name)
                        sheet.write(row, col + 13, diff3, txt_name)
                        sheet.write(row, col + 14, diff4, txt_name)
                        sheet.write(row, col + 15, diff5, txt_name)
                        sheet.write(row, col + 16, line_total, txt_name)
           
                # Baris Grand Total
                sheet.merge_range(row + 1, col, row + 1, col + 9, 'Total', filter_head)

                sheet.write(row + 1, col + 10, data['grand_total']['diff0_sum'], filter_head)
                sheet.write(row + 1, col + 11, data['grand_total']['diff1_sum'], filter_head)
                sheet.write(row + 1, col + 12, data['grand_total']['diff2_sum'], filter_head)
                sheet.write(row + 1, col + 13, data['grand_total']['diff3_sum'], filter_head)
                sheet.write(row + 1, col + 14, data['grand_total']['diff4_sum'], filter_head)
                sheet.write(row + 1, col + 15, data['grand_total']['diff5_sum'], filter_head)
                sheet.write(row + 1, col + 16, data['grand_total']['total_credit'], filter_head)
                
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()