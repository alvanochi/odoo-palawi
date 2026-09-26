"""Read-only REST API for the POS Table/Floor layout.

See .spec/features/expose-table-layout/design.md for the full design. In
short: an external application fetches the exact geometry Odoo's own POS
Floor Plan screen uses -- floors, tables, position/shape/size/seats -- plus
live table occupancy, over a plain GET + API-key call, instead of through
Odoo's session-based JSON-RPC web client API.
"""
import logging
from xml.sax.saxutils import escape

from odoo import http
from odoo.http import request

from .api_auth import ApiError, _json, _svg, require_api_key

_logger = logging.getLogger(__name__)

PREFIX = '/api/v1/table-layout'
ROUTE_OPTS = dict(type='http', auth='public', save_session=False, cors='*', methods=['GET', 'OPTIONS'])

# Process-lifetime (not per-request) memo of geometry fields already found
# missing on this database, so a schema quirk is logged once, not spammed.
_WARNED_MISSING_FIELDS = set()


# ----------------------------------------------------------------------
# Scoping helpers -- shared by all three routes below
# ----------------------------------------------------------------------
def _parse_ids(raw):
    """'1,3' -> [1, 3]; '' / None -> None (meaning "no filter, take all")."""
    if not raw:
        return None
    ids = []
    for chunk in raw.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.isdigit():
            raise ApiError(400, 'bad_request', f'"{chunk}" is not a valid id.')
        ids.append(int(chunk))
    return ids or None


def _companies_in_scope(env, company_ids_param):
    """None -> every company. Given ids -> those, 404 if any is unknown."""
    Company = env['res.company']
    ids = _parse_ids(company_ids_param)
    if ids is None:
        return Company.search([])
    companies = Company.search([('id', 'in', ids)])
    missing = sorted(set(ids) - set(companies.ids))
    if missing:
        raise ApiError(404, 'company_not_found', f'Unknown company_id(s): {missing}')
    return companies


def _pos_configs_for(env, companies, pos_config_id_param):
    """pos.config recordset for these companies, optionally narrowed to one
    pos_config_id. 404 if that id isn't within the resolved company scope --
    covers both "doesn't exist" and "exists but belongs elsewhere"."""
    configs = env['pos.config'].search([('company_id', 'in', companies.ids)])
    if pos_config_id_param:
        if not str(pos_config_id_param).isdigit():
            raise ApiError(400, 'bad_request', 'pos_config_id must be an integer.')
        pos_config_id = int(pos_config_id_param)
        configs = configs.filtered(lambda c: c.id == pos_config_id)
        if not configs:
            raise ApiError(
                404, 'pos_config_not_found',
                f'pos_config_id {pos_config_id} was not found within the given company scope.',
            )
    return configs


def _floor_pos_config_field(env):
    """Which field links a floor to its POS config(s), resolved once via
    fields_get -- NOT guessed. restaurant.floor shipped pos_config_id
    (Many2one) in older Odoo builds and pos_config_ids (Many2many) in newer
    ones; this database's actual shape is checked directly.

    Returns (field_name, is_many2many).
    """
    fields = env['restaurant.floor'].fields_get(['pos_config_ids', 'pos_config_id'])
    if 'pos_config_ids' in fields:
        return 'pos_config_ids', True
    if 'pos_config_id' in fields:
        return 'pos_config_id', False
    # A real environment mismatch -- fail loudly rather than silently return
    # wrong/empty data.
    raise ApiError(
        500, 'layout_schema_mismatch',
        'restaurant.floor has neither pos_config_ids nor pos_config_id on this database.',
    )


def _floors_for(env, pos_configs):
    if not pos_configs:
        return env['restaurant.floor']
    field_name, _is_m2m = _floor_pos_config_field(env)
    return env['restaurant.floor'].search([(field_name, 'in', pos_configs.ids)])


def _table_field(table, name):
    """getattr with a logged-once fallback -- one unexpectedly-missing
    geometry field degrades to null instead of 500ing the whole endpoint."""
    if hasattr(table, name):
        return getattr(table, name)
    if name not in _WARNED_MISSING_FIELDS:
        _WARNED_MISSING_FIELDS.add(name)
        _logger.warning(
            'table_layout_api: restaurant.table has no field "%s" on this database -- '
            'returning null for it from now on.', name,
        )
    return None


