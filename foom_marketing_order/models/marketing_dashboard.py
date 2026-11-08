# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import date, datetime, timedelta

from odoo import models, api, fields

REQUESTOR_LABELS = {
    'TM': 'Trade Marketing',
    'SL': 'Sales',
    'DM': 'Digital Marketing',
    'EV': 'Event/Marketing Lainnya',
    'HR': 'HR',
    'FS': 'Foom Store',
    'RD': 'Research & Development',
}

STATE_LABELS = {
    'draft': 'Draft',
    'submit': 'Submitted',
    'confirm': 'Confirmed',
    'reject': 'Rejected',
}

DELIVERY_LABELS = {
    'draft': 'Belum Kirim',
    'partially': 'Partially',
    'done': 'Done',
    'cancel': 'Cancelled',
}

MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
               'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']


class MarketingOrderDashboard(models.Model):
    _inherit = 'marketing.order'

    # ------------------------------------------------------------------
    # Domain dasar: mengikuti hak akses user, sama seperti action list.
    # Semua user boleh membuka dashboard, tapi hanya melihat data dari
    # company yang sedang aktif untuknya.
    # ------------------------------------------------------------------
    def _dashboard_base_domain(self, date_from=None, date_to=None):
        domain = [('warehouse_id.company_id', 'in', self.env.companies.ids)]
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to + ' 23:59:59'))
        return domain

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        """Semua angka dashboard dalam satu panggilan.

        Sengaja memakai search_read + agregasi Python, bukan read_group,
        supaya tidak bergantung pada signature read_group/_read_group yang
        berubah antar versi Odoo.
        """
        domain = self._dashboard_base_domain(date_from, date_to)

        orders = self.env['marketing.order'].search_read(
            domain,
            ['id', 'name', 'create_date', 'state', 'requestor', 'type_id',
             'analytic_id', 'amount_total', 'amount_total2', 'delivery_state',
             'warehouse_id'],
        )

        order_ids = [o['id'] for o in orders]

        # ---------------- KPI ----------------
        total_order = len(orders)
        total_value = sum(o['amount_total'] or 0.0 for o in orders)
        total_cost = sum(o['amount_total2'] or 0.0 for o in orders)
        confirmed = [o for o in orders if o['state'] == 'confirm']
        pending_delivery = len([
            o for o in confirmed
            if o['delivery_state'] in ('draft', 'partially')
        ])

        # ---------------- Tren bulanan (12 bulan terakhir dari data) -------
        monthly = defaultdict(lambda: {'count': 0, 'value': 0.0, 'cost': 0.0})
        for o in orders:
            created = o['create_date']
            if not created:
                continue
            if isinstance(created, str):
                created = fields.Datetime.from_string(created)
            key = (created.year, created.month)
            monthly[key]['count'] += 1
            monthly[key]['value'] += o['amount_total'] or 0.0
            monthly[key]['cost'] += o['amount_total2'] or 0.0

        trend = []
        for (year, month) in sorted(monthly.keys())[-12:]:
            bucket = monthly[(year, month)]
            trend.append({
                'label': '%s %s' % (MONTH_SHORT[month - 1], str(year)[-2:]),
                'year': year,
                'month': month,
                'count': bucket['count'],
                'value': bucket['value'],
                'cost': bucket['cost'],
            })

        # ---------------- Per Requestor ----------------
        by_requestor = defaultdict(lambda: {'count': 0, 'value': 0.0})
        for o in orders:
            key = o['requestor'] or False
            by_requestor[key]['count'] += 1
            by_requestor[key]['value'] += o['amount_total'] or 0.0
        requestor_rows = [{
            'key': k,
            'label': REQUESTOR_LABELS.get(k, 'Tidak diisi'),
            'count': v['count'],
            'value': v['value'],
        } for k, v in by_requestor.items()]
        requestor_rows.sort(key=lambda r: r['value'], reverse=True)

        # ---------------- Per Tipe ----------------
        by_type = defaultdict(lambda: {'count': 0, 'value': 0.0, 'id': False})
        for o in orders:
            tid = o['type_id'][0] if o['type_id'] else False
            label = o['type_id'][1] if o['type_id'] else 'Tidak diisi'
            by_type[label]['count'] += 1
            by_type[label]['value'] += o['amount_total'] or 0.0
            by_type[label]['id'] = tid
        type_rows = [{
            'id': v['id'],
            'label': k,
            'count': v['count'],
            'value': v['value'],
        } for k, v in by_type.items()]
        type_rows.sort(key=lambda r: r['value'], reverse=True)

        # ---------------- Status ----------------
        by_state = defaultdict(int)
        for o in orders:
            by_state[o['state']] += 1
        state_rows = [{
            'key': k,
            'label': STATE_LABELS.get(k, k),
            'count': v,
        } for k, v in by_state.items()]

        by_delivery = defaultdict(int)
        for o in confirmed:
            by_delivery[o['delivery_state'] or 'draft'] += 1
        delivery_rows = [{
            'key': k,
            'label': DELIVERY_LABELS.get(k, k),
            'count': v,
        } for k, v in by_delivery.items()]

        # ---------------- Per Analytic Account ----------------
        by_analytic = defaultdict(lambda: {'count': 0, 'value': 0.0, 'id': False})
        for o in orders:
            aid = o['analytic_id'][0] if o['analytic_id'] else False
            label = o['analytic_id'][1] if o['analytic_id'] else 'Tidak diisi'
            by_analytic[label]['count'] += 1
            by_analytic[label]['value'] += o['amount_total'] or 0.0
            by_analytic[label]['id'] = aid
        analytic_rows = [{
            'id': v['id'],
            'label': k,
            'count': v['count'],
            'value': v['value'],
        } for k, v in by_analytic.items()]
        analytic_rows.sort(key=lambda r: r['value'], reverse=True)
        analytic_rows = analytic_rows[:10]

        # ---------------- Top produk ----------------
        product_rows = []
        if order_ids:
            lines = self.env['marketing.order.line'].search_read(
                [('marketing_id', 'in', order_ids)],
                ['product_id', 'qty', 'subtotal', 'subtotal2'],
            )
            by_product = defaultdict(lambda: {'qty': 0.0, 'value': 0.0, 'cost': 0.0, 'id': False})
            for line in lines:
                if not line['product_id']:
                    continue
                pid, label = line['product_id']
                by_product[label]['qty'] += line['qty'] or 0.0
                by_product[label]['value'] += line['subtotal'] or 0.0
                by_product[label]['cost'] += line['subtotal2'] or 0.0
                by_product[label]['id'] = pid
            product_rows = [{
                'id': v['id'],
                'label': k,
                'qty': v['qty'],
                'value': v['value'],
                'cost': v['cost'],
            } for k, v in by_product.items()]
            product_rows.sort(key=lambda r: r['qty'], reverse=True)
            product_rows = product_rows[:10]

        return {
            'kpi': {
                'total_order': total_order,
                'total_value': total_value,
                'total_cost': total_cost,
                'pending_delivery': pending_delivery,
            },
            'trend': trend,
            'requestor': requestor_rows,
            'type': type_rows,
            'state': state_rows,
            'delivery': delivery_rows,
            'analytic': analytic_rows,
            'product': product_rows,
            'company_names': self.env.companies.mapped('display_name'),
            'date_from': date_from or False,
            'date_to': date_to or False,
        }

    @api.model
    def get_dashboard_domain(self, date_from=None, date_to=None, extra=None):
        """Dipakai tombol drill-down agar list yang dibuka memakai filter
        yang sama persis dengan dashboard."""
        domain = self._dashboard_base_domain(date_from, date_to)
        if extra:
            domain += extra
        return domain
