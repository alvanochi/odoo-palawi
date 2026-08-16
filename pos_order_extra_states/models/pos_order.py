# -*- coding: utf-8 -*-
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


# Status memasak per baris pesanan.
#
# pos.order.state sengaja dibiarkan sepenuhnya bawaan Odoo. Modul ini pernah
# menambahkan processing/ready/delivered ke sana, dan konsekuensinya mahal:
# pos.order.write() bawaan menolak setiap perpindahan state keluar dari
# 'paid', sehingga modul harus mem-bypass seluruh rantai write() -- termasuk
# override modul lain -- dan setiap view atau filter Odoo yang mencari 'paid'
# kehilangan pesanan tersebut. Menyimpan progres dapur di baris menghapus
# kedua masalah itu sekaligus.
LINE_KITCHEN_STATES = [
    ('pending', 'Pending'),
    ('cooking', 'Cooking'),
    ('ready', 'Ready'),
    ('served', 'Served'),
]

# Perpindahan yang diizinkan per baris: tujuan -> status asal yang sah.
LINE_TRANSITIONS = {
    'cooking': ('pending',),
    'ready': ('cooking',),
    'served': ('ready',),
}

KDS_CHANNEL_PREFIX = 'pos_kds.'
KDS_NOTIFICATION_TYPE = 'pos_kds/update'


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Capability token untuk channel realtime. Payload bus hanya berisi ID dan
    # tipe perubahan (tanpa nama pelanggan/detail order), sedangkan isi antrean
    # tetap dilindungi endpoint REST.
    kds_realtime_token = fields.Char(
        string='KDS Realtime Token', default=lambda self: uuid.uuid4().hex,
        readonly=True, copy=False, index=True, groups='base.group_system')

    def _ensure_kds_realtime_token(self):
        for config in self:
            secure_config = config.sudo()
            if not secure_config.kds_realtime_token:
                secure_config.write({'kds_realtime_token': uuid.uuid4().hex})
        return True

    def _get_kds_realtime_channel(self):
        self.ensure_one()
        self._ensure_kds_realtime_token()
        return '%s%s' % (KDS_CHANNEL_PREFIX, self.sudo().kds_realtime_token)

    def _send_kds_realtime(self, event, payload=None):
        """Kirim invalidation event setelah transaksi berhasil commit.

        bus.bus sendiri menaruh record di precommit dan melakukan PostgreSQL
        NOTIFY pada postcommit, sehingga rollback tidak menghasilkan event
        palsu di layar dapur.
        """
        now = fields.Datetime.now()
        for config in self:
            message = {
                'event': event,
                'pos_config_id': config.id,
                'sent_at': now.isoformat(),
            }
            message.update(payload or {})
            self.env['bus.bus'].sudo()._sendone(
                config._get_kds_realtime_channel(),
                KDS_NOTIFICATION_TYPE,
                message,
            )
        return True

    def action_rotate_kds_realtime_token(self):
        """Putuskan subscriber lama dan buat capability channel baru."""
        self.write({'kds_realtime_token': uuid.uuid4().hex})
        return True


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _send_kds_realtime(self, event, changed_fields=None, line_ids=None):
        for order in self:
            config = order.session_id.config_id
            if not config:
                continue
            config._send_kds_realtime(event, {
                'order_id': order.id,
                'session_id': order.session_id.id,
                'order_state': order.state,
                'changed_fields': sorted(changed_fields or []),
                'line_ids': line_ids or [],
            })
        return True

    @api.model_create_multi
    def create(self, vals_list):
        # Order.create() juga membuat line. Tahan event line selama proses ini
        # agar satu checkout tidak membangunkan KDS berkali-kali.
        orders = super(PosOrder, self.with_context(
            kds_suppress_line_realtime=True)).create(vals_list)
        orders = orders.with_context(kds_suppress_line_realtime=False)
        orders._send_kds_realtime('order.created', changed_fields={'create'})
        return orders

    def write(self, vals):
        tracked = {
            'state', 'session_id', 'table_id', 'general_note',
            'partner_id', 'tracking_number', 'pos_reference',
        }
        changed = tracked.intersection(vals)
        result = super().write(vals)
        if changed and not self.env.context.get('kds_suppress_realtime'):
            event = 'order.state_changed' if 'state' in changed else 'order.updated'
            self._send_kds_realtime(event, changed_fields=changed)
        return result

    def unlink(self):
        snapshots = [(
            order.session_id.config_id,
            order.id,
            order.session_id.id,
            order.state,
        ) for order in self]
        result = super(PosOrder, self.with_context(
            kds_suppress_line_realtime=True)).unlink()
        for config, order_id, session_id, state in snapshots:
            if config:
                config._send_kds_realtime('order.deleted', {
                    'order_id': order_id,
                    'session_id': session_id,
                    'order_state': state,
                    'changed_fields': ['unlink'],
                    'line_ids': [],
                })
        return result


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    # Deliberately NOT required. A default covers every ORM create, but this
    # module runs alongside third-party POS modules that may build order lines
    # in ways we cannot see. A required field turns any such path into a hard
    # failure that blocks the cashier from creating an order at all -- far
    # worse than a line whose cooking status is simply unset. Code here treats
    # an empty value as 'pending'.
    kitchen_state = fields.Selection(
        LINE_KITCHEN_STATES, string='Kitchen Status', default='pending',
        copy=False, index=True,
        help='Cooking status of this dish. A multi-station kitchen finishes '
             'each dish at a different moment, so the status lives on the '
             'line rather than on the order.')

    cooking_started_at = fields.Datetime(
        string='Cooking Started At', readonly=True, copy=False,
        help='Starting point of the countdown on the kitchen display.')

    ready_at = fields.Datetime(
        string='Ready At', readonly=True, copy=False,
        help='When the dish was marked ready. Compared with '
             'cooking_started_at this gives the real cooking duration.')

    # Membedakan pengamatan manusia dari tebakan jam. Tanpa ini, estimasi
    # yang meleset akan tercatat seolah-olah fakta, dan estimated_time
    # tidak akan pernah bisa diperbaiki dari data lapangan.
    ready_source = fields.Selection(
        [('staff', 'Marked by Staff'), ('timer', 'Countdown Elapsed')],
        string='Ready Source', readonly=True, copy=False,
        help='Whether a human confirmed the dish was done, or a countdown '
             'simply ran out. An elapsed estimate is not proof the food is '
             'ready, so the two are recorded separately.')

    @api.model_create_multi
    def create(self, vals_list):
        """Baris reward lahir langsung 'served'.

        Potongan harga dan produk gratis tidak dimasak siapa pun, jadi kalau
        dibiarkan 'pending' ia akan menahan pesanannya di antrean dapur
        selamanya -- domain ('lines.kitchen_state', 'in', [...]) cocok begitu
        ADA satu baris yang belum selesai, dan baris promo tidak akan pernah
        selesai.
        """
        for vals in vals_list:
            if vals.get('is_reward_line') and not vals.get('kitchen_state'):
                vals['kitchen_state'] = 'served'
        lines = super().create(vals_list)
        if not self.env.context.get('kds_suppress_line_realtime'):
            for order in lines.mapped('order_id'):
                order._send_kds_realtime(
                    'line.created', changed_fields={'create'},
                    line_ids=lines.filtered(lambda line: line.order_id == order).ids)
        return lines

    def write(self, vals):
        tracked = {
            'kitchen_state', 'cooking_started_at', 'ready_at', 'ready_source',
            'qty', 'product_id', 'customer_note', 'note', 'full_product_name',
        }
        changed = tracked.intersection(vals)
        orders_and_lines = [
            (order, self.filtered(lambda line: line.order_id == order).ids)
            for order in self.mapped('order_id')
        ]
        result = super().write(vals)
        if changed and not self.env.context.get('kds_suppress_line_realtime'):
            event = (
                'line.kitchen_state_changed'
                if 'kitchen_state' in changed else 'line.updated'
            )
            for order, line_ids in orders_and_lines:
                order._send_kds_realtime(
                    event, changed_fields=changed, line_ids=line_ids)
        return result

    def unlink(self):
        orders_and_lines = [
            (order, self.filtered(lambda line: line.order_id == order).ids)
            for order in self.mapped('order_id')
        ]
        result = super().unlink()
        if not self.env.context.get('kds_suppress_line_realtime'):
            for order, line_ids in orders_and_lines:
                order._send_kds_realtime(
                    'line.deleted', changed_fields={'unlink'}, line_ids=line_ids)
        return result

    def set_kitchen_state(self, target, source='staff'):
        """Geser satu baris sepanjang pending -> cooking -> ready -> served."""
        if target not in LINE_TRANSITIONS:
            raise UserError(_(
                'Invalid kitchen state. Expected one of: %s',
                ', '.join(sorted(LINE_TRANSITIONS))))
        if source not in ('staff', 'timer'):
            raise UserError(_("Invalid source. Expected 'staff' or 'timer'."))

        allowed_from = LINE_TRANSITIONS[target]
        for line in self:
            # Empty reads as 'pending': a line created by a module that never
            # heard of this field has simply not been cooked yet.
            current = line.kitchen_state or 'pending'
            if current not in allowed_from:
                raise UserError(_(
                    'Line %(product)s cannot become %(target)s because its '
                    'kitchen state is %(current)s (should be %(allowed)s).',
                    product=line.full_product_name or line.product_id.display_name,
                    target=target, current=current,
                    allowed=' or '.join(allowed_from)))

            vals = {'kitchen_state': target}
            if target == 'cooking':
                vals['cooking_started_at'] = fields.Datetime.now()
            elif target == 'ready':
                vals['ready_at'] = fields.Datetime.now()
                vals['ready_source'] = source
            line.write(vals)
        return True

    def action_start_cooking(self):
        return self.set_kitchen_state('cooking')

    def action_mark_ready(self):
        return self.set_kitchen_state('ready')

    def action_mark_served(self):
        return self.set_kitchen_state('served')


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        for session in sessions:
            session.config_id._send_kds_realtime('session.created', {
                'session_id': session.id,
                'session_state': session.state,
            })
        return sessions

    def write(self, vals):
        changed = {'state', 'start_at', 'stop_at', 'config_id'}.intersection(vals)
        old_configs = self.mapped('config_id')
        result = super().write(vals)
        if changed and not self.env.context.get('kds_suppress_realtime'):
            configs = old_configs | self.mapped('config_id')
            for config in configs:
                related = self.filtered(lambda session: session.config_id == config)
                # Jika config_id berubah, subscriber config lama juga harus
                # refetch walaupun session sekarang sudah berada di config baru.
                config._send_kds_realtime('session.changed', {
                    'session_ids': related.ids or self.ids,
                    'session_id': related[:1].id if related else None,
                    'session_state': related[:1].state if related else None,
                    'changed_fields': sorted(changed),
                })
        return result