def _table_name(table):
    """table.name is accessed unconditionally everywhere else in this
    module (the JSON payload's identifying field, the SVG label) -- but
    "name" isn't actually a guaranteed field the way position_h/width/etc.
    are already treated as *possibly* missing. Route it through the same
    hasattr-guarded _table_field so a database whose restaurant.table
    doesn't define "name" (renamed/removed by a customization) degrades to
    Odoo's own always-present display_name instead of a 500 on every route
    that touches a table, same "log once, don't crash" spirit as every
    other field here."""
    value = _table_field(table, 'name')
    return value if value else table.display_name


def _occupied_table_ids(env, table_ids):
    """One batched query, not one per table: every table with an open
    pos.order (draft/paid) under a currently-opened pos.session."""
    if not table_ids:
        return set()
    sessions = env['pos.session'].search([('state', '=', 'opened')])
    if not sessions:
        return set()
    orders = env['pos.order'].search([
        ('session_id', 'in', sessions.ids),
        ('table_id', 'in', table_ids),
        ('state', 'in', ('draft', 'paid')),
    ])
    return set(orders.mapped('table_id').ids)


# ----------------------------------------------------------------------
# SVG rendering -- GET /api/v1/table-layout/floors/<id>/svg
# ----------------------------------------------------------------------
_STROKE_OCCUPIED = '#D64545'
_STROKE_AVAILABLE = '#3FA34D'
_DEFAULT_FILL = '#CFCFCF'
_DEFAULT_BG = '#F7F7F7'
_VIEWBOX_PADDING = 20


def _table_svg(table, occupied):
    x = _table_field(table, 'position_h') or 0
    y = _table_field(table, 'position_v') or 0
    w = _table_field(table, 'width') or 0
    h = _table_field(table, 'height') or 0
    shape = _table_field(table, 'shape')
    fill = _table_field(table, 'color') or _DEFAULT_FILL
    name = _table_name(table)
    stroke = _STROKE_OCCUPIED if occupied else _STROKE_AVAILABLE

    if shape == 'round':
        cx, cy = x + w / 2, y + h / 2
        shape_svg = (
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w / 2:.1f}" ry="{h / 2:.1f}" '
            f'fill="{escape(fill)}" stroke="{stroke}" stroke-width="3"/>'
        )
    else:
        shape_svg = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" ry="6" '
            f'fill="{escape(fill)}" stroke="{stroke}" stroke-width="3"/>'
        )

    font_size = max(min(w, h) * 0.18, 10)
    label_svg = (
        f'<text x="{x + w / 2:.1f}" y="{y + h / 2:.1f}" font-size="{font_size:.1f}" '
        f'text-anchor="middle" dominant-baseline="middle" fill="#222222">{escape(name)}</text>'
    )
    return f'<g>{shape_svg}{label_svg}</g>'


def _render_floor_svg(floor, occupied_ids):
    tables = floor.table_ids
    if tables:
        xs_min = min(_table_field(t, 'position_h') or 0 for t in tables)
        ys_min = min(_table_field(t, 'position_v') or 0 for t in tables)
        xs_max = max(
            (_table_field(t, 'position_h') or 0) + (_table_field(t, 'width') or 0) for t in tables
        )
        ys_max = max(
            (_table_field(t, 'position_v') or 0) + (_table_field(t, 'height') or 0) for t in tables
        )
    else:
        xs_min = ys_min = xs_max = ys_max = 0

    vb_x, vb_y = xs_min - _VIEWBOX_PADDING, ys_min - _VIEWBOX_PADDING
    vb_w = max((xs_max - xs_min) + 2 * _VIEWBOX_PADDING, 1)
    vb_h = max((ys_max - ys_min) + 2 * _VIEWBOX_PADDING, 1)

    bg = getattr(floor, 'background_color', None) or _DEFAULT_BG
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x:.1f} {vb_y:.1f} {vb_w:.1f} {vb_h:.1f}">',
        f'<rect x="{vb_x:.1f}" y="{vb_y:.1f}" width="{vb_w:.1f}" height="{vb_h:.1f}" '
        f'fill="{escape(bg)}"/>',
    ]
    parts.extend(_table_svg(t, occupied=t.id in occupied_ids) for t in tables)
    parts.append('</svg>')
    return ''.join(parts)


