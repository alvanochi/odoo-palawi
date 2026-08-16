# -*- coding: utf-8 -*-
import datetime
import pytz
from odoo.exceptions import UserError

from ..domain.entities.pos_config import PosConfigEntity
from ..domain.entities.pos_session import PosSessionEntity

# In Odoo the POS session state 'opened' is displayed as "In Progress"
# (see addons/point_of_sale/models/pos_session.py).
SESSION_STATE_IN_PROGRESS = 'opened'


class PosConfigRepository:
    def __init__(self, env):
        self.env = env

    # -- helpers ----------------------------------------------------------

    def _tz(self, tz_name):
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.timezone('UTC')

    def _local_date(self, naive_utc_dt, tz):
        """Odoo stores Datetime naive in UTC; convert to a local calendar date."""
        if not naive_utc_dt:
            return None
        return pytz.utc.localize(naive_utc_dt).astimezone(tz).date()

    def _state_label(self, session):
        # fields_get resolves selection_add entries from other modules too
        labels = dict(session.fields_get(['state'])['state']['selection'])
        return labels.get(session.state, session.state)

    def _session_entity(self, session, tz, today):
        start_date = self._local_date(session.start_at, tz)
        return PosSessionEntity(
            id=session.id,
            name=session.name,
            state=session.state,
            state_label=self._state_label(session),
            start_at=session.start_at.isoformat() if session.start_at else None,
            stop_at=session.stop_at.isoformat() if session.stop_at else None,
            is_today=(start_date == today) if start_date else False,
            config={"id": session.config_id.id, "name": session.config_id.name} if session.config_id else None,
            company={"id": session.company_id.id, "name": session.company_id.name} if session.company_id else None,
            user={"id": session.user_id.id, "name": session.user_id.name} if session.user_id else None,
            order_count=len(session.order_ids),
        )

    # -- pos.config -------------------------------------------------------

    def find_configs_by_company(self, company_id, include_inactive=False):
        company = self.env['res.company'].sudo().browse(company_id)
        if not company.exists():
            raise UserError(f"Company ID {company_id} does not exist")

        domain = [("company_id", "=", company_id)]
        model = self.env["pos.config"].sudo().with_company(company_id)
        if include_inactive:
            model = model.with_context(active_test=False)

        configs = []
        for config in model.search(domain, order="name asc"):
            session = config.current_session_id
            configs.append(PosConfigEntity(
                id=config.id,
                name=config.name,
                company_id=config.company_id.id,
                active=config.active,
                module_pos_restaurant=config.module_pos_restaurant,
                use_pricelist=config.use_pricelist,
                pricelist={
                    "id": config.pricelist_id.id,
                    "name": config.pricelist_id.name,
                } if config.pricelist_id else None,
                available_pricelists=[
                    {"id": pl.id, "name": pl.name} for pl in config.available_pricelist_ids
                ],
                limit_categories=config.limit_categories,
                available_categories=[
                    {"id": categ.id, "name": categ.name} for categ in config.iface_available_categ_ids
                ],
                payment_methods=[
                    {"id": pm.id, "name": pm.name, "is_cash_count": pm.is_cash_count}
                    for pm in config.payment_method_ids
                ],
                picking_type={
                    "id": config.picking_type_id.id,
                    "name": config.picking_type_id.display_name,
                } if config.picking_type_id else None,
                currency={
                    "id": config.currency_id.id,
                    "name": config.currency_id.name,
                    "symbol": config.currency_id.symbol,
                } if config.currency_id else None,
                current_session={
                    "id": session.id,
                    "state": session.state,
                    "start_at": session.start_at.isoformat() if session.start_at else None,
                } if session else None,
            ))
        return configs

    # -- pos.session ------------------------------------------------------

    def resolve_config(self, pos_config_id):
        config = self.env["pos.config"].sudo().browse(pos_config_id)
        if not config.exists():
            raise UserError(f"POS Config ID {pos_config_id} does not exist")
        return config

    def find_partner(self, partner_id):
        if not partner_id:
            return None
        partner = self.env['res.partner'].sudo().browse(partner_id)
        return partner if partner.exists() else None

    def find_sessions(self, pos_config_id, states=None, date_str=None, limit=20, tz_name='UTC'):
        config = self.resolve_config(pos_config_id)
        tz = self._tz(tz_name)
        today = self._today(tz)

        domain = [("config_id", "=", config.id)]
        if states:
            domain.append(("state", "in", states))

        session_model = self.env["pos.session"].sudo().with_company(config.company_id)
        if date_str:
            sessions = session_model.search(domain, order="start_at desc, id desc").filtered(
                lambda s: self._local_date(s.start_at, tz)
                and self._local_date(s.start_at, tz).isoformat() == date_str
            )
            if limit:
                sessions = sessions[:limit]
        else:
            sessions = session_model.search(domain, order="start_at desc, id desc", limit=limit or None)

        return [self._session_entity(session, tz, today) for session in sessions]

    def _today(self, tz):
        return datetime.datetime.now(tz).date()

    def find_active_session(self, pos_config_id, require_today=False, tz_name='UTC'):
        """The single session a client should post orders to.

        There can legitimately be more than one session in progress when a
        cashier forgets to close yesterday's one, so the newest wins, with a
        preference for one that started today.
        """
        config = self.resolve_config(pos_config_id)
        tz = self._tz(tz_name)
        today = self._today(tz)

        sessions = self.env["pos.session"].sudo().with_company(config.company_id).search(
            [("config_id", "=", config.id), ("state", "=", SESSION_STATE_IN_PROGRESS)],
            order="start_at desc, id desc",
        )

        if not sessions:
            return {
                "can_create_order": False,
                "reason": "no_open_session",
                "session": None,
                "open_session_count": 0,
                "stale_session_ids": [],
                "timezone": tz_name,
            }

        today_sessions = sessions.filtered(lambda s: self._local_date(s.start_at, tz) == today)

        if today_sessions:
            chosen = today_sessions[0]
        elif require_today:
            return {
                "can_create_order": False,
                "reason": "no_session_today",
                "session": None,
                "open_session_count": len(sessions),
                "stale_session_ids": sessions.ids,
                "timezone": tz_name,
            }
        else:
            chosen = sessions[0]

        return {
            "can_create_order": True,
            "reason": None,
            "session": self._session_entity(chosen, tz, today).to_dict(),
            "open_session_count": len(sessions),
            "stale_session_ids": [sid for sid in sessions.ids if sid != chosen.id],
            "timezone": tz_name,
        }

    def resolve_active_session_record(self, pos_config_id, require_today=False,
                                      tz_name='UTC'):
        """Return record yang sama persis dengan endpoint sessions/active.

        Checkout dan KDS harus memakai resolver yang sama. Sebelumnya checkout
        mempunyai search sendiri sehingga dua endpoint dapat memilih session
        berbeda saat ada lebih dari satu session berstatus opened.
        """
        result = self.find_active_session(
            pos_config_id=pos_config_id,
            require_today=require_today,
            tz_name=tz_name,
        )
        session_data = result.get('session') if result.get('can_create_order') else None
        if not session_data:
            return self.env['pos.session']
        return self.env['pos.session'].sudo().browse(session_data['id']).exists()
