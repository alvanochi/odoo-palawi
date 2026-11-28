// Project budget (R&D) + "Budget Proyek / Riset" approval flow:
// Researcher -> Approval Direktur -> Mengetahui Finance -> Transfer Dana by Finance -> Done. Run after t11/t13.
const { login, kw, CID } = require('./rpc');
const ids = require('./ids.json');
const { SA } = require('./approval_ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function gid(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
const STEP = process.argv[2] || 'all';
const has = s => STEP === 'all' || STEP.split(',').includes(s);

(async () => {
  await login();
  const gUser = (await kw('res.groups', 'search', [[['name', '=', 'SS Approval / Pengguna']]]))[0];
  const gMgr = (await kw('res.groups', 'search', [[['name', '=', 'SS Approval / Manager']]]))[0];
  const gContact = (await kw('res.groups', 'search', [[['name', '=', 'SS Demo / Kontak hanya PT ShellaSaukia']]]))[0];

  if (has('model')) {
    // 1) new selection value "riset" on approval + rule type
    for (const model of ['x_ss_approval', 'x_ss_approval_rule']) {
      const fid = (await kw('ir.model.fields', 'search', [[['model', '=', model], ['name', '=', 'x_type']]]))[0];
      if (!(await kw('ir.model.fields.selection', 'search_count', [[['field_id', '=', fid], ['value', '=', 'riset']]])))
        await kw('ir.model.fields.selection', 'create', [{ field_id: fid, value: 'riset', name: 'Budget Proyek / Riset', sequence: 20 }]);
    }
    const AM = (await kw('ir.model', 'search', [[['model', '=', 'x_ss_approval']]]))[0];
    const RM = (await kw('ir.model', 'search', [[['model', '=', 'x_ss_approval_rule']]]))[0];
    async function field(mid, vals) { const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]); if (ex.length) return ex[0]; return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]); }
    await field(AM, { name: 'x_transfer_move_id', field_description: 'Jurnal Transfer Dana', ttype: 'many2one', relation: 'account.move', readonly: true, copied: false });
    await field(RM, { name: 'x_override', field_description: 'Ganti aturan umum', ttype: 'boolean', help: 'Jika dicentang, pengajuan jenis ini HANYA memakai aturan khusus jenis ini (aturan "Semua jenis" diabaikan).' });
    const fa = (await kw('ir.model.fields', 'search', [[['model', '=', 'x_ss_approval'], ['name', '=', 'x_analytic_id']]]))[0];
    await kw('ir.model.fields', 'write', [[fa], { field_description: 'Proyek / Pos Anggaran' }]);

    // 2) project budget model
    const PB = 'x_ss_project_budget';
    let PM = (await kw('ir.model', 'search', [[['model', '=', PB]]]))[0];
    if (!PM) PM = await kw('ir.model', 'create', [{ name: 'Budget Proyek', model: PB, state: 'manual', is_mail_thread: true }]);
    const F = [
      { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company', required: true, on_delete: 'cascade' },
      { name: 'x_project_id', field_description: 'Proyek', ttype: 'many2one', relation: 'project.project' },
      { name: 'x_analytic_id', field_description: 'Akun Analitik Proyek', ttype: 'many2one', relation: 'account.analytic.account', required: true, on_delete: 'restrict' },
      { name: 'x_pic_id', field_description: 'Researcher / PIC', ttype: 'many2one', relation: 'res.users', tracking: 1 },
      { name: 'x_date_from', field_description: 'Mulai', ttype: 'date' },
      { name: 'x_date_to', field_description: 'Selesai', ttype: 'date' },
      { name: 'x_amount', field_description: 'Budget (Rp)', ttype: 'float', tracking: 1 },
      { name: 'x_state', field_description: 'Status', ttype: 'selection', tracking: 1, selection_ids: [[0, 0, { value: 'draft', name: 'Draft', sequence: 1 }], [0, 0, { value: 'aktif', name: 'Aktif', sequence: 2 }], [0, 0, { value: 'selesai', name: 'Selesai', sequence: 3 }]] },
      { name: 'x_note', field_description: 'Catatan', ttype: 'text' },
      { name: 'x_actual', field_description: 'Realisasi (Rp)', ttype: 'float', store: false, readonly: true, depends: '',
        compute: "for rec in self:\n    lines = rec.env['account.analytic.line'].sudo().search([('account_id', '=', rec.x_analytic_id.id), ('amount', '<', 0)]) if rec.x_analytic_id else []\n    rec['x_actual'] = -sum(l.amount for l in lines)" },
      { name: 'x_committed', field_description: 'Sedang Diajukan (Rp)', ttype: 'float', store: false, readonly: true, depends: '',
        compute: "for rec in self:\n    reqs = rec.env['x_ss_approval'].sudo().search([('x_analytic_id', '=', rec.x_analytic_id.id), ('x_state', 'in', ['submitted', 'approved'])]) if rec.x_analytic_id else []\n    rec['x_committed'] = sum(r.x_amount for r in reqs)" },
      { name: 'x_remaining', field_description: 'Sisa Budget (Rp)', ttype: 'float', store: false, readonly: true, depends: '',
        compute: "for rec in self:\n    rec['x_remaining'] = (rec.x_amount or 0.0) - rec.x_actual - rec.x_committed" },
      { name: 'x_usage', field_description: 'Terpakai (%)', ttype: 'float', store: false, readonly: true, depends: '',
        compute: "for rec in self:\n    rec['x_usage'] = ((rec.x_actual + rec.x_committed) / rec.x_amount * 100.0) if rec.x_amount else 0.0" },
      { name: 'x_request_ids', field_description: 'Pengajuan Dana', ttype: 'many2many', relation: 'x_ss_approval', store: false, readonly: true, depends: '',
        compute: "for rec in self:\n    rec['x_request_ids'] = rec.env['x_ss_approval'].search([('x_analytic_id', '=', rec.x_analytic_id.id)]) if rec.x_analytic_id else False" },
    ];
    for (const f of F) await field(PM, f);
    for (const [g, w] of [[gUser, false], [gMgr, true]])
      await foc('ir.model.access', [['model_id', '=', PM], ['group_id', '=', g]], { name: 'access x_ss_project_budget ' + g, model_id: PM, group_id: g, perm_read: true, perm_write: w, perm_create: w, perm_unlink: w });
    await foc('ir.rule', [['model_id', '=', PM], ['name', '=', 'Project budget multi-company']], { name: 'Project budget multi-company', model_id: PM, domain_force: "[('x_company_id', 'in', company_ids)]" });
    async function view(name, type, model, arch) { const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]); if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; } return kw('ir.ui.view', 'create', [{ name, type, model, arch_db: arch }]); }
    await view('x_ss_project_budget.list', 'list', PB, `<list decoration-danger="x_remaining &lt; 0" decoration-muted="x_state == 'selesai'">
  <field name="x_name"/><field name="x_pic_id" widget="many2one_avatar_user"/><field name="x_date_from" optional="show"/><field name="x_date_to" optional="show"/>
  <field name="x_amount" sum="Total"/><field name="x_actual"/><field name="x_committed"/><field name="x_remaining"/>
  <field name="x_usage" widget="progressbar"/><field name="x_state" widget="badge" decoration-success="x_state == 'aktif'"/>
</list>`);
    await view('x_ss_project_budget.form', 'form', PB, `<form>
  <header><field name="x_state" widget="statusbar" options="{'clickable': '1'}"/></header>
  <sheet>
    <div class="alert alert-danger" role="alert" invisible="x_remaining &gt;= 0"><b>Budget proyek terlampaui.</b> Pengajuan baru untuk proyek ini otomatis ditandai melebihi anggaran.</div>
    <div class="oe_title"><h1><field name="x_name" placeholder="cth: R&amp;D SS Glow Serum Gen 2"/></h1></div>
    <group>
      <group string="Proyek"><field name="x_project_id"/><field name="x_analytic_id"/><field name="x_pic_id" widget="many2one_avatar_user"/><field name="x_date_from"/><field name="x_date_to"/><field name="x_company_id" invisible="1"/></group>
      <group string="Budget vs Realisasi"><field name="x_amount"/><field name="x_actual"/><field name="x_committed"/><field name="x_remaining"/><field name="x_usage" widget="progressbar"/></group>
    </group>
    <notebook>
      <page string="Pengajuan Dana"><field name="x_request_ids"><list><field name="x_number"/><field name="x_name"/><field name="x_requester_id" widget="many2one_avatar_user"/><field name="x_amount" sum="Total"/><field name="x_approver_id"/><field name="x_state" widget="badge"/></list></field></page>
      <page string="Catatan"><field name="x_note"/></page>
    </notebook>
  </sheet>
  <chatter/>
</form>`);
    let act = (await kw('ir.actions.act_window', 'search', [[['res_model', '=', PB]]]))[0];
    const av = { name: 'Budget Proyek', res_model: PB, view_mode: 'list,form', context: "{'default_x_company_id': allowed_company_ids[0], 'default_x_state': 'aktif'}", help: '<p class="o_view_nocontent_smiling_face">Buat budget proyek pertama</p><p>Tentukan budget per proyek riset; realisasi dihitung otomatis dari dana yang ditransfer Finance.</p>' };
    if (act) await kw('ir.actions.act_window', 'write', [[act], av]); else act = await kw('ir.actions.act_window', 'create', [av]);
    const root = (await kw('ir.ui.menu', 'search', [[['name', '=', 'Pengajuan & Approval'], ['parent_id', '=', false]]]))[0];
    await foc('ir.ui.menu', [['name', '=', 'Budget Proyek'], ['parent_id', '=', root]], { name: 'Budget Proyek', parent_id: root, action: 'ir.actions.act_window,' + act, sequence: 5 });

    // 3) approval form: transfer button + transfer journal field; rule form: override flag
    const fv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval.form']]], { fields: ['arch_db'] }))[0];
    let arch = fv.arch_db;
    const TRANSFER = 'SS Approval: transfer';
    let tsa = (await kw('ir.actions.server', 'search', [[['name', '=', TRANSFER]]]))[0];
    const TCODE = `move = False
for rec in records:
    if rec.x_state != 'approved':
        raise UserError('Dana hanya bisa ditransfer untuk pengajuan yang sudah disetujui.')
    if not env.user.has_group('account.group_account_manager'):
        raise UserError('Transfer dana hanya dapat dilakukan oleh Finance.')
    company = rec.x_company_id
    bank = env['account.journal'].sudo().search([('code', '=', 'BCA'), ('company_id', '=', company.id)], limit=1)
    codes = {'riset': '63110100', 'kantor': '63110120', 'event': '61200070', 'campaign': '61200010'}
    acc = env['account.account'].sudo().search([('code', '=', codes.get(rec.x_type, '69000000')), ('company_ids', 'in', company.ids)], limit=1)
    partner = rec.x_partner_id or rec.x_requester_id.partner_id
    line = {'name': rec.x_name, 'account_id': acc.id, 'partner_id': partner.id, 'debit': rec.x_amount}
    if rec.x_analytic_id:
        line['analytic_distribution'] = {str(rec.x_analytic_id.id): 100}
    move = env['account.move'].sudo().create({'move_type': 'entry', 'journal_id': bank.id, 'date': datetime.date.today(), 'ref': '%s - %s' % (rec.x_number, rec.x_name), 'company_id': company.id, 'line_ids': [(0, 0, line), (0, 0, {'name': 'Transfer dana %s' % rec.x_number, 'account_id': bank.default_account_id.id, 'partner_id': partner.id, 'credit': rec.x_amount})]})
    move.action_post()
    rec.write({'x_state': 'done', 'x_transfer_move_id': move.id})
    rec.message_post(body='Dana Rp {:,.0f} ditransfer oleh {} dari {} (jurnal {}). Realisasi budget proyek ter-update.'.format(rec.x_amount, env.user.name, bank.name, move.name))
    rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.x_requester_id.id, summary='Dana sudah ditransfer: %s' % rec.x_number, note='Silakan lampirkan bukti penggunaan dana di pengajuan ini.')
`;
    if (tsa) await kw('ir.actions.server', 'write', [[tsa], { code: TCODE }]); else tsa = await kw('ir.actions.server', 'create', [{ name: TRANSFER, model_id: AM, state: 'code', code: TCODE }]);
    if (!arch.includes(`name="${tsa}"`)) {
      arch = arch.replace(`invisible="x_state != 'approved' or x_type == 'pembelian'"/>`,
        `invisible="x_state != 'approved' or x_type in ('pembelian', 'riset')"/>\n    <button name="${tsa}" type="action" string="Transfer Dana (Finance)" class="btn-primary" groups="account.group_account_manager" invisible="x_state != 'approved' or x_type not in ('riset', 'kantor', 'event', 'campaign')" confirm="Transfer dana dari Bank BCA dan tandai pengajuan selesai?"/>`);
      arch = arch.replace(`<field name="x_purchase_id" invisible="not x_purchase_id"/>`, `<field name="x_purchase_id" invisible="not x_purchase_id"/>\n        <field name="x_transfer_move_id" invisible="not x_transfer_move_id"/>`);
      await kw('ir.ui.view', 'write', [[fv.id], { arch_db: arch }]);
    }
    const rv = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval_rule.form']]], { fields: ['arch_db'] }))[0];
    if (!rv.arch_db.includes('x_override')) await kw('ir.ui.view', 'write', [[rv.id], { arch_db: rv.arch_db.replace('<field name="x_type"/>', '<field name="x_type"/><field name="x_override" invisible="x_type == \'all\'"/>') }]);
    const rl = (await kw('ir.ui.view', 'search_read', [[['name', '=', 'x_ss_approval_rule.list']]], { fields: ['arch_db'] }))[0];
    if (!rl.arch_db.includes('x_override')) await kw('ir.ui.view', 'write', [[rl.id], { arch_db: rl.arch_db.replace('<field name="x_type"/>', '<field name="x_type"/><field name="x_override" optional="show"/>') }]);

    // 4) submit/approve code: per-type override + project budget remaining + "Diketahui oleh"
    let sub = (await kw('ir.actions.server', 'read', [[SA.submit]], { fields: ['code'] }))[0].code;
    if (!sub.includes('x_ss_project_budget')) {
      sub = sub.replace("    over = has_budget and amount > remaining\n",
        "    pb = env['x_ss_project_budget'].sudo().search([('x_analytic_id', '=', rec.x_analytic_id.id), ('x_state', '=', 'aktif')], limit=1) if rec.x_analytic_id else False\n    if pb:\n        has_budget = True\n        remaining = pb.x_remaining\n    over = has_budget and amount > remaining\n");
      sub = sub.replace("    chain = []\n    for r in rules:",
        "    if rules.filtered(lambda r: r.x_type == rec.x_type and r.x_override):\n        rules = rules.filtered(lambda r: r.x_type == rec.x_type)\n    chain = []\n    for r in rules:");
      await kw('ir.actions.server', 'write', [[SA.submit], { code: sub }]);
    }
    let app = (await kw('ir.actions.server', 'read', [[SA.approve]], { fields: ['code'] }))[0].code;
    if (!app.includes('Diketahui')) {
      app = app.replace("    rec.message_post(body='Disetujui oleh %s sebagai %s.' % (env.user.name, label_of(key)))",
        "    lbl = label_of(key)\n    rec.message_post(body=('Diketahui oleh %s (%s).' if lbl.lower().startswith('mengetahui') else 'Disetujui oleh %s sebagai %s.') % (env.user.name, lbl))");
      await kw('ir.actions.server', 'write', [[SA.approve], { code: app }]);
    }
    require('fs').writeFileSync('approval_ids.json', JSON.stringify(Object.assign(require('./approval_ids.json'), { SA: Object.assign(SA, { transfer: tsa }) }), null, 1));
    console.log('model ready; transfer action', tsa, 'budget action', act);
  }

  if (has('data')) {
    const shella = (await kw('res.users', 'search', [[['login', '=', 'ss.shella']]]))[0], dewi = (await kw('res.users', 'search', [[['login', '=', 'ss.dewi']]]))[0];
    // researcher user
    const groups = [await gid('base.group_user'), await gid('project.group_project_user'), gUser, gContact];
    let yuni = (await kw('res.users', 'search', [[['login', '=', 'ss.yuni']]], { context: { active_test: false } }))[0];
    if (!yuni) yuni = await kw('res.users', 'create', [{ name: 'Yuni Astuti', login: 'ss.yuni', email: 'ss.yuni@demo.invalid', notification_type: 'inbox', company_id: CID, company_ids: [[6, 0, [CID]]], groups_id: [[6, 0, groups]], tz: 'Asia/Jakarta' }], { context: { no_reset_password: true } });
    await kw('res.users', 'write', [[yuni], { password: process.env.DEMO_PW }]);
    const up = (await kw('res.users', 'read', [[yuni]], { fields: ['partner_id'] }))[0].partner_id[0];
    await kw('res.partner', 'write', [[up], { company_id: CID }]);
    const emp = (await kw('hr.employee', 'search_read', [[['name', '=', 'Yuni Astuti'], ['company_id', '=', CID]]], { fields: ['work_contact_id'] }))[0];
    const dup = await kw('hr.employee', 'search', [[['user_id', '=', yuni], ['id', '!=', emp.id]]]); if (dup.length) await kw('hr.employee', 'write', [dup, { user_id: false, active: false }]);
    const oldWc = emp.work_contact_id && emp.work_contact_id[0];
    await kw('hr.employee', 'write', [[emp.id], { user_id: yuni, work_contact_id: up }]);
    if (oldWc && oldWc !== up) await kw('res.partner', 'write', [[oldWc], { active: false }]).catch(() => {});
    // rules for riset (override general rules)
    const R = 'x_ss_approval_rule';
    await foc(R, [['x_name', '=', 'Riset: Approval Direktur']], { x_name: 'Riset: Approval Direktur', x_sequence: 100, x_company_id: CID, x_active: true, x_type: 'riset', x_override: true, x_condition: 'amount', x_min_amount: 0, x_max_amount: 0, x_approver_type: 'user', x_user_id: shella, x_label: 'Approval Direktur', x_note: 'Semua pengajuan dana riset disetujui Direktur.' });
    await foc(R, [['x_name', '=', 'Riset: Mengetahui Finance']], { x_name: 'Riset: Mengetahui Finance', x_sequence: 110, x_company_id: CID, x_active: true, x_type: 'riset', x_override: true, x_condition: 'amount', x_min_amount: 0, x_max_amount: 0, x_approver_type: 'user', x_user_id: dewi, x_label: 'Mengetahui (Finance)', x_note: 'Finance mengetahui sebelum dana ditransfer. Transfer dilakukan Finance setelah tahap ini.' });
    // projects + analytic + project budgets
    const P = [
      ['R&D - SS Glow Serum Gen 2', 35000000, 'Niacinamide 10% + Ceramide. Target launching Feb 2027.'],
      ['R&D - SS Lip Cream 4 Shade Baru', 15000000, 'Pengembangan 4 shade baru, maklon PT Maklon Kosmetik Nusantara.'],
      ['R&D - SS Sunscreen SPF 50 PA++++', 20000000, 'Formulasi & uji SPF di lab eksternal.'],
    ];
    const PRJ = {};
    for (const [name, amt, note] of P) {
      const an = await foc('account.analytic.account', [['name', '=', name], ['company_id', '=', CID]], { name, plan_id: 1, company_id: CID });
      const pr = await foc('project.project', [['name', '=', name], ['company_id', '=', CID]], { name, company_id: CID, account_id: an, user_id: yuni, color: 10, description: note });
      const pb = await foc('x_ss_project_budget', [['x_name', '=', name]], { x_name: name, x_company_id: CID, x_project_id: pr, x_analytic_id: an, x_pic_id: yuni, x_date_from: '2026-09-01', x_date_to: '2027-02-28', x_amount: amt, x_state: 'aktif', x_note: note });
      PRJ[name] = { an, pr, pb };
    }
    console.log('projects', PRJ);
    require('fs').writeFileSync('rd_ids.json', JSON.stringify({ yuni, PRJ }, null, 1));
  }
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-6).join(String.fromCharCode(10))); process.exit(1); });
