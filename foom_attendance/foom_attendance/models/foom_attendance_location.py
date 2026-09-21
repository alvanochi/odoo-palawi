# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import utils

GEOFENCE_POLICY = [
    ('block', 'Blokir di luar radius'),
    ('warn', 'Izinkan tapi ditandai'),
    ('off', 'Tidak dicek'),
]


class FoomAttendanceLocation(models.Model):
    _name = 'foom.attendance.location'
    _description = 'Lokasi Absensi (Geofence)'
    _order = 'sequence, name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(help="Kode singkat, mis. HO, WH-CKR, OUTLET-01.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    address_id = fields.Many2one('res.partner', string='Alamat')

    latitude = fields.Float(string='Latitude', digits=(10, 7), required=True, aggregator=None)
    longitude = fields.Float(string='Longitude', digits=(10, 7), required=True, aggregator=None)
    radius_m = fields.Integer(
        string='Radius (m)', default=150, required=True,
        help="Jarak maksimum dari titik di atas yang masih dianggap berada di lokasi.")
    geofence_policy = fields.Selection(
        GEOFENCE_POLICY, string='Kebijakan Geofence', default='block', required=True)

    note = fields.Text(string='Catatan')
    shift_ids = fields.Many2many(
        'foom.attendance.shift', 'foom_att_shift_location_rel', 'location_id', 'shift_id',
        string='Shift')
    employee_ids = fields.One2many(
        'hr.employee', 'foom_att_location_id', string='Employee (lokasi default)')
    employee_count = fields.Integer(compute='_compute_employee_count')
    map_url = fields.Char(string='Buka di Peta', compute='_compute_map_url')

    _sql_constraints = [
        ('radius_positive', 'CHECK(radius_m > 0)', 'Radius harus lebih besar dari 0 meter.'),
    ]

    # ------------------------------------------------------------------
    @api.depends('employee_ids')
    def _compute_employee_count(self):
        data = self.env['hr.employee'].sudo()._read_group(
            [('foom_att_location_id', 'in', self.ids)],
            ['foom_att_location_id'], ['__count'])
        mapped = {loc.id: count for loc, count in data}
        for rec in self:
            rec.employee_count = mapped.get(rec.id, 0)

    @api.depends('latitude', 'longitude')
    def _compute_map_url(self):
        for rec in self:
            if rec.latitude or rec.longitude:
                rec.map_url = 'https://www.google.com/maps?q=%s,%s' % (rec.latitude, rec.longitude)
            else:
                rec.map_url = False

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for rec in self:
            if not (-90.0 <= rec.latitude <= 90.0):
                raise ValidationError(_("Latitude harus di antara -90 dan 90."))
            if not (-180.0 <= rec.longitude <= 180.0):
                raise ValidationError(_("Longitude harus di antara -180 dan 180."))

    # ------------------------------------------------------------------
    def distance_from(self, lat, lon):
        """Jarak (meter) titik yang diberikan ke lokasi ini."""
        self.ensure_one()
        if not utils.valid_coords(lat, lon):
            return None
        return utils.haversine_m(float(lat), float(lon), self.latitude, self.longitude)

    def nearest_to(self, lat, lon):
        """Dari recordset ini, kembalikan (location, distance_m) terdekat."""
        best = (self.browse(), None)
        for rec in self:
            dist = rec.distance_from(lat, lon)
            if dist is None:
                continue
            if best[1] is None or dist < best[1]:
                best = (rec, dist)
        if not best[0] and self:
            # koordinat tidak valid — tetap kembalikan kandidat pertama tanpa jarak
            return self[0], None
        return best

    def action_open_map(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.map_url, 'target': 'new'}

    def action_view_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Employee'),
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('foom_att_location_id', '=', self.id)],
        }
