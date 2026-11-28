// "Peran (Role)" on Brand SS employees, mirrored on approval requests as "Peran Pengaju".
const { login, kw, CID } = require('./rpc');
const ROLES = [['direktur', 'Direktur'], ['finance', 'Finance'], ['hr', 'HR & GA'], ['purchasing', 'Purchasing'], ['produksi', 'Produksi / QC'], ['gudang', 'Gudang'], ['marketplace', 'Marketplace'], ['host', 'Host Live Streaming'], ['marketing', 'Digital Marketing'], ['creative', 'Creative & Media'], ['researcher', 'Researcher'], ['toko', 'Offline Store'], ['b2b', 'Reseller & B2B'], ['cs', 'Customer Service'], ['legal', 'Legal & BD']];
const MAP = { 'Shella Saukia': 'direktur', 'Dewi Anggraini': 'finance', 'Agus Prasetyo': 'finance', 'Rina Kartika': 'hr', 'Budi Santoso': 'purchasing', 'Hendra Wijaya': 'produksi', 'Siti Nurhaliza': 'produksi', 'Joko Susilo': 'gudang', 'Andi Saputra': 'gudang', 'Maya Puspita': 'marketplace', 'Nadia Putri': 'host', 'Citra Lestari': 'host', 'Fajar Ramadhan': 'host', 'Intan Permata': 'host', 'Reza Firmansyah': 'marketing', 'Laras Wulandari': 'creative', 'Dimas Pratama': 'creative', 'Yuni Astuti': 'researcher', 'Eko Kurniawan': 'toko', 'Wulan Sari': 'b2b', 'Putri Ayu': 'cs', 'Taufik Hidayat': 'legal' };
async function field(model, vals) {
  const mid = (await kw('ir.model', 'search', [[['model', '=', model]]]))[0];
  const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]);
  if (ex.length) return ex[0];
  return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]);
}
async function inherit(name, model, parentXmlid, arch) {
  const [m, n] = parentXmlid.split('.');
  const parent = (await kw('ir.model.data', 'check_object_reference', [m, n]))[1];
  const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]);
  if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; }
  return kw('ir.ui.view', 'create', [{ name, model, inherit_id: parent, mode: 'extension', arch_db: arch }]);
}
(async () => {
  await login();
  const sel = ROLES.map(([v, n], i) => [0, 0, { value: v, name: n, sequence: i + 1 }]);
  // 1) employee field + values
  await field('hr.employee', { name: 'x_ss_role', field_description: 'Peran (Role)', ttype: 'selection', tracking: 1, selection_ids: sel, help: 'Peran karyawan Brand SS dalam alur kerja dan approval.' });
  const emps = await kw('hr.employee', 'search_read', [[['company_id', '=', CID]]], { fields: ['name'] });
  for (const e of emps) if (MAP[e.name]) await kw('hr.employee', 'write', [[e.id], { x_ss_role: MAP[e.name] }]);
  await inherit('hr.employee.form.x_ss_role', 'hr.employee', 'hr.view_employee_form', `<data><xpath expr="//field[@name='job_title']" position="after"><field name="x_ss_role" placeholder="Peran (Role)" invisible="company_id != ${CID}"/></xpath></data>`);
  await inherit('hr.employee.list.x_ss_role', 'hr.employee', 'hr.view_employee_tree', `<data><xpath expr="//field[@name='name']" position="after"><field name="x_ss_role" optional="hide"/></xpath></data>`).catch(e => console.log('list view', e.message));
  await inherit('hr.employee.search.x_ss_role', 'hr.employee', 'hr.view_employee_filter', `<data><xpath expr="//search" position="inside"><field name="x_ss_role"/><filter name="g_ss_role" string="Peran (Role)" context="{'group_by': 'x_ss_role'}"/></xpath></data>`).catch(e => console.log('search view', e.message));
  // 2) approval: requester role (stored, from requester's employee)
  await field('x_ss_approval', { name: 'x_requester_role', field_description: 'Peran Pengaju', ttype: 'selection', selection_ids: sel, store: true, readonly: true, depends: 'x_requester_id',
    compute: "for rec in self:\n    emp = rec.env['hr.employee'].sudo().search([('user_id', '=', rec.x_requester_id.id)], limit=1) if rec.x_requester_id else False\n    rec['x_requester_role'] = emp.x_ss_role if emp else False" });
  // existing requests: force recompute by re-writing requester
  const reqs = await kw('x_ss_approval', 'search_read', [[]], { fields: ['x_requester_id'] });
  for (const r of reqs) if (r.x_requester_id) await kw('x_ss_approval', 'write', [[r.id], { x_requester_id: r.x_requester_id[0] }]);
  // 3) approval views
  const fv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval.form']]], { fields: ['arch_db'] }))[0];
  if (!fv.arch_db.includes('x_requester_role')) await kw('ir.ui.view', 'write', [[fv.id], { arch_db: fv.arch_db.replace(/(<field name="x_requester_id"[^>]*\/>)/, '$1\n        <field name="x_requester_role"/>') }]);
  const lv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval.list']]], { fields: ['arch_db'] }))[0];
  if (!lv.arch_db.includes('x_requester_role')) await kw('ir.ui.view', 'write', [[lv.id], { arch_db: lv.arch_db.replace(/(<field name="x_requester_id"[^>]*\/>)/, '$1<field name="x_requester_role" optional="show"/>') }]);
  const sv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval.search']]], { fields: ['arch_db'] }))[0];
  if (!sv.arch_db.includes('x_requester_role')) await kw('ir.ui.view', 'write', [[sv.id], { arch_db: sv.arch_db.replace('<filter name="g_type"', '<filter name="g_role" string="Peran Pengaju" context="{\'group_by\':\'x_requester_role\'}"/><filter name="g_type"') }]);
  // verify
  console.log((await kw('hr.employee', 'search_read', [[['company_id', '=', CID], ['x_ss_role', '!=', false]]], { fields: ['name', 'x_ss_role'] })).length, 'employees with role');
  console.log(await kw('x_ss_approval', 'search_read', [[['x_requester_id.login', 'in', ['ss.yuni', 'ss.budi', 'ss.reza']]]], { fields: ['x_number', 'x_requester_id', 'x_requester_role'], limit: 4 }));
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-4).join(String.fromCharCode(10))); process.exit(1); });
