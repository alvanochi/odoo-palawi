# -*- coding: utf-8 -*-
from odoo import models

from .pos_order import KDS_CHANNEL_PREFIX


class IrWebsocket(models.AbstractModel):
    _inherit = 'ir.websocket'

    def _build_bus_channel_list(self, channels):
        """Terima hanya capability channel KDS yang masih terdaftar.

        Odoo 18 menerima string channel yang dikirim browser. Token acak pada
        pos.config membuat channel tidak dapat ditebak; pemeriksaan ini juga
        memastikan token yang sudah dirotasi langsung tidak dapat digunakan.
        """
        regular_channels = []
        requested_tokens = []
        for channel in channels:
            if channel.startswith(KDS_CHANNEL_PREFIX):
                requested_tokens.append(channel[len(KDS_CHANNEL_PREFIX):])
            else:
                regular_channels.append(channel)

        if requested_tokens:
            valid_tokens = set(self.env['pos.config'].sudo().search([
                ('kds_realtime_token', 'in', requested_tokens),
            ]).mapped('kds_realtime_token'))
            regular_channels.extend(
                '%s%s' % (KDS_CHANNEL_PREFIX, token)
                for token in requested_tokens if token in valid_tokens
            )

        return super()._build_bus_channel_list(regular_channels)
