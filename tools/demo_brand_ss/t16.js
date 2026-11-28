// Payment source per request type (Finance + Admin configurable) and "Bayar dari (Bank/Kas)" on requests.
const { login, kw, CID } = require('./rpc');
const { SA } = require('./approval_ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function ref(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
async function xid(module, name, model, res_id) { const e = await kw('ir.model.data', 'search', [[['module', '=', module], ['name', '=', name]]]); if (!e.length) await kw('ir.model.data', 'create', [{ module, name, model, res_id, noupdate: true }]); }
const TRANSFER_TYPES = ['riset', 'kantor', 'event', 'campaign'];
(async () => {
  await login();
  const sys = await ref('base.group_system');
  const gUser = (await kw('res.groups', 'search', [[['name', '=', 'SS Approval / Pengguna']]]))[0];
  const dewi = (await kw('res.users', 'search', [[['login', '=', 'ss.dewi']]]))[0];
  // 1) Finance group (only Finance staff, not Direktur)
  const gFin = await foc('res.groups', [['name', '=', 'SS Approval / Finance']], { name: 'SS Approval / Finance', comment: 'Finance Brand SS: boleh mengatur rekening & akun pembayaran per jenis pengajuan.' });
  await kw('res.groups', 'write', [[gFin], { users: [[4, dewi]] }]);
  await xid('ss_demo', 'group_approval_finance', 'res.groups', gFin);

  // 2) config model
  const CM = 'x_ss_approval_type_conf';
  let M = (await kw('ir.model', 'search', [[['model', '=', CM]]]))[0];
  if (!M) M = await kw('ir.model', 'create', [{ name: 'Pengaturan Jenis Pengajuan', model: CM, state: 'manual', is_mail_thread: true }]);
  async function field(mid, vals) { const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]); if (ex.length) return ex[0]; return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]); }
  const typeSel = (await kw('ir.model.fields.selection', 'search_read', [[['field_id.model', '=', 'x_ss_approval'], ['field_id.name', '=', 'x_type']]], { fields: ['value', 'name', 'sequence'] }));
  await field(M, { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company', required: true, on_delete: 'cascade' });
  await field(M, { name: 'x_type', field_description: 'Jenis Pengajuan', ttype: 'selection', required: true, tracking: 1, selection_ids: typeSel.map(s => [0, 0, { value: s.value, name: s.name, sequence: s.sequence }]) });
  await field(M, { name: 'x_journal_id', field_description: 'Rekening Default (Bank/Kas)', ttype: 'many2one', relation: 'account.journal', tracking: 1 });
  await field(M, { name: 'x_account_id', field_description: 'Akun Biaya', ttype: 'many2one', relation: 'account.account', tracking: 1 });
  await field(M, { name: 'x_note', field_description: 'Catatan', ttype: 'text' });
  for (const [g, w] of [[gUser, false], [gFin, true], [sys, true]])
    await foc('ir.model.access', [['model_id', '=', M], ['group_id', '=', g]], { name: 'access ' + CM + ' ' + g, model_id: M, group_id: g, perm_read: true, perm_write: w, perm_create: w, perm_unlink: w });
  await foc('ir.rule', [['model_id', '=', M], ['name', '=', 'Type conf multi-company']], { name: 'Type conf multi-company', model_id: M, domain_force: "[('x_company_id', 'in', company_ids)]" });
  async function view(name, type, model, arch) { const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]); if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; } return kw('ir.ui.view', 'create', [{ name, type, model, arch_db: arch }]); }
  await view(CM + '.list', 'list', CM, `<list editable="bottom"><field name="x_name"/><field name="x_type"/><field name="x_journal_id" domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', x_company_id)]"/><field name="x_account_id" domain="[('account_type', 'in', ['expense', 'expense_direct_cost'])]"/><field name="x_note" optional="hide"/><field name="x_company_id" column_invisible="1"/></list>`);
  await view(CM + '.form', 'form', CM, `<form><sheet><div class="oe_title"><h1><field name="x_name" placeholder="cth: Dana Riset"/></h1></div><group><group><field name="x_type"/><field name="x_journal_id" domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', x_company_id)]"/><field name="x_account_id" domain="[('account_type', 'in', ['expense', 'expense_direct_cost'])]"/><field name="x_company_id" invisible="1"/></group><group><div class="alert alert-info" role="alert" colspan="2">Rekening ini terisi otomatis di field <b>Bayar dari (Bank/Kas)</b> saat pengajuan disetujui. Finance tetap bisa menggantinya sebelum klik Transfer Dana.</div></group></group><field name="x_note" placeholder="Catatan"/></sheet><chatter/></form>`);
  let act = (await kw('ir.actions.act_window', 'search', [[['res_model', '=', CM]]]))[0];
  const av = { name: 'Pengaturan Jenis Pengajuan', res_model: CM, view_mode: 'list,form', context: "{'default_x_company_id': allowed_company_ids[0]}" };
  if (act) await kw('ir.actions.act_window', 'write', [[act], av]); else act = await kw('ir.actions.act_window', 'create', [av]);
  // 3) menus: Konfigurasi = Admin + Finance; Aturan Approval = Admin only; new menu = Admin + Finance
  const root = (await kw('ir.ui.menu', 'search', [[['name', '=', 'Pengajuan & Approval'], ['parent_id', '=', false]]]))[0];
  const conf = (await kw('ir.ui.menu', 'search', [[['name', '=', 'Konfigurasi'], ['parent_id', '=', root]]]))[0];
  await kw('ir.ui.menu', 'write', [[conf], { groups_id: [[6, 0, [sys, gFin]]] }]);
  const rules = (await kw('ir.ui.menu', 'search', [[['name', '=', 'Aturan Approval'], ['parent_id', '=', conf]]]))[0];
  await kw('ir.ui.menu', 'write', [[rules], { groups_id: [[6, 0, [sys]]] }]);
  const tm = await foc('ir.ui.menu', [['name', '=', 'Pengaturan Jenis Pengajuan'], ['parent_id', '=', conf]], { name: 'Pengaturan Jenis Pengajuan', parent_id: conf, action: 'ir.actions.act_window,' + act, sequence: 2 });
  await kw('ir.ui.menu', 'write', [[tm], { groups_id: [[6, 0, [sys, gFin]]] }]);

  // 4) seed defaults
  const J = async code => (await kw('account.journal', 'search', [[['code', '=', code], ['company_id', '=', CID]]]))[0];
  const A = async code => (await kw('account.account', 'search', [[['code', '=', code], ['company_ids', 'in', [CID]]]]))[0];
  const SEED = [['Dana Riset / Budget Proyek', 'riset', 'BCA', '63110100'], ['Kebutuhan Operasional Kantor', 'kantor', 'CSH1', '63110120'], ['Event & Partnership', 'event', 'BCA', '61200070'], ['Campaign / Iklan / KOL', 'campaign', 'BCA', '61200010']];
  for (const [n, t, j, a] of SEED) await foc(CM, [['x_type', '=', t], ['x_company_id', '=', CID]], { x_name: n, x_type: t, x_company_id: CID, x_journal_id: await J(j), x_account_id: await A(a) });

  // 5) request field "Bayar dari (Bank/Kas)" + form
  const AM = (await kw('ir.model', 'search', [[['model', '=', 'x_ss_approval']]]))[0];
  await field(AM, { name: 'x_journal_id', field_description: 'Bayar dari (Bank/Kas)', ttype: 'many2one', relation: 'account.journal', tracking: 1, copied: false });
  const fv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval.form']]], { fields: ['arch_db'] }))[0];
  let arch = fv.arch_db;
  if (!arch.includes('name="x_journal_id"')) {
    arch = arch.replace('<field name="x_transfer_move_id" invisible="not x_transfer_move_id"/>',
      `<field name="x_journal_id" invisible="x_state not in ('approved', 'done') or x_type not in ('riset', 'kantor', 'event', 'campaign')" readonly="x_state != 'approved'" groups="ss_demo.group_approval_finance,base.group_system,account.group_account_manager" domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', x_company_id)]" options="{'no_create': True}"/>\n        <field name="x_transfer_move_id" invisible="not x_transfer_move_id"/>`);
    arch = arch.replace('confirm="Transfer dana dari Bank BCA dan tandai pengajuan selesai?"', 'confirm="Transfer dana dari rekening di field \'Bayar dari (Bank/Kas)\' dan tandai pengajuan selesai?"');
    await kw('ir.ui.view', 'write', [[fv.id], { arch_db: arch }]);
  }

  // 6) transfer code: journal & account from request / config, BCA + code map as fallback
  let tc = (await kw('ir.actions.server', 'read', [[SA.transfer || (await kw('ir.actions.server', 'search', [[['name', '=', 'SS Approval: transfer']]]))[0]]], { fields: ['code', 'id'] }))[0];
  let code = tc.code;
  if (!code.includes('x_ss_approval_type_conf')) {
    code = code.replace("    bank = env['account.journal'].sudo().search([('code', '=', 'BCA'), ('company_id', '=', company.id)], limit=1)\n",
      "    conf = env['x_ss_approval_type_conf'].sudo().search([('x_type', '=', rec.x_type), ('x_company_id', '=', company.id)], limit=1)\n    bank = rec.x_journal_id or conf.x_journal_id or env['account.journal'].sudo().search([('code', '=', 'BCA'), ('company_id', '=', company.id)], limit=1)\n    if bank.type not in ('bank', 'cash') or bank.company_id != company:\n        raise UserError('Rekening sumber dana harus jurnal Bank/Kas milik %s.' % company.name)\n");
    code = code.replace("    acc = env['account.account'].sudo().search([('code', '=', codes.get(rec.x_type, '69000000')), ('company_ids', 'in', company.ids)], limit=1)\n",
      "    acc = conf.x_account_id or env['account.account'].sudo().search([('code', '=', codes.get(rec.x_type, '69000000')), ('company_ids', 'in', company.ids)], limit=1)\n");
    code = code.replace("    rec.write({'x_state': 'done', 'x_transfer_move_id': move.id})", "    rec.write({'x_state': 'done', 'x_transfer_move_id': move.id, 'x_journal_id': bank.id})");
    await kw('ir.actions.server', 'write', [[tc.id], { code }]);
  }
  // 7) approve: prefill "Bayar dari" when fully approved
  let ap = (await kw('ir.actions.server', 'read', [[SA.approve]], { fields: ['code'] }))[0].code;
  if (!ap.includes('x_ss_approval_type_conf')) {
    ap = ap.replace("        rec.write({'x_state': 'approved', 'x_approver_id': False, 'x_step': nxt, 'x_approved_date': datetime.datetime.now()})\n",
      "        rec.write({'x_state': 'approved', 'x_approver_id': False, 'x_step': nxt, 'x_approved_date': datetime.datetime.now()})\n        conf = env['x_ss_approval_type_conf'].sudo().search([('x_type', '=', rec.x_type), ('x_company_id', '=', rec.x_company_id.id)], limit=1)\n        if conf.x_journal_id and not rec.x_journal_id:\n            rec.write({'x_journal_id': conf.x_journal_id.id})\n");
    await kw('ir.actions.server', 'write', [[SA.approve], { code: ap }]);
  }
  // 8) prefill existing approved requests (not yet transferred)
  const open = await kw('x_ss_approval', 'search_read', [[['x_state', '=', 'approved'], ['x_type', 'in', TRANSFER_TYPES], ['x_journal_id', '=', false]]], { fields: ['x_type', 'x_number'] });
  for (const r of open) { const c = await kw(CM, 'search_read', [[['x_type', '=', r.x_type], ['x_company_id', '=', CID]]], { fields: ['x_journal_id'], limit: 1 }); if (c.length && c[0].x_journal_id) await kw('x_ss_approval', 'write', [[r.id], { x_journal_id: c[0].x_journal_id[0] }]); }
  console.log('done. group', gFin, 'menu', tm, 'prefilled', open.map(r => r.x_number));
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-4).join(String.fromCharCode(10))); process.exit(1); });
