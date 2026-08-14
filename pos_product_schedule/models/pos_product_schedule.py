# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

WEEKDAY_FIELDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

# Writing these fields must not re-trigger the apply / cron sync logic,
# otherwise create() and write() would call themselves in a loop.
INTERNAL_FIELDS = {'last_applied', 'cron_open_id', 'cron_close_id'}


class PosProductSchedule(models.Model):
    """Time based availability of products in the Point of Sale.

    Instead of polling, every schedule owns two scheduled actions: one
    firing at the start time and one at the end time, each repeating
    daily. They are plain ir.cron records, visible and runnable from
    Settings > Technical > Scheduled Actions.
    """
    _name = 'pos.product.schedule'
    _description = 'POS Product Schedule'
    _order = 'time_from, name'

    name = fields.Char(
        string='Schedule Name', required=True,
        help='For example: Breakfast Menu, Lunch Promo.')
    active = fields.Boolean(string='Active', default=True)
    product_ids = fields.Many2many(
        'product.template', string='Products', required=True,
        help='Products whose POS availability is driven by this schedule. '
             'They can be searched by name or by barcode.')
    time_from = fields.Float(
        string='Start Time', required=True, default=9.0,
        help='Products start showing in the POS at this time.')
    time_to = fields.Float(
        string='End Time', required=True, default=12.0,
        help='Products stop showing in the POS at this time. When the end '
             'time is earlier than the start time, the schedule is treated '
             'as crossing midnight (for example 22:00 - 02:00).')
    tz = fields.Selection(
        lambda self: [(t, t) for t in pytz.all_timezones],
        string='Timezone', required=True,
        default=lambda self: self.env.user.tz or 'UTC',
        help='Timezone the start and end times refer to.')
    mon = fields.Boolean(string='Monday', default=True)
    tue = fields.Boolean(string='Tuesday', default=True)
    wed = fields.Boolean(string='Wednesday', default=True)
    thu = fields.Boolean(string='Thursday', default=True)
    fri = fields.Boolean(string='Friday', default=True)
    sat = fields.Boolean(string='Saturday', default=True)
    sun = fields.Boolean(string='Sunday', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    product_count = fields.Integer(
        string='Products', compute='_compute_product_count')
    is_open_now = fields.Boolean(
        string='Running Now', compute='_compute_is_open_now',
        help='Whether the current time falls inside this schedule.')
    last_applied = fields.Datetime(
        string='Last Applied', readonly=True, copy=False,
        help='Last time this schedule actually changed product '
             'availability.')
    cron_open_id = fields.Many2one(
        'ir.cron', string='Show Trigger', readonly=True, copy=False,
        ondelete='set null',
        help='Scheduled action firing daily at the start time.')
    cron_close_id = fields.Many2one(
        'ir.cron', string='Hide Trigger', readonly=True, copy=False,
        ondelete='set null',
        help='Scheduled action firing daily at the end time.')
    next_show = fields.Datetime(
        string='Next Show', related='cron_open_id.nextcall', readonly=True)
    next_hide = fields.Datetime(
        string='Next Hide', related='cron_close_id.nextcall', readonly=True)

    # ------------------------------------------------------------------
    # Compute / constraints
    # ------------------------------------------------------------------
    @api.depends('product_ids')
    def _compute_product_count(self):
        for schedule in self:
            schedule.product_count = len(schedule.product_ids)

    def _compute_is_open_now(self):
        for schedule in self:
            schedule.is_open_now = schedule._is_open_now()

    @api.constrains('time_from', 'time_to')
    def _check_times(self):
        for schedule in self:
            for value in (schedule.time_from, schedule.time_to):
                if not 0.0 <= value < 24.0:
                    raise ValidationError(_(
                        'Times must be between 00:00 and 23:59.'))
            if schedule.time_from == schedule.time_to:
                raise ValidationError(_(
                    'Start Time and End Time cannot be identical.'))

    @api.constrains('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
    def _check_weekdays(self):
        for schedule in self:
            if not any(schedule[day] for day in WEEKDAY_FIELDS):
                raise ValidationError(_(
                    'Select at least one active day for schedule %s.',
                    schedule.name))

    # ------------------------------------------------------------------
    # Lifecycle: keep the triggers in sync with the schedule
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        schedules = super().create(vals_list)
        schedules._sync_triggers()
        schedules._apply_schedules(schedules)
        return schedules

    def write(self, vals):
        result = super().write(vals)
        if set(vals) - INTERNAL_FIELDS:
            self._sync_triggers()
            self._apply_schedules(self)
        return result

    def unlink(self):
        triggers = (self.cron_open_id | self.cron_close_id).sudo()
        result = super().unlink()
        triggers.unlink()
        return result

    # ------------------------------------------------------------------
    # Trigger (ir.cron) management
    # ------------------------------------------------------------------
    @staticmethod
    def _float_to_hour_minute(value):
        hour = int(value)
        minute = int(round((value - hour) * 60))
        if minute >= 60:
            hour, minute = hour + 1, 0
        if hour >= 24:
            hour, minute = 23, 59
        return hour, minute

    def _next_utc_call(self, hour_float):
        """Next UTC datetime matching hour_float in the schedule timezone."""
        self.ensure_one()
        tz = pytz.timezone(self.tz or 'UTC')
        now_local = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        hour, minute = self._float_to_hour_minute(hour_float)
        target = tz.localize(
            datetime.combine(now_local.date(), time(hour, minute)))
        if target <= now_local:
            target = tz.localize(
                datetime.combine(now_local.date() + timedelta(days=1),
                                 time(hour, minute)))
        return target.astimezone(pytz.UTC).replace(tzinfo=None)

    def _trigger_vals(self, kind):
        self.ensure_one()
        hour_float = self.time_from if kind == 'open' else self.time_to
        label = _('Show') if kind == 'open' else _('Hide')
        return {
            'name': _('Product Schedule: %(action)s - %(name)s',
                      action=label, name=self.name),
            'model_id': self.env['ir.model']._get_id('pos.product.schedule'),
            'state': 'code',
            'code': 'model._cron_boundary(%d)' % self.id,
            'interval_number': 1,
            'interval_type': 'days',
            'nextcall': self._next_utc_call(hour_float),
            'user_id': self.env.ref('base.user_root').id,
            'active': self.active,
            'priority': 5,
        }

    def _sync_triggers(self):
        """Create or refresh the two scheduled actions of each schedule."""
        Cron = self.env['ir.cron'].sudo()
        for schedule in self:
            if not schedule.id:
                continue
            for kind, field_name in (('open', 'cron_open_id'),
                                     ('close', 'cron_close_id')):
                vals = schedule._trigger_vals(kind)
                cron = schedule[field_name].sudo()
                if cron:
                    cron.write(vals)
                else:
                    schedule.sudo().write({field_name: Cron.create(vals).id})
        return True

    # ------------------------------------------------------------------
    # Schedule window
    # ------------------------------------------------------------------
    def _is_day_enabled(self, weekday_index):
        """weekday_index: 0 = Monday ... 6 = Sunday."""
        self.ensure_one()
        return bool(self[WEEKDAY_FIELDS[weekday_index]])

    def _is_open_now(self):
        """Return True when the current time falls inside this schedule."""
        self.ensure_one()
        tz = pytz.timezone(self.tz or 'UTC')
        now = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        now_float = now.hour + now.minute / 60.0
        if self.time_from < self.time_to:
            # Regular window inside a single day, e.g. 09:00 - 12:00.
            return (self._is_day_enabled(now.weekday())
                    and self.time_from <= now_float < self.time_to)
        # Window crossing midnight, e.g. 22:00 - 02:00.
        if now_float >= self.time_from:
            # Before midnight: the schedule started today.
            return self._is_day_enabled(now.weekday())
        if now_float < self.time_to:
            # After midnight: the schedule started yesterday.
            return self._is_day_enabled((now - timedelta(days=1)).weekday())
        return False

    # ------------------------------------------------------------------
    # Applying availability
    # ------------------------------------------------------------------
    def _set_available_in_pos(self, products, value):
        """Write available_in_pos product by product.

        Each write runs in its own savepoint: core POS constraints (a
        product belonging to a combo, for instance) raise UserError, and
        without isolation a single rejected product would roll back the
        whole batch and leave every other product untouched.
        """
        changed = 0
        for product in products:
            try:
                with self.env.cr.savepoint():
                    product.sudo().available_in_pos = value
                changed += 1
            except (UserError, ValidationError) as error:
                _logger.warning(
                    'POS Product Schedule: cannot set "Available in POS" = %s '
                    'on product %s (id %s): %s',
                    value, product.display_name, product.id, error)
        return changed

    def _apply_schedules(self, schedules=None, force_stamp=True):
        """Synchronise available_in_pos for every scheduled product.

        Always recomputed from every schedule at once, never as a blind
        on/off: a product shared by two schedules stays visible while any
        of them is running, and a trigger that fires late still lands on
        the correct state.
        """
        if schedules is None:
            schedules = self.sudo().search([])
        schedules = schedules.sudo()
        if not schedules:
            return {'enabled': 0, 'disabled': 0}
        should_show = self.env['product.template'].sudo()
        managed = self.env['product.template'].sudo()
        for schedule in schedules:
            products = schedule.product_ids
            managed |= products
            if schedule._is_open_now():
                should_show |= products
        to_enable = should_show.filtered(lambda p: not p.available_in_pos)
        to_disable = (managed - should_show).filtered(
            lambda p: p.available_in_pos)
        if not (to_enable or to_disable) and not force_stamp:
            return {'enabled': 0, 'disabled': 0}
        enabled = self._set_available_in_pos(to_enable, True)
        disabled = self._set_available_in_pos(to_disable, False)
        schedules.write({'last_applied': fields.Datetime.now()})
        if enabled or disabled:
            _logger.info(
                'POS Product Schedule: %s product(s) shown, %s hidden.',
                enabled, disabled)
        return {'enabled': enabled, 'disabled': disabled}

    def action_apply_now(self):
        """Apply immediately, same effect as Run Manually on the trigger."""
        result = self._apply_schedules(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Schedule Applied'),
                'message': _(
                    '%(on)s product(s) shown, %(off)s product(s) hidden '
                    'in the POS.',
                    on=result['enabled'], off=result['disabled']),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_triggers(self):
        """Open the two scheduled actions of this schedule."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Triggers - %s', self.name),
            'res_model': 'ir.cron',
            'view_mode': 'list,form',
            'domain': [('id', 'in',
                        (self.cron_open_id | self.cron_close_id).ids)],
        }

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Products - %s', self.name),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.product_ids.ids)],
        }

    # ------------------------------------------------------------------
    # Entry points called by scheduled actions
    # ------------------------------------------------------------------
    @api.model
    def _cron_boundary(self, schedule_id=None):
        """Fired by a schedule trigger at its start or end time."""
        self._apply_schedules(force_stamp=False)

    @api.model
    def _cron_apply_schedules(self):
        """Hourly safety net in case a trigger was missed or edited."""
        self._apply_schedules(force_stamp=False)
