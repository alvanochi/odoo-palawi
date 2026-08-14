# -*- coding: utf-8 -*-

class PosSessionEntity:
    def __init__(self, id, name, state, state_label, start_at, stop_at, is_today,
                 config, company, user, order_count):
        self.id = id
        self.name = name
        self.state = state
        self.state_label = state_label   # 'opened' reads as "In Progress" in Odoo
        self.start_at = start_at
        self.stop_at = stop_at
        self.is_today = is_today
        self.config = config             # dict {"id","name"} or None
        self.company = company           # dict {"id","name"} or None
        self.user = user                 # dict {"id","name"} or None
        self.order_count = order_count

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "state_label": self.state_label,
            "start_at": self.start_at,
            "stop_at": self.stop_at,
            "is_today": self.is_today,
            "config": self.config,
            "company": self.company,
            "user": self.user,
            "order_count": self.order_count,
        }
