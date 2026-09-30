# -*- coding: utf-8 -*-
"""Antrean dapur yang berasal dari open bill (poskas.bill).

Open bill BELUM membuat pos.order: kasir baru menahan pesanan di meja. Dapur
tetap harus memasaknya, jadi baris bill dibaca ke bentuk entity yang sama
dengan pos.order dan diberi flag source='bill'. Frontend memakai flag itu untuk
membedakan UX -- misalnya menandai bahwa isinya masih bisa berubah sampai
kasir checkout.

Model poskas.bill dimiliki modul rest_api_odoo. Modul itu sengaja TIDAK
didaftarkan sebagai dependency (lihat catatan di __manifest__.py), jadi setiap
pembacaan di sini dijaga is_available(): bila modulnya tidak terpasang,
endpoint dapur tetap melayani pos.order seperti biasa.
"""
from datetime import timedelta

from odoo.exceptions import UserError

from ..domain.entities.pos_order import PosOrderEntity, PosOrderLineEntity
from .pos_order_repository import PosOrderRepository

# Bill yang masih ditunggu dapur. 'paid'/'cancel' sudah selesai atau dibatalkan.
BILL_STATES = ['open']

BILL_MODEL = 'poskas.bill'


class PoskasBillRepository:
    """Baca open bill sebagai pesanan dapur, dan geser status memasak barisnya."""

    def __init__(self, env):
        self.env = env

    def is_available(self):
        return BILL_MODEL in self.env

    # -- serialisation ----------------------------------------------------

    @staticmethod
    def _iso(value):
        return value.isoformat() if value else None

    def _line_entity(self, line):
        product = line.product_id
        template = product.product_tmpl_id
        # estimated_time berasal dari addon product_estimated_time; dijaga
        # kalau addon itu tidak terpasang di suatu database.
        estimated_time = getattr(template, 'estimated_time', 0) or 0

        return PosOrderLineEntity(
            id=line.id,
            source='bill',
            product_id=product.id,
            product_tmpl_id=template.id if template else False,
            product_name=product.name,
            full_product_name=product.display_name,
            qty=line.qty,
            price_unit=line.price_unit,
            discount=line.discount_percent,
            # Bill tidak melewati mesin pajak POS: subtotal-nya satu angka,
            # dan dikirim di kedua field supaya bentuk payload tetap sama.
            price_subtotal=line.subtotal,
            price_subtotal_incl=line.subtotal,
            estimated_time=estimated_time,
            attributes=[],
            customer_note=line.note or None,
            note=line.note or None,
            # Bill belum mengenal reward loyalty; baris promo baru lahir saat
            # checkout membuat pos.order.
            is_reward_line=False,
            reward_id=None,
            coupon_id=None,
            kitchen_state=(
                getattr(line, 'kitchen_state', None) or 'pending'
            ) if 'kitchen_state' in line._fields else None,
            cooking_started_at=self._iso(getattr(line, 'cooking_started_at', None)),
            ready_at=self._iso(getattr(line, 'ready_at', None)),
            ready_source=getattr(line, 'ready_source', None) or None,
        )

    def _state_label(self, bill):
        labels = dict(bill.fields_get(['state'])['state']['selection'])
        return labels.get(bill.state, bill.state)

    def _table_dict(self, bill):
        table = bill.table_id
        if table:
            return {
                "id": table.id,
                "table_number": table.table_number,
                "floor": {
                    "id": table.floor_id.id,
                    "name": table.floor_id.name,
                } if table.floor_id else None,
            }
        # Mobile boleh mengirim nomor meja bebas yang tidak ada di
        # restaurant.table; nomor itu disimpan sebagai teks di table_ref.
        if bill.table_ref:
            return {
                "id": None,
                "table_number": bill.table_ref,
                "floor": None,
            }
        return None

    def _bill_entity(self, bill):
        line_entities = [self._line_entity(line) for line in bill.line_ids]

        cooking_times = [
            line.estimated_time for line in line_entities if line.estimated_time
        ]
        estimated_time_max = max(cooking_times) if cooking_times else 0
        estimated_time_total = sum(cooking_times)

        started = [
            line.cooking_started_at for line in bill.line_ids
            if getattr(line, 'cooking_started_at', False)
        ]
        processing_started_at = min(started) if started else None

        estimated_ready_at = None
        if processing_started_at and estimated_time_max:
            estimated_ready_at = (
                processing_started_at + timedelta(minutes=estimated_time_max)
            ).isoformat()

        config = bill.config_id

        return PosOrderEntity(
            id=bill.id,
            source='bill',
            name=bill.name or "Bill %s" % bill.id,
            pos_reference=None,
            tracking_number=None,
            state=bill.state,
            state_label=self._state_label(bill),
            date_order=self._iso(bill.create_date),
            processing_started_at=self._iso(processing_started_at),
            estimated_ready_at=estimated_ready_at,
            estimated_time_max=estimated_time_max,
            estimated_time_total=estimated_time_total,
            amount_total=bill.amount_total,
            # Bill tidak menghitung pajak sendiri, dan yang sudah masuk baru DP.
            amount_tax=0.0,
            amount_paid=bill.dp_amount or 0.0,
            company_id=bill.company_id.id if bill.company_id else False,
            # Open bill hidup di luar pos.session: ia dibuat sebelum checkout,
            # dan bisa bertahan melewati pergantian session.
            session=None,
            config={
                "id": config.id,
                "name": config.name,
            } if config else None,
            partner=None,
            table=self._table_dict(bill),
            pricelist=None,
            general_note=None,
            kitchen_state=PosOrderRepository._summarise_kitchen_state(line_entities),
            lines=line_entities,
            bill={
                "id": bill.id,
                "customer_name": bill.name_customer or None,
                "waiter_name": bill.name_waiters or None,
                "type_order": bill.type_order or None,
                "is_dp": bool(bill.is_dp),
                "dp_amount": bill.dp_amount or 0.0,
                "amount_due": bill.amount_due or 0.0,
                "table_ref": bill.table_ref or None,
                # Terisi berarti bill ini hanya cermin dari sebuah pos.order,
                # dan pesanannya sudah muncul di antrean lewat sumber itu.
                "pos_order_id": bill.pos_order_id.id if bill.pos_order_id else None,
                "write_date": self._iso(bill.write_date),
            },
        )

    # -- reads ------------------------------------------------------------

    def find_bills(self, pos_config_id, states=None, table_id=None,
                   limit=100, offset=0, kitchen_states=None):
        """Open bill pada satu POS config, dalam bentuk entity pesanan dapur."""
        if not self.is_available():
            return []

        config = self.env["pos.config"].sudo().browse(pos_config_id)
        if not config.exists():
            raise UserError(f"POS Config ID {pos_config_id} does not exist")

        domain = [
            ("config_id", "=", config.id),
            ("state", "in", states or BILL_STATES),
            # Bill yang dibuat checkout hanyalah cermin dari sebuah pos.order.
            # Menampilkan keduanya akan menggandakan hidangan yang sama di
            # layar dapur, jadi cermin itu dilewati -- pos.order-nya sendiri
            # sudah masuk antrean.
            ("pos_order_id", "=", False),
            # Bill kosong bukan pesanan; upsert dengan keranjang kosong justru
            # menghapus bill-nya.
            ("line_ids", "!=", False),
        ]

        line_model = self.env["poskas.bill.line"]
        if kitchen_states and 'kitchen_state' in line_model._fields:
            # NULL pada baris lama dibaca 'pending' oleh serialisasi di atas.
            # Domainnya harus sepakat, kalau tidak bill lama kadang hilang
            # walaupun payload-nya menyebut pending.
            if 'pending' in kitchen_states:
                domain.extend([
                    '|',
                    ("line_ids.kitchen_state", "=", False),
                    ("line_ids.kitchen_state", "in", kitchen_states),
                ])
            else:
                domain.append(("line_ids.kitchen_state", "in", kitchen_states))

        if table_id:
            domain.append(("table_id", "=", table_id))

        # Tertua dulu: layar dapur bekerja FIFO.
        bills = self.env[BILL_MODEL].sudo().with_company(config.company_id).search(
            domain, order="create_date asc, id asc",
            limit=limit or None, offset=offset or 0,
        )
        return [self._bill_entity(bill) for bill in bills]

    def find_bill(self, bill_id):
        if not self.is_available():
            raise UserError(
                "The 'rest_api_odoo' module is required to read POS bills")
        bill = self.env[BILL_MODEL].sudo().browse(bill_id)
        if not bill.exists():
            raise UserError(f"Bill ID {bill_id} does not exist")
        return self._bill_entity(bill)

    # -- writes -----------------------------------------------------------

    def set_line_kitchen_state(self, bill_id, line_id, target, source='staff'):
        """Geser status memasak satu baris bill. Status bill diturunkan otomatis."""
        if not self.is_available():
            raise UserError(
                "The 'rest_api_odoo' module is required to update bill lines")

        bill = self.env[BILL_MODEL].sudo().browse(bill_id)
        if not bill.exists():
            raise UserError(f"Bill ID {bill_id} does not exist")

        line = bill.line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError(
                f"Bill line ID {line_id} does not belong to Bill ID {bill_id}")

        if not hasattr(line, 'set_kitchen_state'):
            raise UserError(
                "Module 'rest_api_odoo' version 18.0.1.1.0 or newer is required "
                "for kitchen states on bill lines")

        line.set_kitchen_state(target, source)
        return self._bill_entity(bill)
