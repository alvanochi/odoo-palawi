# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.exceptions import UserError

from ..domain.entities.pos_order import PosOrderEntity, PosOrderLineEntity

# Kitchen queue: what a kitchen display cares about by default.
#
# pos.order.state is plain Odoo again, so the queue is simply "paid but not
# yet posted". What still needs cooking is expressed by kitchen_state, which
# lives on the lines and is summarised on the order.
KITCHEN_STATES = ['paid']

# Orders the kitchen still has work on. 'served' is excluded: everything on
# that order has already reached the customer.
KITCHEN_PENDING_STATES = ['pending', 'cooking', 'ready']


class PosOrderRepository:
    def __init__(self, env):
        self.env = env

    # -- serialisation ----------------------------------------------------

    def _state_label(self, order):
        # fields_get resolves selection_add entries from other modules too
        labels = dict(order.fields_get(['state'])['state']['selection'])
        return labels.get(order.state, order.state)

    def _line_entity(self, line):
        template = line.product_id.product_tmpl_id
        # estimated_time comes from the product_estimated_time addon; guard in
        # case that addon is not installed on a given database.
        estimated_time = getattr(template, 'estimated_time', 0) or 0

        return PosOrderLineEntity(
            id=line.id,
            product_id=line.product_id.id,
            product_tmpl_id=template.id if template else False,
            product_name=line.product_id.name,
            full_product_name=line.full_product_name or line.product_id.display_name,
            qty=line.qty,
            price_unit=line.price_unit,
            discount=line.discount,
            price_subtotal=line.price_subtotal,
            price_subtotal_incl=line.price_subtotal_incl,
            estimated_time=estimated_time,
            attributes=line.attribute_value_ids.mapped('name'),
            customer_note=line.customer_note or None,
            note=line.note or None,
            is_reward_line=bool(getattr(line, 'is_reward_line', False)),
            reward_id=line.reward_id.id if getattr(line, 'reward_id', False) else None,
            coupon_id=line.coupon_id.id if getattr(line, 'coupon_id', False) else None,
            # getattr: field ini datang dari pos_order_extra_states, jadi API
            # tetap jalan (mengirim null) bila modul itu belum terpasang.
            kitchen_state=getattr(line, 'kitchen_state', None) or None,
            cooking_started_at=self._iso(getattr(line, 'cooking_started_at', None)),
            ready_at=self._iso(getattr(line, 'ready_at', None)),
            ready_source=getattr(line, 'ready_source', None) or None,
        )

    @staticmethod
    def _iso(value):
        return value.isoformat() if value else None

    def _order_entity(self, order):
        line_entities = [self._line_entity(line) for line in order.lines]

        # Reward lines are discounts/freebies, not dishes to cook.
        cooking_times = [
            line.estimated_time for line in line_entities
            if not line.is_reward_line and line.estimated_time
        ]
        estimated_time_max = max(cooking_times) if cooking_times else 0
        estimated_time_total = sum(cooking_times)

        # Diturunkan dari baris, bukan dari kolom di pos.order: menyimpan
        # salinannya di order berarti ada dua tempat yang bisa berbeda isi.
        started = [
            line.cooking_started_at for line in order.lines
            if getattr(line, 'cooking_started_at', False)
        ]
        processing_started_at = min(started) if started else None

        estimated_ready_at = None
        if processing_started_at and estimated_time_max:
            estimated_ready_at = (
                processing_started_at + timedelta(minutes=estimated_time_max)
            ).isoformat()

        kitchen_state = self._summarise_kitchen_state(line_entities)

        table = order.table_id if 'table_id' in order._fields else False

        return PosOrderEntity(
            id=order.id,
            name=order.name,
            pos_reference=order.pos_reference or None,
            tracking_number=order.tracking_number or None,
            state=order.state,
            state_label=self._state_label(order),
            date_order=order.date_order.isoformat() if order.date_order else None,
            processing_started_at=self._iso(processing_started_at),
            estimated_ready_at=estimated_ready_at,
            estimated_time_max=estimated_time_max,
            estimated_time_total=estimated_time_total,
            amount_total=order.amount_total,
            amount_tax=order.amount_tax,
            amount_paid=order.amount_paid,
            company_id=order.company_id.id,
            session={
                "id": order.session_id.id,
                "name": order.session_id.name,
                "state": order.session_id.state,
            } if order.session_id else None,
            config={
                "id": order.config_id.id,
                "name": order.config_id.name,
            } if order.config_id else None,
            partner={
                "id": order.partner_id.id,
                "name": order.partner_id.name,
                "phone": order.partner_id.phone or None,
            } if order.partner_id else None,
            table={
                "id": table.id,
                "table_number": table.table_number,
                "floor": {
                    "id": table.floor_id.id,
                    "name": table.floor_id.name,
                } if table.floor_id else None,
            } if table else None,
            pricelist={
                "id": order.pricelist_id.id,
                "name": order.pricelist_id.name,
            } if order.pricelist_id else None,
            general_note=order.general_note or None,
            kitchen_state=kitchen_state,
            lines=line_entities,
        )

    @staticmethod
    def _summarise_kitchen_state(line_entities):
        """Ringkasan status dapur satu pesanan, dihitung dari barisnya.

        Baris reward dikecualikan: potongan harga bukan makanan, dan sejak
        v2.1.0 baris seperti itu memang lahir langsung 'served'.
        """
        states = [
            line.kitchen_state for line in line_entities
            if not line.is_reward_line and line.kitchen_state
        ]
        if not states:
            return None
        if all(state == 'served' for state in states):
            return 'served'
        if all(state in ('ready', 'served') for state in states):
            return 'ready'
        if any(state in ('cooking', 'ready', 'served') for state in states):
            return 'cooking'
        return 'pending'

    # -- reads ------------------------------------------------------------

    def find_orders(self, session_id=None, pos_config_id=None, states=None,
                    table_id=None, limit=100, offset=0, kitchen_states=None):
        domain = []
        if session_id:
            session = self.env["pos.session"].sudo().browse(session_id)
            if not session.exists():
                raise UserError(f"POS Session ID {session_id} does not exist")
            domain.append(("session_id", "=", session.id))
            company = session.company_id
        elif pos_config_id:
            config = self.env["pos.config"].sudo().browse(pos_config_id)
            if not config.exists():
                raise UserError(f"POS Config ID {pos_config_id} does not exist")
            domain.append(("config_id", "=", config.id))
            company = config.company_id
        else:
            raise UserError("Either 'pos_session_id' or 'pos_config_id' is required")

        if states:
            domain.append(("state", "in", states))
        # Filtered through the lines, not through a summary column on the
        # order: "has at least one dish in this state" is what a kitchen
        # display actually asks for. Reward lines are born 'served' so they
        # never hold an order in the queue.
        #
        # Guarded because kitchen_state belongs to pos_order_extra_states. If
        # that module is absent the filter is simply dropped, so this endpoint
        # keeps serving orders instead of failing with a raw SQL error.
        if kitchen_states and 'kitchen_state' in self.env["pos.order.line"]._fields:
            domain.append(("lines.kitchen_state", "in", kitchen_states))
        if table_id:
            domain.append(("table_id", "=", table_id))

        # Oldest first: a kitchen display works FIFO.
        orders = self.env["pos.order"].sudo().with_company(company).search(
            domain, order="date_order asc, id asc", limit=limit or None, offset=offset or 0
        )
        return [self._order_entity(order) for order in orders]

    def find_order(self, order_id):
        order = self.env["pos.order"].sudo().browse(order_id)
        if not order.exists():
            raise UserError(f"POS Order ID {order_id} does not exist")
        return self._order_entity(order.with_company(order.company_id))

    # -- writes -----------------------------------------------------------

    def set_line_kitchen_state(self, order_id, line_id, target, source='staff'):
        """Geser status memasak satu baris. Status order diturunkan otomatis."""
        order = self.env["pos.order"].sudo().browse(order_id)
        if not order.exists():
            raise UserError(f"POS Order ID {order_id} does not exist")

        line = order.lines.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError(
                f"Order line ID {line_id} does not belong to POS Order ID {order_id}")

        if not hasattr(line, 'set_kitchen_state'):
            raise UserError(
                "The 'pos_order_extra_states' module is required for kitchen line states")

        line.set_kitchen_state(target, source)
        return self._order_entity(order.with_company(order.company_id))

