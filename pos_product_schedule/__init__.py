# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Rebuild the triggers of every schedule on install and upgrade.

    Also repairs databases where a trigger was deleted or disabled by
    hand: after an upgrade the schedules always own a correct pair of
    scheduled actions again.
    """
    schedules = env['pos.product.schedule'].sudo().with_context(
        active_test=False).search([])
    if schedules:
        schedules._sync_triggers()
        schedules._apply_schedules(schedules)
        _logger.info('POS Product Schedule: %s schedule(s) resynchronised.',
                     len(schedules))


def uninstall_hook(env):
    """Remove the scheduled actions generated per schedule."""
    crons = env['ir.cron'].sudo().search([('code', 'like', '_cron_boundary')])
    if crons:
        crons.unlink()
