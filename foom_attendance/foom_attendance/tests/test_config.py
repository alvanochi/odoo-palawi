# -*- coding: utf-8 -*-
from odoo.tests.common import tagged

from ..models import utils
from ..models.utils import PARAM_PREFIX
from .common import FoomAttendanceCommon


@tagged('post_install', '-at_install')
class TestConfig(FoomAttendanceCommon):
    """Odoo menghapus baris `ir.config_parameter` begitu checkbox dimatikan atau
    angka diisi 0. Test di sini mengunci konsekuensinya: parameter yang hilang
    harus berarti mati/nol, dan layar Settings harus menampilkan hal yang sama
    dengan yang benar-benar dijalankan controller."""

    def _icp(self, name):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_PREFIX + name)

    def _save(self, **vals):
        self.env['res.config.settings'].create(vals).execute()

    def _ui_value(self, field):
        settings = self.env['res.config.settings']
        return settings.default_get([field]).get(field)

    # ------------------------------------------------------------------
    def test_seeded_defaults_are_on_after_install(self):
        self.assertTrue(utils.get_bool_param(self.env, 'public_enabled'))
        self.assertTrue(utils.get_bool_param(self.env, 'require_reason_outside'))
        self.assertTrue(utils.get_bool_param(self.env, 'allow_without_roster'))
        self.assertEqual(utils.get_int_param(self.env, 'max_gps_accuracy_m'), 100)
        self.assertEqual(utils.get_int_param(self.env, 'min_punch_interval_sec'), 60)

    def test_turning_a_checkbox_off_actually_turns_it_off(self):
        """Regresi. Kalau DEFAULTS berisi '1', mematikan checkbox tidak
        berpengaruh sama sekali: parameternya dihapus lalu default terbaca lagi."""
        self._save(foom_att_public_enabled=False)
        self.assertFalse(self._icp('public_enabled'),
                         "Odoo memang menghapus barisnya — itu yang diuji di sini")
        self.assertFalse(utils.get_bool_param(self.env, 'public_enabled'))
        self.assertFalse(self._ui_value('foom_att_public_enabled'),
                         "layar Settings harus ikut menunjukkan keadaan mati")

    def test_turning_it_back_on_works(self):
        self._save(foom_att_public_enabled=False)
        self._save(foom_att_public_enabled=True)
        self.assertTrue(utils.get_bool_param(self.env, 'public_enabled'))
        self.assertTrue(self._ui_value('foom_att_public_enabled'))

    def test_zero_means_disabled_for_thresholds(self):
        self._save(foom_att_max_gps_accuracy_m=0, foom_att_min_punch_interval_sec=0)
        self.assertEqual(utils.get_int_param(self.env, 'max_gps_accuracy_m'), 0)
        self.assertEqual(utils.get_int_param(self.env, 'min_punch_interval_sec'), 0)
        self.assertEqual(self._ui_value('foom_att_max_gps_accuracy_m'), 0)

    def test_non_zero_thresholds_round_trip(self):
        self._save(foom_att_max_gps_accuracy_m=42, foom_att_default_radius_m=321)
        self.assertEqual(utils.get_int_param(self.env, 'max_gps_accuracy_m'), 42)
        self.assertEqual(utils.get_int_param(self.env, 'default_radius_m'), 321)

    def test_selection_round_trip(self):
        self._save(foom_att_default_geofence_policy='warn')
        self.assertEqual(utils.get_param(self.env, 'default_geofence_policy'), 'warn')

    def test_bool_parser_accepts_odoo_string_forms(self):
        for raw, expected in (('1', True), ('True', True), ('true', True), ('on', True),
                              ('0', False), ('False', False), ('', False), ('nonsense', False)):
            self._set_param('require_photo', raw)
            self.assertEqual(utils.get_bool_param(self.env, 'require_photo'), expected,
                             'nilai %r salah diartikan' % raw)

    def test_int_parser_survives_garbage(self):
        self._set_param('default_radius_m', 'bukan-angka')
        self.assertEqual(utils.get_int_param(self.env, 'default_radius_m'), 150,
                         "nilai rusak harus jatuh ke default, bukan melempar error")

    def test_public_url_is_computed(self):
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.foom_att_public_url.endswith('/foom/attendance'))
