"""HttpCase tests for table_layout_api.

Builds its own minimal fixtures in setUpClass rather than relying on demo
data. For the "occupied" case, this creates pos.session/pos.order records
directly via the ORM instead of going through POS's own session-opening
wizard -- deliberately: what's under test here is THIS module's auth/
scoping/occupancy-read logic, not point_of_sale's own session-opening
business rules (which have their own, unrelated required setup -- cash
payment methods, closing control sequences, etc.).

If your database's pos.session/pos.order carry additional required fields
from other custom modules (139+ installed on the production instance this
was written for), adjust _open_order_on() below to match -- same
"verify against your instance" caveat as the rest of this module, see
README.md's verification checklist.
"""
import unittest
import xml.etree.ElementTree as ET

from odoo.tests import HttpCase, tagged

from ..controllers.table_layout import _table_name, _table_payload, _table_svg

API_KEY_PARAM = 'table_layout_api.key'


class _FakeTableWithoutName:
    """Reproduces a real production crash: a database whose restaurant.table
    has no `name` field at all (customized away -- not just blank). Plain
    unittest.TestCase, not HttpCase -- this is a pure-function regression
    test for _table_name()'s hasattr guard, doesn't need a live Odoo request
    to exercise it."""
    id = 999
    position_h = position_v = 0.0
    width = height = 50.0
    shape = 'square'
    color = None
    seats = 2
    active = True
    display_name = 'Table_999'
    # deliberately no .name attribute


class TestTableNameFallback(unittest.TestCase):
    """Regression test for the 'restaurant.table' object has no attribute
    'name' crash reported against a production instance -- see README's
    "Known real-world gap, fixed" note."""

    def test_table_name_falls_back_to_display_name(self):
        table = _FakeTableWithoutName()
        self.assertEqual(_table_name(table), 'Table_999')

    def test_table_payload_does_not_crash_without_name_field(self):
        table = _FakeTableWithoutName()
        payload = _table_payload(table, occupied_ids=set())
        self.assertEqual(payload['name'], 'Table_999')

    def test_table_svg_does_not_crash_without_name_field(self):
        table = _FakeTableWithoutName()
        svg_fragment = _table_svg(table, occupied=False)
        self.assertIn('Table_999', svg_fragment)


