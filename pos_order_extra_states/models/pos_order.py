# -*- coding: utf-8 -*-
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
        return super().create(vals_list)

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
