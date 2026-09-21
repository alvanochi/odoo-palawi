# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from ..models import utils
from .common import FAR_LAT, FAR_LON, HQ_LAT, HQ_LON, FoomAttendanceCommon


@tagged('post_install', '-at_install')
class TestGeofence(FoomAttendanceCommon):

    # -- perhitungan jarak ---------------------------------------------
    def test_haversine_known_distance(self):
        """Monas -> Kota Tua kira-kira 4,7 km menurut peta."""
        dist = utils.haversine_m(HQ_LAT, HQ_LON, FAR_LAT, FAR_LON)
        self.assertAlmostEqual(dist / 1000.0, 4.7, delta=0.3)

    def test_haversine_zero_for_same_point(self):
        self.assertEqual(utils.haversine_m(HQ_LAT, HQ_LON, HQ_LAT, HQ_LON), 0.0)

    def test_haversine_symmetric(self):
        a = utils.haversine_m(HQ_LAT, HQ_LON, FAR_LAT, FAR_LON)
        b = utils.haversine_m(FAR_LAT, FAR_LON, HQ_LAT, HQ_LON)
        self.assertAlmostEqual(a, b, places=6)

    def test_valid_coords_rejects_null_island_and_garbage(self):
        self.assertTrue(utils.valid_coords(HQ_LAT, HQ_LON))
        # 0,0 hampir selalu berarti pembacaan GPS gagal, bukan lokasi nyata
        self.assertFalse(utils.valid_coords(0.0, 0.0))
        self.assertFalse(utils.valid_coords(91.0, 0.0))
        self.assertFalse(utils.valid_coords(0.0, 181.0))
        self.assertFalse(utils.valid_coords(None, None))
        self.assertFalse(utils.valid_coords('abc', 'def'))

    # -- model lokasi ---------------------------------------------------
    def test_distance_from(self):
        self.assertLess(self.hq.distance_from(HQ_LAT, HQ_LON), 1.0)
        self.assertIsNone(self.hq.distance_from(None, None),
                          "koordinat tidak valid harus mengembalikan None, bukan 0")

    def test_nearest_to_picks_closest(self):
        both = self.hq | self.branch
        loc, dist = both.nearest_to(HQ_LAT, HQ_LON)
        self.assertEqual(loc, self.hq)
        self.assertLess(dist, 1.0)

        loc, dist = both.nearest_to(FAR_LAT, FAR_LON)
        self.assertEqual(loc, self.branch)
        self.assertLess(dist, 1.0)

    def test_nearest_to_without_coords_returns_first_and_no_distance(self):
        loc, dist = (self.hq | self.branch).nearest_to(None, None)
        self.assertTrue(loc)
        self.assertIsNone(dist)

    def test_coordinate_range_constraint(self):
        with self.assertRaises(ValidationError):
            self.Location.create({'name': 'X', 'latitude': 95.0, 'longitude': 0.1})
        with self.assertRaises(ValidationError):
            self.Location.create({'name': 'X', 'latitude': 0.1, 'longitude': -200.0})

    @mute_logger('odoo.sql_db')
    def test_radius_must_be_positive(self):
        with self.assertRaises(Exception):
            self.Location.create({
                'name': 'X', 'latitude': HQ_LAT, 'longitude': HQ_LON, 'radius_m': 0})
            self.env.flush_all()

    # -- resolusi kebijakan ---------------------------------------------
    def test_policy_falls_back_to_location(self):
        self.assertEqual(self.employee.foom_effective_policy(self.hq), 'block')
        self.assertEqual(self.employee.foom_effective_policy(self.branch), 'warn')

    def test_employee_override_beats_location(self):
        self.employee.foom_att_geofence_policy = 'off'
        self.assertEqual(self.employee.foom_effective_policy(self.hq), 'off',
                         "override employee harus menang atas kebijakan lokasi")

    def test_policy_without_location_uses_global_param(self):
        empty = self.Location.browse()
        self.assertEqual(self.employee.foom_effective_policy(empty), 'block')
        self._set_param('default_geofence_policy', 'off')
        self.assertEqual(self.employee.foom_effective_policy(empty), 'off')

    # -- lokasi kandidat -------------------------------------------------
    def test_candidate_locations_priority(self):
        """roster > shift > employee."""
        sched = self.employee.foom_resolve_schedule()
        self.assertEqual(self.employee.foom_candidate_locations(sched), self.hq,
                         "tanpa roster, lokasi diambil dari shift")

        multi = self.Shift.create({
            'name': 'Keliling', 'time_from': 8.0, 'time_to': 17.0,
            'location_ids': [(6, 0, (self.hq | self.branch).ids)],
        })
        sched['shift'] = multi
        sched['roster'] = self.Roster.browse()
        self.assertEqual(self.employee.foom_candidate_locations(sched), self.hq | self.branch)

        sched['roster'] = self.Roster.new({'location_id': self.branch.id})
        self.assertEqual(self.employee.foom_candidate_locations(sched), self.branch,
                         "lokasi pada baris roster harus menang")

    def test_candidate_locations_empty_when_nothing_configured(self):
        bare = self.Employee.create({'name': 'Tanpa Apa-apa', 'tz': 'Asia/Jakarta'})
        sched = bare.foom_resolve_schedule()
        self.assertFalse(bare.foom_candidate_locations(sched))