def _table_payload(table, occupied_ids):
    return {
        'id': table.id,
        'name': _table_name(table),
        'shape': _table_field(table, 'shape'),
        'position_h': _table_field(table, 'position_h'),
        'position_v': _table_field(table, 'position_v'),
        'width': _table_field(table, 'width'),
        'height': _table_field(table, 'height'),
        'seats': _table_field(table, 'seats'),
        'color': _table_field(table, 'color'),
        'active': table.active,
        'status': 'occupied' if table.id in occupied_ids else 'available',
    }


def _floor_pos_config_ids(floor, pos_config_field, is_m2m):
    value = getattr(floor, pos_config_field)
    if is_m2m:
        return value.ids
    return [value.id] if value else []


def _floor_payload(floor, occupied_ids, pos_config_field, is_m2m):
    return {
        'id': floor.id,
        'name': floor.name,
        'sequence': floor.sequence,
        'background_color': getattr(floor, 'background_color', None),
        'pos_config_ids': _floor_pos_config_ids(floor, pos_config_field, is_m2m),
        'tables': [_table_payload(t, occupied_ids) for t in floor.table_ids],
    }


def _build_layout(env, company_ids_param, pos_config_id_param):
    companies = _companies_in_scope(env, company_ids_param)
    all_pos_configs = _pos_configs_for(env, companies, pos_config_id_param)
    pos_config_field, is_m2m = _floor_pos_config_field(env)

    data = []
    for company in companies:
        company_pos_configs = all_pos_configs.filtered(lambda c: c.company_id == company)
        floors = _floors_for(env, company_pos_configs)
        occupied_ids = _occupied_table_ids(env, floors.mapped('table_ids').ids)
        data.append({
            'company_id': company.id,
            'company_name': company.name,
            # A company with no POS config (or none matching pos_config_id)
            # in scope still gets an entry, just with an empty list -- same
            # "include the company, say it has nothing" style as
            #coa_api's per-company results.
            'floors': [_floor_payload(f, occupied_ids, pos_config_field, is_m2m) for f in floors],
        })
    return data


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
class TableLayoutController(http.Controller):

    @http.route(PREFIX, **ROUTE_OPTS)
    @require_api_key
    def table_layout(self, company_ids=None, pos_config_id=None, **kw):
        data = _build_layout(request.env, company_ids, pos_config_id)
        return _json({'success': True, 'count': len(data), 'data': data})

    @http.route(f'{PREFIX}/status', **ROUTE_OPTS)
    @require_api_key
    def table_layout_status(self, company_ids=None, pos_config_id=None, **kw):
        env = request.env
        companies = _companies_in_scope(env, company_ids)
        pos_configs = _pos_configs_for(env, companies, pos_config_id)
        floors = _floors_for(env, pos_configs)
        table_ids = floors.mapped('table_ids').ids
        occupied_ids = _occupied_table_ids(env, table_ids)
        status = {str(tid): ('occupied' if tid in occupied_ids else 'available') for tid in table_ids}
        return _json({'success': True, 'data': status})

    @http.route(f'{PREFIX}/floors/<int:floor_id>/svg', **ROUTE_OPTS)
    @require_api_key
    def table_layout_floor_svg(self, floor_id, **kw):
        floor = request.env['restaurant.floor'].browse(floor_id)
        if not floor.exists():
            raise ApiError(404, 'floor_not_found', f'No floor with id {floor_id}.')
        occupied_ids = _occupied_table_ids(request.env, floor.table_ids.ids)
        return _svg(_render_floor_svg(floor, occupied_ids))

    @http.route(f'{PREFIX}/companies', **ROUTE_OPTS)
    @require_api_key
    def table_layout_companies(self, company_ids=None, **kw):
        env = request.env
        companies = _companies_in_scope(env, company_ids)
        # Resolved (and validated) once up front so a schema mismatch on an
        # otherwise-empty database still surfaces clearly.
        _floor_pos_config_field(env)

        data = []
        for company in companies:
            company_pos_configs = env['pos.config'].search([('company_id', '=', company.id)])
            floors = _floors_for(env, company_pos_configs)
            if not floors:
                continue
            data.append({
                'company_id': company.id,
                'company_name': company.name,
                'floor_count': len(floors),
                'table_count': len(floors.mapped('table_ids')),
            })
        return _json({'success': True, 'count': len(data), 'data': data})
