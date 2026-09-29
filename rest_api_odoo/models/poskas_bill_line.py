from odoo import _, models, fields, api
from odoo.exceptions import UserError


# Status memasak per baris bill.
#
# Open bill tidak pernah menjadi pos.order sampai dibayar, sehingga dapur harus
# bisa bekerja langsung dari bill. Selection ini SENGAJA menyalin
# pos_order_extra_states.pos.order.line, bukan meng-import-nya: modul dapur itu
# opsional, dan rest_api_odoo harus tetap terpasang di database yang tidak
# memakainya. Nilai yang sama membuat KDS memperlakukan kedua sumber identik.
BILL_LINE_KITCHEN_STATES = [
    ('pending', 'Pending'),
    ('cooking', 'Cooking'),
    ('ready', 'Ready'),
    ('served', 'Served'),
]

# Perpindahan yang diizinkan per baris: tujuan -> status asal yang sah.
BILL_LINE_TRANSITIONS = {
    'cooking': ('pending',),
    'ready': ('cooking',),
    'served': ('ready',),
}

# Field dapur yang harus dibawa saat /api/pos/bill/upsert menulis ulang baris.
KITCHEN_FIELDS = ('kitchen_state', 'cooking_started_at', 'ready_at', 'ready_source')

# Field promo yang boleh dikirim klien pada tiap item upsert.
PROMO_FIELDS = ('reward_id', 'coupon_id', 'is_reward_line', 'reward_identifier_code')


