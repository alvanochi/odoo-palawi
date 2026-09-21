# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from ..models import utils
from .common import PIN_OK, FoomAttendanceCommon


@tagged('post_install', '-at_install')
class TestPin(FoomAttendanceCommon):

    def test_pin_is_hashed_not_stored_plaintext(self):
        stored = self.employee.foom_att_pin_hash
        self.assertTrue(stored)
        self.assertNotIn(PIN_OK, stored)
        self.assertFalse(self.employee.foom_att_pin_set,
                         "field bantu tidak boleh menyimpan PIN")

    def test_verify_pin(self):
        self.assertTrue(self.employee.foom_verify_pin(PIN_OK))
        self.assertFalse(self.employee.foom_verify_pin('000000'))
        self.assertFalse(self.employee.foom_verify_pin(''))
        self.assertFalse(self.employee.foom_verify_pin(None))

    def test_weak_pins_rejected(self):
        for bad in ('123', 'abcd', '12a4', '1234', '0000', '111111', '9' * 13):
            with self.assertRaises(ValidationError, msg='PIN %r seharusnya ditolak' % bad):
                self.employee.write({'foom_att_pin_set': bad})

    def test_legacy_kiosk_pin_accepted_once_then_hashed(self):
        legacy = self.Employee.create({'name': 'Lama', 'pin': '246813'})
        self.assertFalse(legacy.foom_att_pin_hash)
        self.assertTrue(legacy.foom_verify_pin('246813'))
        self.assertTrue(legacy.foom_att_pin_hash, "PIN lama harus ikut di-hash")
        self.assertFalse(legacy.foom_verify_pin('999999'))

    def test_setting_pin_clears_lock(self):
        self.employee.foom_att_locked_until = fields.Datetime.now() + timedelta(hours=1)
        self.employee.write({'foom_att_pin_set': '135791'})
        self.assertFalse(self.employee.foom_att_locked_until)

    def test_reset_lock_button(self):
        self.employee.foom_att_locked_until = fields.Datetime.now() + timedelta(hours=1)
        self.employee.action_foom_reset_lock()
        self.assertFalse(self.employee.foom_att_locked_until)


@tagged('post_install', '-at_install')
class TestCodeLookup(FoomAttendanceCommon):

    def test_find_by_code(self):
        self.assertEqual(self.Employee._foom_find_by_code('ZZTEST001'), self.employee)
        self.assertEqual(self.Employee._foom_find_by_code('zztest001'), self.employee,
                         "pencarian kode tidak peka huruf besar/kecil")

    def test_wildcards_are_escaped(self):
        """Regresi. `=ilike` diteruskan mentah ke SQL ILIKE — tanpa escape,
        `%` cocok ke employee mana pun dan kode bisa dienumerasi."""
        for probe in ('%', '_______', 'F%', 'F1_____', '%1%'):
            self.assertFalse(self.Employee._foom_find_by_code(probe),
                             'pola %r seharusnya tidak cocok ke siapa pun' % probe)

    def test_backslash_does_not_break_query(self):
        self.assertFalse(self.Employee._foom_find_by_code('\\'))
        self.assertFalse(self.Employee._foom_find_by_code('F\\%'))

    def test_barcode_fallback(self):
        self.employee.write({'foom_att_code': False, 'barcode': '049900112233'})
        self.assertEqual(self.Employee._foom_find_by_code('049900112233'), self.employee)

    def test_archived_employee_not_found(self):
        self.employee.active = False
        self.assertFalse(self.Employee._foom_find_by_code('ZZTEST001'))

    def test_empty_and_oversized_input(self):
        self.assertFalse(self.Employee._foom_find_by_code(''))
        self.assertFalse(self.Employee._foom_find_by_code(None))
        self.assertFalse(self.Employee._foom_find_by_code('X' * 40))

    @mute_logger('odoo.sql_db')
    def test_code_is_unique(self):
        with self.assertRaises(Exception):
            self.Employee.create({'name': 'Kembar', 'foom_att_code': 'ZZTEST001'})
            self.env.flush_all()

    def test_generate_code_is_unique_and_idempotent(self):
        emp = self.Employee.create({'name': 'Tanpa Kode'})
        emp.action_foom_generate_code()
        first = emp.foom_att_code
        self.assertTrue(first)
        self.assertEqual(self.Employee._foom_find_by_code(first), emp)
        emp.action_foom_generate_code()
        self.assertEqual(emp.foom_att_code, first, "kode yang sudah ada tidak ditimpa")


