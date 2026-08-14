# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

# Orders counted as sales: everything except draft and cancelled.
# "not in" is used on purpose so the dashboard stays compatible with modules
# that add extra states to pos.order (processing / ready / delivered, ...).
SALE_STATES_EXCLUDED = ('draft', 'cancel')


class PosPerformanceDashboard(models.TransientModel):
    _name = 'pos.performance.dashboard'
    _description = 'POS Performance Dashboard'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_tz(self):
        return pytz.timezone(self.env.user.tz or 'UTC')

    def _bounds(self, date_from, date_to):
        """Local dates (YYYY-MM-DD) -> naive UTC datetime bounds."""
        tz = self._get_tz()
        start = tz.localize(datetime.combine(date_from, time.min))
        end = tz.localize(datetime.combine(date_to, time.max))
        return (start.astimezone(pytz.UTC).replace(tzinfo=None),
                end.astimezone(pytz.UTC).replace(tzinfo=None))

    def _parse_dates(self, date_from, date_to):
        d_from = fields.Date.to_date(date_from) or fields.Date.today()
        d_to = fields.Date.to_date(date_to) or fields.Date.today()
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        return d_from, d_to

    def _order_domain(self, dt_from, dt_to, config_ids):
        domain = [
            ('state', 'not in', SALE_STATES_EXCLUDED),
            ('date_order', '>=', dt_from),
            ('date_order', '<=', dt_to),
            ('company_id', 'in', self.env.companies.ids),
        ]
        if config_ids:
            domain.append(('config_id', 'in', config_ids))
        return domain

    def _line_domain(self, dt_from, dt_to, config_ids):
        domain = [
            ('order_id.state', 'not in', SALE_STATES_EXCLUDED),
            ('order_id.date_order', '>=', dt_from),
            ('order_id.date_order', '<=', dt_to),
            ('order_id.company_id', 'in', self.env.companies.ids),
        ]
        if config_ids:
            domain.append(('order_id.config_id', 'in', config_ids))
        return domain

    def _payment_domain(self, dt_from, dt_to, config_ids):
        domain = [
            ('pos_order_id.state', 'not in', SALE_STATES_EXCLUDED),
            ('pos_order_id.date_order', '>=', dt_from),
            ('pos_order_id.date_order', '<=', dt_to),
            ('pos_order_id.company_id', 'in', self.env.companies.ids),
        ]
        if config_ids:
            domain.append(('pos_order_id.config_id', 'in', config_ids))
        return domain

    def _sum_sales(self, d_from, d_to, config_ids):
        dt_from, dt_to = self._bounds(d_from, d_to)
        rows = self.env['pos.order']._read_group(
            self._order_domain(dt_from, dt_to, config_ids), [],
            ['amount_total:sum', '__count'])
        amount, count = rows[0] if rows else (0.0, 0)
        return (amount or 0.0), count

    @staticmethod
    def _growth(current, previous):
        if previous:
            return round((current - previous) / abs(previous) * 100.0, 1)
        return 100.0 if current else 0.0

    def _configs(self, config_ids):
        if config_ids:
            return self.env['pos.config'].browse(config_ids).exists()
        return self.env['pos.config'].search(
            [('company_id', 'in', self.env.companies.ids)])

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _get_kpi(self, d_from, d_to, order_domain, line_domain, config_ids,
                 days):
        Order = self.env['pos.order']
        rows = Order._read_group(
            order_domain, [],
            ['amount_total:sum', '__count', 'partner_id:count_distinct'])
        total_sales, total_orders, total_customers = rows[0] if rows \
            else (0.0, 0, 0)
        total_sales = total_sales or 0.0
        refunds = Order._read_group(
            order_domain + [('amount_total', '<', 0)], [],
            ['amount_total:sum', '__count'])
        refund_amount, refund_count = refunds[0] if refunds else (0.0, 0)
        lines = self.env['pos.order.line']._read_group(
            line_domain, [], ['qty:sum'])
        items_sold = (lines[0][0] if lines else 0.0) or 0.0

        # Growth vs the immediately preceding period of the same length.
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=days - 1)
        prev_sales, _prev_orders = self._sum_sales(
            prev_from, prev_to, config_ids)

        # Month over month: this month up to today vs the same slice of the
        # previous month.
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        prev_month_start = month_start - relativedelta(months=1)
        prev_month_end = min(
            prev_month_start + relativedelta(day=today.day),
            month_start - timedelta(days=1))
        mtd_sales, _c = self._sum_sales(month_start, today, config_ids)
        prev_mtd_sales, _c = self._sum_sales(
            prev_month_start, prev_month_end, config_ids)

        target = sum(self._configs(config_ids).mapped(
            'daily_sales_target')) * days
        return {
            'total_sales': total_sales,
            'total_orders': total_orders,
            'average_order': total_sales / total_orders if total_orders else 0.0,
            'total_customers': total_customers or 0,
            'items_sold': items_sold,
            'refund_amount': abs(refund_amount or 0.0),
            'refund_count': refund_count,
            'target_amount': target,
            'target_achievement': round(total_sales / target * 100, 1)
            if target else 0.0,
            'growth': self._growth(total_sales, prev_sales),
            'mom_growth': self._growth(mtd_sales, prev_mtd_sales),
        }

    def _get_sales_trend(self, order_domain):
        rows = self.env['pos.order']._read_group(
            order_domain, ['date_order:day'],
            ['amount_total:sum', '__count'], order='date_order:day')
        labels, sales, orders = [], [], []
        for day, amount, count in rows:
            if not day:
                labels.append('')
            else:
                value = day.date() if isinstance(day, datetime) else day
                labels.append(fields.Date.to_string(value))
            sales.append(round(amount or 0.0, 2))
            orders.append(count)
        return {'labels': labels, 'sales': sales, 'orders': orders}

    def _get_sales_by_hour(self, order_domain):
        rows = self.env['pos.order']._read_group(
            order_domain, ['date_order:hour_number'],
            ['amount_total:sum', '__count'])
        sales_by_hour, orders_by_hour = {}, {}
        for hour, amount, count in rows:
            if hour is None:
                continue
            sales_by_hour[int(hour)] = round(amount or 0.0, 2)
            orders_by_hour[int(hour)] = count
        return {
            'labels': ['%02d:00' % h for h in range(24)],
            'sales': [sales_by_hour.get(h, 0.0) for h in range(24)],
            'orders': [orders_by_hour.get(h, 0) for h in range(24)],
        }

    def _get_payment_methods(self, payment_domain):
        rows = self.env['pos.payment']._read_group(
            payment_domain, ['payment_method_id'],
            ['amount:sum', '__count'], order='amount:sum desc')
        methods = [{
            'id': method.id,
            'name': method.display_name,
            'amount': round(amount or 0.0, 2),
            'count': count,
        } for method, amount, count in rows]
        total = sum(m['amount'] for m in methods)
        for method in methods:
            method['percentage'] = round(method['amount'] / total * 100, 1) \
                if total else 0.0
        return methods

    def _get_top_products(self, line_domain, limit=5):
        rows = self.env['pos.order.line']._read_group(
            line_domain, ['product_id'],
            ['qty:sum', 'price_subtotal_incl:sum'],
            order='price_subtotal_incl:sum desc', limit=limit)
        return [{
            'id': product.id,
            'name': product.display_name,
            'qty': round(qty or 0.0, 2),
            'amount': round(amount or 0.0, 2),
        } for product, qty, amount in rows]

    def _get_top_categories(self, line_domain, limit=8):
        rows = self.env['pos.order.line']._read_group(
            line_domain, ['product_id'], ['price_subtotal_incl:sum'])
        by_category = {}
        for product, amount in rows:
            category = product.categ_id
            key = (category.id, category.display_name or 'N/A')
            by_category[key] = by_category.get(key, 0.0) + (amount or 0.0)
        items = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        return [{'id': key[0], 'name': key[1], 'amount': round(value, 2)}
                for key, value in items[:limit]]

    def _get_top_customers(self, order_domain, limit=5):
        rows = self.env['pos.order']._read_group(
            order_domain + [('partner_id', '!=', False)], ['partner_id'],
            ['amount_total:sum', '__count'],
            order='amount_total:sum desc', limit=limit)
        return [{
            'id': partner.id,
            'name': partner.display_name,
            'amount': round(amount or 0.0, 2),
            'count': count,
        } for partner, amount, count in rows]

    def _get_cashiers(self, order_domain, limit=6):
        rows = self.env['pos.order']._read_group(
            order_domain + [('user_id', '!=', False)], ['user_id'],
            ['amount_total:sum', '__count'],
            order='amount_total:sum desc', limit=limit)
        cashiers = [{
            'id': user.id,
            'name': user.display_name,
            'initial': (user.display_name or '?')[0].upper(),
            'amount': round(amount or 0.0, 2),
            'count': count,
        } for user, amount, count in rows]
        best = max([c['amount'] for c in cashiers], default=0.0)
        for cashier in cashiers:
            cashier['share'] = round(cashier['amount'] / best * 100, 1) \
                if best else 0.0
        return cashiers

    def _get_stores(self, order_domain, days):
        configs = self.env['pos.config'].search(
            [('company_id', 'in', self.env.companies.ids)])
        rows = self.env['pos.order']._read_group(
            order_domain, ['config_id'], ['amount_total:sum', '__count'])
        stats = {config.id: (amount or 0.0, count)
                 for config, amount, count in rows}
        open_sessions = self.env['pos.session'].search([
            ('config_id', 'in', configs.ids), ('state', '!=', 'closed')])
        open_by_config = {s.config_id.id: s.name for s in open_sessions}
        stores = []
        for config in configs:
            amount, count = stats.get(config.id, (0.0, 0))
            target = config.daily_sales_target * days
            stores.append({
                'id': config.id,
                'name': config.name,
                'company': config.company_id.display_name,
                'sales': round(amount, 2),
                'orders': count,
                'target': round(target, 2),
                'achievement': round(amount / target * 100, 1) if target
                else 0.0,
                'session': open_by_config.get(config.id, ''),
            })
        return sorted(stores, key=lambda s: s['sales'], reverse=True)

    def _format_duration(self, start, end):
        if not start:
            return '-'
        delta = (end or fields.Datetime.now()) - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        return '%dh %02dm' % (hours, minutes)

    def _get_session_stock(self, config_ids, kpi, dt_from, dt_to):
        """Panel Session & Stock: sesi terakhir + ringkasan angka."""
        domain = [('company_id', 'in', self.env.companies.ids)]
        if config_ids:
            domain.append(('config_id', 'in', config_ids))
        session = self.env['pos.session'].search(
            domain, order='start_at desc', limit=1)
        return {
            'session_id': session.id,
            'session_name': session.name or '',
            'state': session.state or 'none',
            'duration': self._format_duration(session.start_at,
                                              session.stop_at)
            if session else '-',
            'cash_difference': session.cash_register_difference
            if session else 0.0,
            'stock_sold': kpi['items_sold'],
            'average_order': kpi['average_order'],
            'total_revenue': kpi['total_sales'],
        }

    def _get_recent_sessions(self, config_ids, limit=8):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if config_ids:
            domain.append(('config_id', 'in', config_ids))
        sessions = self.env['pos.session'].search(
            domain, order='start_at desc', limit=limit)
        rows = self.env['pos.order']._read_group(
            [('session_id', 'in', sessions.ids),
             ('state', 'not in', SALE_STATES_EXCLUDED)],
            ['session_id'], ['amount_total:sum', '__count'])
        stats = {session.id: (amount or 0.0, count)
                 for session, amount, count in rows}
        result = []
        for session in sessions:
            amount, count = stats.get(session.id, (0.0, 0))
            result.append({
                'id': session.id,
                'name': session.name,
                'config': session.config_id.name,
                'state': session.state,
                'start_at': fields.Datetime.to_string(session.start_at) or '',
                'sales': round(amount, 2),
                'orders': count,
            })
        return result

    def _get_out_of_stock(self, limit=8):
        Product = self.env['product.product']
        if 'is_storable' not in Product._fields:
            return {'count': 0, 'products': []}
        domain = [
            ('available_in_pos', '=', True),
            ('is_storable', '=', True),
            ('qty_available', '<=', 0),
        ]
        products = Product.search(domain, limit=limit)
        return {
            'count': Product.search_count(domain),
            'products': [{
                'id': product.id,
                'name': product.display_name,
                'qty': product.qty_available,
                'barcode': product.barcode or '',
            } for product in products],
        }

    # ------------------------------------------------------------------
    # Public API called from the dashboard (JS)
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None,
                           config_ids=None):
        config_ids = [int(c) for c in (config_ids or [])]
        d_from, d_to = self._parse_dates(date_from, date_to)
        dt_from, dt_to = self._bounds(d_from, d_to)
        days = (d_to - d_from).days + 1
        order_domain = self._order_domain(dt_from, dt_to, config_ids)
        line_domain = self._line_domain(dt_from, dt_to, config_ids)
        payment_domain = self._payment_domain(dt_from, dt_to, config_ids)
        kpi = self._get_kpi(d_from, d_to, order_domain, line_domain,
                            config_ids, days)
        selected = self._configs(config_ids) if config_ids \
            else self.env['pos.config']
        all_configs = self.env['pos.config'].search(
            [('company_id', 'in', self.env.companies.ids)])
        return {
            'currency_id': self.env.company.currency_id.id,
            'date_from': fields.Date.to_string(d_from),
            'date_to': fields.Date.to_string(d_to),
            'days': days,
            'store': {
                'id': selected[:1].id,
                'name': selected[:1].name or '',
                'company': selected[:1].company_id.display_name or '',
            } if len(selected) == 1 else None,
            'kpi': kpi,
            'active_sessions': self.env['pos.session'].search_count([
                ('config_id', 'in', all_configs.ids),
                ('state', '=', 'opened')]),
            'out_of_stock': self._get_out_of_stock(),
            'session_stock': self._get_session_stock(
                config_ids, kpi, dt_from, dt_to),
            'sales_trend': self._get_sales_trend(order_domain),
            'sales_by_hour': self._get_sales_by_hour(order_domain),
            'payment_methods': self._get_payment_methods(payment_domain),
            'top_products': self._get_top_products(line_domain),
            'top_categories': self._get_top_categories(line_domain),
            'top_customers': self._get_top_customers(order_domain),
            'cashiers': self._get_cashiers(order_domain),
            'stores': self._get_stores(order_domain, days),
            'recent_sessions': self._get_recent_sessions(config_ids),
            'all_configs': [{
                'id': config.id,
                'name': config.name,
                'company': config.company_id.display_name,
            } for config in all_configs],
        }

    @api.model
    def get_order_domain(self, date_from=None, date_to=None, config_ids=None,
                         extra_domain=None):
        """Domain used for drill-down from the dashboard to POS Orders."""
        config_ids = [int(c) for c in (config_ids or [])]
        d_from, d_to = self._parse_dates(date_from, date_to)
        dt_from, dt_to = self._bounds(d_from, d_to)
        domain = self._order_domain(dt_from, dt_to, config_ids)
        # Datetimes must be sent as strings to survive JSON-RPC.
        domain = [(field, operator, fields.Datetime.to_string(value)
                   if isinstance(value, datetime) else value)
                  for field, operator, value in domain]
        return domain + (extra_domain or [])
