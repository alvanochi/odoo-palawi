// Turn "Peran (Role)" into master data (x_ss_role) that HR + Admin can create, and migrate existing values.
const { login, kw, CID } = require('./rpc');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function ref(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
async function xid(module, name, model, res_id) { const e = await kw('ir.model.data', 'search', [[['module', '=', module], ['name', '=', name]]]); if (!e.length) await kw('ir.model.data', 'create', [{ module, name, model, res_id, noupdate: true }]); }
async function field(model, vals) {
  const mid = (await kw('ir.model', 'search', [[['model', '=', model]]]))[0];
  const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]);
  if (ex.length) return ex[0];
  return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]);
}
async function setArch(name, fn) { const v = (await kw('ir.ui.view', 'search_read', [[['name', '=', name]]], { fields: ['arch_db'] }))[0]; if (!v) return; const a = fn(v.arch_db); if (a !== v.arch_db) await kw('ir.ui.view', 'write', [[v.id], { arch_db: a }]); }
(async () => {
  await login();
  const sys = await ref('base.group_system'), gUser = await ref('base.group_user');
  const rina = (await kw('res.users', 'search', [[['login', '=', 'ss.rina']]]))[0];
  // 1) group allowed to manage roles
  const gHR = await foc('res.groups', [['name', '=', 'SS HR / Kelola Peran']], { name: 'SS HR / Kelola Peran', comment: 'HR Brand SS: boleh menambah & mengubah master Peran (Role).' });
  await kw('res.groups', 'write', [[gHR], { users: [[4, rina]] }]);
  await xid('ss_demo', 'group_hr_role_manager', 'res.groups', gHR);
  // 2) role model
  const RM = 'x_ss_role';
  let M = (await kw('ir.model', 'search', [[['model', '=', RM]]]))[0];
  if (!M) M = await kw('ir.model', 'create', [{ name: 'Peran (Role)', model: RM, state: 'manual' }]);
  await field(RM, { name: 'x_sequence', field_description: 'Urutan', ttype: 'integer' });
  await kw('ir.model', 'write', [[M], { order: 'x_sequence, id' }]);
  await field(RM, { name: 'x_active', field_description: 'Aktif', ttype: 'boolean' });
  await field(RM, { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company' });
  await field(RM, { name: 'x_description', field_description: 'Keterangan', ttype: 'text' });
  for (const [g, w] of [[gUser, false], [gHR, true], [sys, true]])
    await foc('ir.model.access', [['model_id', '=', M], ['group_id', '=', g]], { name: 'access x_ss_role ' + g, model_id: M, group_id: g, perm_read: true, perm_write: w, perm_create: w, perm_unlink: w });
  await foc('ir.rule', [['model_id', '=', M], ['name', '=', 'Role multi-company']], { name: 'Role multi-company', model_id: M, domain_force: "['|', ('x_company_id', '=', False), ('x_company_id', 'in', company_ids)]" });
  const view = async (name, type, arch) => { const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]); if (ex.length) return kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return kw('ir.ui.view', 'create', [{ name, type, model: RM, arch_db: arch }]); };
  await view('x_ss_role.list', 'list', `<list editable="bottom"><field name="x_sequence" widget="handle"/><field name="x_name"/><field name="x_description" optional="show"/><field name="x_active" widget="boolean_toggle"/><field name="x_company_id" column_invisible="1"/></list>`);
  await view('x_ss_role.form', 'form', `<form><sheet><group><field name="x_name"/><field name="x_description"/><field name="x_sequence"/><field name="x_active"/><field name="x_company_id" invisible="1"/></group></sheet></form>`);
  let act = (await kw('ir.actions.act_window', 'search', [[['res_model', '=', RM]]]))[0];
  const av = { name: 'Peran (Role)', res_model: RM, view_mode: 'list,form', context: "{'default_x_company_id': allowed_company_ids[0], 'default_x_active': True, 'active_test': False}" };
  if (act) await kw('ir.actions.act_window', 'write', [[act], av]); else act = await kw('ir.actions.act_window', 'create', [av]);
  const hrConf = await ref('hr.menu_human_resources_configuration');
  const menu = await foc('ir.ui.menu', [['name', '=', 'Peran (Role)'], ['parent_id', '=', hrConf]], { name: 'Peran (Role)', parent_id: hrConf, action: 'ir.actions.act_window,' + act, sequence: 50 });
  await kw('ir.ui.menu', 'write', [[menu], { groups_id: [[6, 0, [gHR, sys]]] }]);
  // 3) role records from the old selection values
  const sel = await kw('ir.model.fields.selection', 'search_read', [[['field_id.model', '=', 'hr.employee'], ['field_id.name', '=', 'x_ss_role']]], { fields: ['value', 'name', 'sequence'], order: 'sequence' });
  const byValue = {};
  for (const s of sel) byValue[s.value] = await foc(RM, [['x_name', '=', s.name], ['x_company_id', '=', CID]], { x_name: s.name, x_sequence: s.sequence * 10, x_active: true, x_company_id: CID });
  // 4) new m2o fields + migrate
  await field('hr.employee', { name: 'x_ss_role_id', field_description: 'Peran (Role)', ttype: 'many2one', relation: RM, tracking: 1, on_delete: 'restrict' });
  const emps = await kw('hr.employee', 'search_read', [[['company_id', '=', CID], ['x_ss_role', '!=', false]]], { fields: ['x_ss_role'], context: { active_test: false } }).catch(() => []);
  for (const e of emps) if (byValue[e.x_ss_role]) await kw('hr.employee', 'write', [[e.id], { x_ss_role_id: byValue[e.x_ss_role] }]);
  await field('x_ss_approval', { name: 'x_requester_role_id', field_description: 'Peran Pengaju', ttype: 'many2one', relation: RM, store: true, readonly: true, depends: 'x_requester_id', on_delete: 'set null',
    compute: "for rec in self:\n    emp = rec.env['hr.employee'].sudo().search([('user_id', '=', rec.x_requester_id.id)], limit=1) if rec.x_requester_id else False\n    rec['x_requester_role_id'] = emp.x_ss_role_id if emp else False" });
  const reqs = await kw('x_ss_approval', 'search_read', [[]], { fields: ['x_requester_id'] });
  for (const r of reqs) if (r.x_requester_id) await kw('x_ss_approval', 'write', [[r.id], { x_requester_id: r.x_requester_id[0] }]);
  // 5) views -> new fields
  await setArch('hr.employee.form.x_ss_role', () => `<data><xpath expr="//field[@name='job_id']" position="after"><field name="x_ss_role_id" string="Peran (Role)" invisible="company_id != ${CID}" options="{'no_open': True}"/></xpath></data>`);
  await setArch('hr.employee.list.x_ss_role', () => `<data><xpath expr="//field[@name='name']" position="after"><field name="x_ss_role_id" optional="hide"/></xpath></data>`);
  await setArch('hr.employee.search.x_ss_role', () => `<data><xpath expr="//search" position="inside"><field name="x_ss_role_id"/><filter name="g_ss_role" string="Peran (Role)" context="{'group_by': 'x_ss_role_id'}"/></xpath></data>`);
  await setArch('x_ss_approval.form', a => a.replace('<field name="x_requester_role"/>', '<field name="x_requester_role_id" options="{\'no_open\': True}"/>'));
  await setArch('x_ss_approval.list', a => a.replace('<field name="x_requester_role" optional="show"/>', '<field name="x_requester_role_id" optional="show"/>'));
  await setArch('x_ss_approval.search', a => a.replace("context=\"{'group_by':'x_requester_role'}\"", "context=\"{'group_by':'x_requester_role_id'}\""));
  // 6) drop old selection fields once nothing references them
  for (const [model, name] of [['x_ss_approval', 'x_requester_role'], ['hr.employee', 'x_ss_role']]) {
    const users = await kw('ir.ui.view', 'search_count', [[['arch_db', 'like', `"${name}"`], ['model', '=', model]]]);
    const f = await kw('ir.model.fields', 'search', [[['model', '=', model], ['name', '=', name]]]);
    if (f.length && !users) { await kw('ir.model.fields', 'unlink', [f]); console.log('dropped', model, name); } else if (f.length) console.log('kept (still referenced)', model, name, users);
  }
  console.log('roles', Object.keys(byValue).length, 'employees migrated', emps.length, 'menu', menu);
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-4).join(String.fromCharCode(10))); process.exit(1); });