@tagged('post_install', '-at_install')
class TestSession(FoomAttendanceCommon):

    def test_issue_returns_plaintext_token_but_stores_hash(self):
        session, token = self.Session._issue(self.employee, ip='10.0.0.1', user_agent='UA')
        self.assertTrue(token)
        self.assertNotEqual(session.token_hash, token)
        self.assertEqual(session.token_hash, utils.hash_token(token))
        self.assertEqual(session.state, 'active')

    def test_resolve(self):
        session, token = self.Session._issue(self.employee)
        self.assertEqual(self.Session._resolve(token), session)
        self.assertFalse(self.Session._resolve('salah'))
        self.assertFalse(self.Session._resolve(''))
        self.assertFalse(self.Session._resolve('x' * 200))

    def test_revoked_session_is_dead(self):
        session, token = self.Session._issue(self.employee)
        session.action_revoke()
        self.assertEqual(session.state, 'revoked')
        self.assertFalse(self.Session._resolve(token))

    def test_expired_session_is_dead(self):
        session, token = self.Session._issue(self.employee)
        session.expire_at = fields.Datetime.now() - timedelta(minutes=1)
        self.assertEqual(session.state, 'expired')
        self.assertFalse(self.Session._resolve(token))

    def test_archived_employee_session_is_dead(self):
        """Regresi. hr_attendance meng-check-out employee saat diarsipkan;
        token lamanya tidak boleh bisa membuat absensi baru."""
        session, token = self.Session._issue(self.employee)
        self.employee.active = False
        self.assertFalse(self.Session._resolve(token))

    def test_revoke_all_sessions_of_employee(self):
        self.Session._issue(self.employee)
        self.Session._issue(self.employee)
        self.employee.action_foom_revoke_sessions()
        self.assertFalse(self.Session.search([
            ('employee_id', '=', self.employee.id), ('revoked', '=', False)]))

    def test_gc_removes_dead_sessions_only(self):
        alive, _t = self.Session._issue(self.employee)
        dead, _t2 = self.Session._issue(self.employee)
        dead.write({'revoked': True,
                    'expire_at': fields.Datetime.now() - timedelta(days=30)})
        self.Session._gc_sessions(days=0)
        self.assertTrue(alive.exists())
        self.assertFalse(dead.exists())

    def test_search_state_filter(self):
        session, _t = self.Session._issue(self.employee)
        self.assertIn(session, self.Session.search([('state', '=', 'active')]))
        session.action_revoke()
        self.assertNotIn(session, self.Session.search([('state', '=', 'active')]))
        self.assertIn(session, self.Session.search([('state', '=', 'revoked')]))


@tagged('post_install', '-at_install')
class TestThrottle(FoomAttendanceCommon):

    def test_blocks_after_max_attempts(self):
        key = 'test:key'
        for _i in range(4):
            self.assertFalse(self.Throttle._register_failure(key, 5, 15, 10))
            self.assertFalse(self.Throttle._is_blocked(key))
        until = self.Throttle._register_failure(key, 5, 15, 10)
        self.assertTrue(until)
        self.assertTrue(self.Throttle._is_blocked(key))

    def test_success_clears_counter(self):
        key = 'test:key2'
        self.Throttle._register_failure(key, 5, 15, 10)
        self.Throttle._register_failure(key, 5, 15, 10)
        self.Throttle._register_success(key)
        for _i in range(4):
            self.assertFalse(self.Throttle._register_failure(key, 5, 15, 10),
                             "penghitung harus mulai dari nol lagi")

    def test_window_resets_counter(self):
        key = 'test:key3'
        rec = self.Throttle._get(key)
        self.Throttle._register_failure(key, 5, 15, 10)
        rec.window_start = fields.Datetime.now() - timedelta(hours=2)
        self.Throttle._register_failure(key, 5, 15, 10)
        self.assertEqual(rec.counter, 1, "jendela lama harus dilupakan")

    def test_block_expires(self):
        key = 'test:key4'
        for _i in range(5):
            self.Throttle._register_failure(key, 5, 15, 10)
        rec = self.Throttle._get(key)
        rec.blocked_until = fields.Datetime.now() - timedelta(minutes=1)
        self.assertFalse(self.Throttle._is_blocked(key))