class PoskasBillLine(models.Model):
    _name = "poskas.bill.line"
    _description = "POSKAS Bill Line"

    bill_id = fields.Many2one(
        "poskas.bill",
        required=True,
        ondelete="cascade",
        index=True
    )

    product_id = fields.Many2one(
        "product.product",
        required=True,
        index=True
    )

    qty = fields.Float(default=1.0)
    price_unit = fields.Float(default=0.0)
    note = fields.Char()

    discount_percent = fields.Float(
        string="Discount Percent",
        default=0.0
    )

    subtotal = fields.Float(
        compute="_compute_subtotal",
        store=True
    )

    # -- kitchen ----------------------------------------------------------
    #
    # Tidak required, sama seperti pos.order.line: baris yang dibuat modul lain
    # tanpa nilai ini harus tetap bisa lahir. Kosong dibaca sebagai 'pending'.
    kitchen_state = fields.Selection(
        BILL_LINE_KITCHEN_STATES, string='Kitchen Status', default='pending',
        copy=False, index=True,
        help='Status memasak hidangan ini. Dapur multi-stasiun menyelesaikan '
             'tiap hidangan pada waktu berbeda, jadi statusnya ada di baris.')

    cooking_started_at = fields.Datetime(
        string='Cooking Started At', readonly=True, copy=False,
        help='Titik awal hitung mundur pada layar dapur.')

    ready_at = fields.Datetime(
        string='Ready At', readonly=True, copy=False,
        help='Waktu hidangan ditandai siap.')

    ready_source = fields.Selection(
        [('staff', 'Marked by Staff'), ('timer', 'Countdown Elapsed')],
        string='Ready Source', readonly=True, copy=False,
        help='Ditandai petugas, atau sekadar hitung mundur yang habis. '
             'Estimasi yang habis bukan bukti makanan sudah jadi, jadi '
             'keduanya dicatat terpisah.')

    # -- promo ------------------------------------------------------------
    #
    # Open bill juga membawa promo: pelanggan melihat totalnya sebelum bayar.
    # Yang tidak bisa dilakukan bill adalah baris berharga negatif -- subtotal
    # di bawah ini menjepitnya ke nol -- jadi promo di tahap ini dinyatakan
    # sebagai diskon per baris (produk gratis = discount_percent 100), dan
    # field berikut mencatat promo MANA yang dipakai. Tanpa itu, identitas
    # programnya hilang sampai bill diubah menjadi pos.order.
    #
    # Relasi ke loyalty sengaja disimpan sebagai Integer, bukan Many2one:
    # field relasi akan menjadikan modul loyalty dependency rest_api_odoo,
    # dan mencabut loyalty berarti mematikan seluruh API POS.
    reward_id = fields.Integer(
        string='Loyalty Reward', index=True, copy=False,
        help='ID loyalty.reward yang menghasilkan baris ini.')

    coupon_id = fields.Integer(
        string='Loyalty Coupon', index=True, copy=False,
        help='ID loyalty.card yang dipakai pada baris ini.')

    is_reward_line = fields.Boolean(
        string='Is Reward Line', copy=False,
        help='Baris ini berasal dari promo, bukan pesanan pelanggan.')

    reward_identifier_code = fields.Char(
        string='Reward Code', copy=False,
        help='Pengelompokan baris reward, seperti di POS Odoo.')

    @api.depends("qty", "price_unit", "discount_percent")
    def _compute_subtotal(self):
        for line in self:
            qty = line.qty or 0.0
            price_unit = line.price_unit or 0.0
            discount_percent = line.discount_percent or 0.0

            if discount_percent < 0.0:
                discount_percent = 0.0
            if discount_percent > 100.0:
                discount_percent = 100.0

            price_after_discount = price_unit - (price_unit * discount_percent / 100.0)
            if price_after_discount < 0.0:
                price_after_discount = 0.0

            line.subtotal = qty * price_after_discount

    # -- realtime ---------------------------------------------------------

    def _notify_kds(self, event, changed_fields=None):
        """Beritahu KDS bahwa isi bill berubah.

        Hanya invalidation event: KDS tetap membaca antrean lewat REST, jadi
        event yang terlewat tidak merusak layar dapur.
        """
        if self.env.context.get('kds_suppress_line_realtime'):
            return True
        for bill in self.mapped('bill_id'):
            # Bill yang menempel pada pos.order hanyalah cermin dari pesanan
            # itu; KDS membacanya lewat pos.order dan menyaring bill-nya. Event
            # dari cermin cuma membuat layar dapur mengambil ulang data yang
            # tidak berubah, jadi tidak diterbitkan.
            if bill.pos_order_id:
                continue
            lines = self.filtered(lambda line: line.bill_id == bill)
            bill._send_kds_realtime(event, {
                'changed_fields': sorted(changed_fields or []),
                'line_ids': lines.ids,
            })
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Baris promo tidak dimasak siapa pun. Dibiarkan 'pending' ia akan
            # menahan bill-nya di antrean dapur selamanya, karena baris promo
            # tidak akan pernah ditandai selesai.
            if vals.get('is_reward_line') and not vals.get('kitchen_state'):
                vals['kitchen_state'] = 'served'
        lines = super().create(vals_list)
        lines._notify_kds('bill.line.created', {'create'})
        return lines

    def write(self, vals):
        tracked = {
            'kitchen_state', 'cooking_started_at', 'ready_at', 'ready_source',
            'qty', 'product_id', 'note', 'price_unit', 'discount_percent',
            'is_reward_line', 'reward_id',
        }
        changed = tracked.intersection(vals)
        result = super().write(vals)
        if changed:
            event = (
                'bill.line.kitchen_state_changed'
                if 'kitchen_state' in changed else 'bill.line.updated'
            )
            self._notify_kds(event, changed)
        return result

    def unlink(self):
        # Satu event per bill, bukan per baris: menghapus keranjang delapan item
        # tidak boleh membuat layar dapur mengambil ulang antrean delapan kali.
        snapshots = {}
        for line in self:
            snapshots.setdefault(line.bill_id, []).append(line.id)
        result = super().unlink()
        if not self.env.context.get('kds_suppress_line_realtime'):
            for bill, line_ids in snapshots.items():
                if bill.exists() and not bill.pos_order_id:
                    bill._send_kds_realtime('bill.line.deleted', {
                        'changed_fields': ['unlink'],
                        'line_ids': line_ids,
                    })
        return result

    # -- kitchen workflow -------------------------------------------------

    def set_kitchen_state(self, target, source='staff'):
        """Geser satu baris sepanjang pending -> cooking -> ready -> served."""
        if target not in BILL_LINE_TRANSITIONS:
            raise UserError(_(
                'Invalid kitchen state. Expected one of: %s',
                ', '.join(sorted(BILL_LINE_TRANSITIONS))))
        if source not in ('staff', 'timer'):
            raise UserError(_("Invalid source. Expected 'staff' or 'timer'."))

        allowed_from = BILL_LINE_TRANSITIONS[target]
        for line in self:
            # Kosong dibaca 'pending': baris yang dibuat sebelum field ini ada
            # memang belum pernah dimasak.
            current = line.kitchen_state or 'pending'
            if current not in allowed_from:
                raise UserError(_(
                    'Bill line %(product)s cannot become %(target)s because its '
                    'kitchen state is %(current)s (should be %(allowed)s).',
                    product=line.product_id.display_name,
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

    def kitchen_snapshot(self):
        """Nilai dapur baris ini, untuk dipulihkan setelah upsert menulis ulang.

        kitchen_state dinormalkan ke 'pending' supaya baris warisan yang masih
        NULL tidak ditulis ulang sebagai NULL -- nilai itu melewati default
        kolom, dan hanya menyisakan status kosong yang harus terus dijaga
        pembacanya.
        """
        self.ensure_one()
        snapshot = {field: self[field] for field in KITCHEN_FIELDS}
        snapshot['kitchen_state'] = snapshot.get('kitchen_state') or 'pending'
        return snapshot