@tagged('post_install', '-at_install')
class TestTableLayoutApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.api_key = cls.icp.get_param(API_KEY_PARAM)
        assert cls.api_key, 'post_init_hook should have created this key on module install'

        cls.company = cls.env['res.company'].create({'name': 'Table Layout Test Co'})
        cls.pos_config = cls.env['pos.config'].create({
            'name': 'Test POS',
            'company_id': cls.company.id,
        })
        cls.floor = cls.env['restaurant.floor'].create(cls._floor_vals())
        cls.table_a = cls.env['restaurant.table'].create({
            'name': 'T1', 'floor_id': cls.floor.id, 'seats': 4,
            'position_h': 100.0, 'position_v': 50.0, 'width': 80.0, 'height': 80.0,
            'shape': 'square',
        })
        cls.table_b = cls.env['restaurant.table'].create({
            'name': 'T2', 'floor_id': cls.floor.id, 'seats': 2,
            'position_h': 250.0, 'position_v': 50.0, 'width': 60.0, 'height': 60.0,
            'shape': 'round',
        })

    @classmethod
    def _floor_vals(cls):
        """Links the fixture floor to cls.pos_config regardless of whether
        this database's restaurant.floor uses pos_config_ids (M2M) or
        pos_config_id (M2O) -- same probe the controller itself uses."""
        floor_fields = cls.env['restaurant.floor'].fields_get(['pos_config_ids', 'pos_config_id'])
        vals = {'name': 'Main Floor'}
        if 'pos_config_ids' in floor_fields:
            vals['pos_config_ids'] = [(6, 0, [cls.pos_config.id])]
        elif 'pos_config_id' in floor_fields:
            vals['pos_config_id'] = cls.pos_config.id
        else:
            raise AssertionError('restaurant.floor has neither pos_config_ids nor pos_config_id')
        return vals

    def _open_order_on(self, table):
        session = self.env['pos.session'].create({'config_id': self.pos_config.id})
        session.sudo().write({'state': 'opened'})
        self.env['pos.order'].create({
            'company_id': self.company.id,
            'session_id': session.id,
            'table_id': table.id,
            'state': 'draft',
            'amount_total': 0, 'amount_tax': 0, 'amount_paid': 0, 'amount_return': 0,
        })
        return session

    def _get(self, path, headers=None, **params):
        if params:
            path = f'{path}?' + '&'.join(f'{k}={v}' for k, v in params.items())
        return self.url_open(path, headers=headers or {})

    # ------------------------------------------------------------------
    def test_missing_key_is_unauthorized(self):
        res = self._get('/api/v1/table-layout')
        self.assertEqual(res.status_code, 401)

    def test_wrong_key_is_unauthorized(self):
        res = self._get('/api/v1/table-layout', headers={'X-API-Key': 'not-the-real-key'})
        self.assertEqual(res.status_code, 401)

    def test_blank_configured_key_is_service_unavailable(self):
        self.icp.set_param(API_KEY_PARAM, '')
        try:
            res = self._get('/api/v1/table-layout', headers={'X-API-Key': 'anything'})
            self.assertEqual(res.status_code, 503)
        finally:
            self.icp.set_param(API_KEY_PARAM, self.api_key)

    def test_full_layout_valid_key(self):
        res = self._get(
            '/api/v1/table-layout', headers={'X-API-Key': self.api_key}, company_ids=self.company.id,
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['success'])
        [company_entry] = [c for c in body['data'] if c['company_id'] == self.company.id]
        [floor_entry] = company_entry['floors']
        self.assertEqual({t['name'] for t in floor_entry['tables']}, {'T1', 'T2'})

    def test_unknown_company_id_is_not_found(self):
        res = self._get(
            '/api/v1/table-layout', headers={'X-API-Key': self.api_key}, company_ids=999999,
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['error']['code'], 'company_not_found')

    def test_pos_config_id_outside_scope_is_not_found(self):
        other_company = self.env['res.company'].create({'name': 'Other Co'})
        other_config = self.env['pos.config'].create({'name': 'Other POS', 'company_id': other_company.id})
        res = self._get(
            '/api/v1/table-layout', headers={'X-API-Key': self.api_key},
            company_ids=self.company.id, pos_config_id=other_config.id,
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['error']['code'], 'pos_config_not_found')

    def test_occupied_table_reported_correctly(self):
        self._open_order_on(self.table_a)
        res = self._get(
            '/api/v1/table-layout', headers={'X-API-Key': self.api_key}, company_ids=self.company.id,
        )
        [floor_entry] = res.json()['data'][0]['floors']
        by_name = {t['name']: t['status'] for t in floor_entry['tables']}
        self.assertEqual(by_name['T1'], 'occupied')
        self.assertEqual(by_name['T2'], 'available')

    def test_status_endpoint_matches_full_layout_occupancy(self):
        self._open_order_on(self.table_a)
        res = self._get(
            '/api/v1/table-layout/status', headers={'X-API-Key': self.api_key}, company_ids=self.company.id,
        )
        body = res.json()
        self.assertEqual(body['data'][str(self.table_a.id)], 'occupied')
        self.assertEqual(body['data'][str(self.table_b.id)], 'available')
        self.assertNotIn('floors', body)

    def test_companies_endpoint_lists_this_company(self):
        res = self._get('/api/v1/table-layout/companies', headers={'X-API-Key': self.api_key})
        body = res.json()
        [entry] = [c for c in body['data'] if c['company_id'] == self.company.id]
        self.assertEqual(entry['floor_count'], 1)
        self.assertEqual(entry['table_count'], 2)

    def test_post_is_rejected(self):
        res = self.url_open(
            '/api/v1/table-layout', data=b'{}',
            headers={'X-API-Key': self.api_key, 'Content-Type': 'application/json'},
        )
        self.assertNotEqual(res.status_code, 200)

    # -- render-floor-svg ----------------------------------------------
    def test_floor_svg_valid_key(self):
        res = self._get(
            f'/api/v1/table-layout/floors/{self.floor.id}/svg',
            headers={'X-API-Key': self.api_key},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers.get('Content-Type', '').startswith('image/svg+xml'))
        body = res.text
        self.assertIn('T1', body)
        self.assertIn('T2', body)

    def test_floor_svg_occupied_table_has_different_stroke(self):
        self._open_order_on(self.table_a)
        res = self._get(
            f'/api/v1/table-layout/floors/{self.floor.id}/svg',
            headers={'X-API-Key': self.api_key},
        )
        root = ET.fromstring(res.text)
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        strokes = set()
        for g in root.findall('svg:g', ns):
            shape = g[0]
            strokes.add(shape.get('stroke'))
        self.assertEqual(len(strokes), 2, 'occupied and available tables should render with different strokes')

    def test_floor_svg_unknown_floor_is_not_found(self):
        res = self._get(
            '/api/v1/table-layout/floors/999999/svg',
            headers={'X-API-Key': self.api_key},
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['error']['code'], 'floor_not_found')

    def test_floor_svg_missing_key_is_unauthorized(self):
        res = self._get(f'/api/v1/table-layout/floors/{self.floor.id}/svg')
        self.assertEqual(res.status_code, 401)
        # Error path stays JSON even on this route -- not a half-built SVG body.
        self.assertTrue(res.headers.get('Content-Type', '').startswith('application/json'))

    def test_floor_svg_escapes_table_name(self):
        self.table_a.write({'name': 'T1 <script>'})
        try:
            res = self._get(
                f'/api/v1/table-layout/floors/{self.floor.id}/svg',
                headers={'X-API-Key': self.api_key},
            )
            self.assertNotIn('<script>', res.text)
            # Must still be well-formed XML -- this raises if escaping was skipped.
            ET.fromstring(res.text)
        finally:
            self.table_a.write({'name': 'T1'})
