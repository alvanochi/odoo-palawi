// Configurable approval rules (x_ss_approval_rule) + rule-driven submit/approve server actions. Run after t11.js.
const { login, kw, CID } = require('./rpc');
const { SA } = require('./approval_ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
const sel = arr => arr.map(([v, n], i) => [0, 0, { value: v, name: n, sequence: i + 1 }]);

(async () => {
  await login();
  const gUser = (await kw('res.groups', 'search', [[['name', '=', 'SS Approval / Pengguna']]]))[0];
  const gMgr = (await kw('res.groups', 'search', [[['name', '=', 'SS Approval / Manager']]]))[0];

  // ---------- model ----------
  const R = 'x_ss_approval_rule';
  let M = (await kw('ir.model', 'search', [[['model', '=', R]]]))[0];
  if (!M) M = await kw('ir.model', 'create', [{ name: 'Aturan Approval', model: R, state: 'manual', is_mail_thread: true }]);
  async function field(vals) {
    const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', M], ['name', '=', vals.name]]]);
    if (ex.length) return ex[0];
    return kw('ir.model.fields', 'create', [Object.assign({ model_id: M, state: 'manual' }, vals)]);
  }
  const F = [
    { name: 'x_active', field_description: 'Aktif', ttype: 'boolean', tracking: 1 },
    { name: 'x_sequence', field_description: 'Urutan', ttype: 'integer' },
    { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company', required: true, on_delete: 'cascade' },
    { name: 'x_type', field_description: 'Berlaku untuk Jenis', ttype: 'selection', required: true, tracking: 1, selection_ids: sel([['all', 'Semua jenis'], ['pembelian', 'Pembelian Barang'], ['pembayaran', 'Pembayaran Supplier/Vendor'], ['campaign', 'Campaign / Iklan / KOL'], ['produksi', 'Permintaan Produksi'], ['event', 'Event & Partnership'], ['kantor', 'Kebutuhan Operasional Kantor']]) },
    { name: 'x_department_id', field_description: 'Hanya untuk Divisi', ttype: 'many2one', relation: 'hr.department', help: 'Kosongkan agar berlaku untuk semua divisi.' },
    { name: 'x_condition', field_description: 'Kondisi', ttype: 'selection', required: true, tracking: 1, selection_ids: sel([['amount', 'Berdasarkan nominal'], ['over_budget', 'Jika melebihi anggaran']]) },
    { name: 'x_min_amount', field_description: 'Nominal Minimal (Rp)', ttype: 'float', tracking: 1 },
    { name: 'x_max_amount', field_description: 'Nominal Maksimal (Rp)', ttype: 'float', tracking: 1, help: '0 = tanpa batas atas.' },
    { name: 'x_approver_type', field_description: 'Approver', ttype: 'selection', required: true, tracking: 1, selection_ids: sel([['manager', 'Atasan langsung pengaju'], ['dept_manager', 'Manager divisi pengajuan'], ['user', 'User tertentu']]) },
    { name: 'x_user_id', field_description: 'User Approver', ttype: 'many2one', relation: 'res.users', tracking: 1 },
    { name: 'x_fallback_user_id', field_description: 'Cadangan jika atasan/manager tidak ada', ttype: 'many2one', relation: 'res.users' },
    { name: 'x_label', field_description: 'Nama Tahap', ttype: 'char', required: true, help: 'Tampil di alur approval, mis. "Finance Manager".' },
    { name: 'x_note', field_description: 'Catatan', ttype: 'text' },
  ];
  for (const f of F) await field(f);
  for (const [g, w] of [[gUser, false], [gMgr, true]])
    await foc('ir.model.access', [['model_id', '=', M], ['group_id', '=', g]], { name: 'access x_ss_approval_rule ' + g, model_id: M, group_id: g, perm_read: true, perm_write: w, perm_create: w, perm_unlink: w });
  await foc('ir.rule', [['model_id', '=', M], ['name', '=', 'Approval rule multi-company']], { name: 'Approval rule multi-company', model_id: M, domain_force: "[('x_company_id', 'in', company_ids)]" });

  // ---------- views ----------
  async function view(name, type, arch) {
    const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]);
    if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; }
    return kw('ir.ui.view', 'create', [{ name, type, model: R, arch_db: arch }]);
  }
  await view('x_ss_approval_rule.list', 'list', `<list default_order="x_sequence" decoration-muted="not x_active">
  <field name="x_sequence" widget="handle"/>
  <field name="x_name"/><field name="x_type"/><field name="x_department_id" optional="show"/>
  <field name="x_condition"/><field name="x_min_amount"/><field name="x_max_amount"/>
  <field name="x_approver_type"/><field name="x_user_id" widget="many2one_avatar_user"/><field name="x_label"/>
  <field name="x_active" widget="boolean_toggle"/>
</list>`);
  await view('x_ss_approval_rule.form', 'form', `<form>
  <sheet>
    <div class="oe_title"><h1><field name="x_name" placeholder="cth: Finance untuk pengajuan ≥ Rp10 juta"/></h1></div>
    <group>
      <group string="Kapan aturan ini berlaku">
        <field name="x_type"/><field name="x_department_id"/><field name="x_condition"/>
        <field name="x_min_amount" invisible="x_condition != 'amount'"/>
        <field name="x_max_amount" invisible="x_condition != 'amount'"/>
      </group>
      <group string="Siapa yang menyetujui">
        <field name="x_approver_type"/>
        <field name="x_user_id" invisible="x_approver_type != 'user'" required="x_approver_type == 'user'"/>
        <field name="x_fallback_user_id" invisible="x_approver_type == 'user'"/>
        <field name="x_label"/><field name="x_sequence"/><field name="x_active"/>
        <field name="x_company_id" invisible="1"/>
      </group>
    </group>
    <div class="alert alert-info" role="alert">Semua aturan aktif yang cocok dengan jenis, divisi, dan nominal pengajuan dipakai berurutan sesuai <b>Urutan</b>. Approver yang sama hanya menyetujui sekali (di tahap tertinggi), dan pengaju tidak pernah menyetujui pengajuannya sendiri.</div>
    <field name="x_note" placeholder="Catatan / dasar kebijakan"/>
  </sheet>
  <chatter/>
</form>`);
  await view('x_ss_approval_rule.search', 'search', `<search><field name="x_name"/><field name="x_user_id"/>
  <filter name="active" string="Aktif" domain="[('x_active','=',True)]"/><filter name="inactive" string="Nonaktif" domain="[('x_active','=',False)]"/>
  <group expand="0"><filter name="g_type" string="Jenis" context="{'group_by':'x_type'}"/></group></search>`);
  let act = (await kw('ir.actions.act_window', 'search', [[['res_model', '=', R]]]))[0];
  const actVals = { name: 'Aturan Approval', res_model: R, view_mode: 'list,form', context: "{'default_x_company_id': allowed_company_ids[0], 'default_x_active': True, 'default_x_type': 'all', 'default_x_condition': 'amount', 'default_x_approver_type': 'user', 'active_test': False}", help: '<p class="o_view_nocontent_smiling_face">Buat aturan approval pertama</p><p>Tentukan jenis pengajuan, batas nominal, dan siapa approvernya.</p>' };
  if (act) await kw('ir.actions.act_window', 'write', [[act], actVals]); else act = await kw('ir.actions.act_window', 'create', [actVals]);
  const root = (await kw('ir.ui.menu', 'search', [[['name', '=', 'Pengajuan & Approval'], ['parent_id', '=', false]]]))[0];
  const conf = await foc('ir.ui.menu', [['name', '=', 'Konfigurasi'], ['parent_id', '=', root]], { name: 'Konfigurasi', parent_id: root, sequence: 90, groups_id: [[6, 0, [gMgr]]] });
  await foc('ir.ui.menu', [['name', '=', 'Aturan Approval'], ['parent_id', '=', conf]], { name: 'Aturan Approval', parent_id: conf, action: 'ir.actions.act_window,' + act, sequence: 1 });

  // ---------- seed rules (current policy) ----------
  const U = Object.fromEntries((await kw('res.users', 'search_read', [[['login', 'in', ['ss.dewi', 'ss.shella']]]], { fields: ['login'] })).map(u => [u.login, u.id]));
  const RULES = [
    [10, 'Atasan langsung (semua pengajuan)', 'all', 'amount', 0, 0, 'manager', false, U['ss.dewi'], 'Atasan', 'Tahap pertama untuk semua pengajuan. Jika pengaju tidak punya atasan, dialihkan ke Finance.'],
    [15, 'Pembayaran selalu lewat Finance', 'pembayaran', 'amount', 0, 0, 'user', U['ss.dewi'], false, 'Finance Manager', 'Semua pembayaran ke supplier/vendor wajib diverifikasi Finance.'],
    [20, 'Finance untuk nominal ≥ Rp10 juta', 'all', 'amount', 10000000, 0, 'user', U['ss.dewi'], false, 'Finance Manager', ''],
    [30, 'Direksi untuk nominal > Rp50 juta', 'all', 'amount', 50000001, 0, 'user', U['ss.shella'], false, 'Direksi', ''],
    [40, 'Direksi jika melebihi anggaran divisi', 'all', 'over_budget', 0, 0, 'user', U['ss.shella'], false, 'Direksi', 'Berlaku berapa pun nominalnya bila sisa budget divisi bulan berjalan tidak cukup.'],
  ];
  for (const [seq, name, type, cond, mn, mx, at, user, fb, label, note] of RULES)
    await foc(R, [['x_name', '=', name]], { x_name: name, x_sequence: seq, x_company_id: CID, x_active: true, x_type: type, x_condition: cond, x_min_amount: mn, x_max_amount: mx, x_approver_type: at, x_user_id: user, x_fallback_user_id: fb, x_label: label, x_note: note });

  // ---------- rule-driven server actions ----------
  const SUBMIT = `for rec in records:
    if rec.x_state != 'draft':
        continue
    total = sum(l.x_qty * l.x_price for l in rec.x_line_ids)
    amount = total or rec.x_amount
    if amount <= 0:
        raise UserError('Isi nominal pengajuan atau rincian barang terlebih dahulu.')
    today = datetime.date.today()
    remaining = 0.0
    has_budget = False
    if rec.x_analytic_id:
        bls = env['crossovered.budget.lines'].sudo().search([('analytic_account_id', '=', rec.x_analytic_id.id), ('date_from', '<=', today), ('date_to', '>=', today), ('crossovered_budget_id.state', '=', 'validate')])
        if bls:
            has_budget = True
            remaining = sum(abs(b.planned_amount) - abs(b.practical_amount) for b in bls)
    over = has_budget and amount > remaining
    emp = env['hr.employee'].sudo().search([('user_id', '=', rec.x_requester_id.id)], limit=1)
    rules = env['x_ss_approval_rule'].sudo().search([('x_active', '=', True), ('x_company_id', '=', rec.x_company_id.id), ('x_type', 'in', ['all', rec.x_type])], order='x_sequence, id')
    chain = []
    for r in rules:
        if r.x_department_id and r.x_department_id != rec.x_department_id:
            continue
        if r.x_condition == 'over_budget':
            if not over:
                continue
        elif amount < r.x_min_amount or (r.x_max_amount and amount > r.x_max_amount):
            continue
        u = r.x_user_id
        if r.x_approver_type == 'manager':
            u = emp.parent_id.user_id or r.x_fallback_user_id
        elif r.x_approver_type == 'dept_manager':
            u = rec.x_department_id.manager_id.user_id or r.x_fallback_user_id
        if not u or u == rec.x_requester_id:
            continue
        chain = [c for c in chain if c[1] != u.id]
        chain.append((r.id, u.id))
    Users = env['res.users'].sudo()
    Rules = env['x_ss_approval_rule'].sudo()
    if not chain:
        rec.write({'x_state': 'approved', 'x_amount': amount, 'x_budget_remaining': remaining, 'x_has_budget': has_budget, 'x_over_budget': over, 'x_chain': '', 'x_approval_path': 'Disetujui otomatis (tidak ada approver di atas pengaju)', 'x_number': rec.x_number or env['ir.sequence'].sudo().next_by_code('x.ss.approval'), 'x_submitted_date': datetime.datetime.now(), 'x_approved_date': datetime.datetime.now()})
        rec.message_post(body='Disetujui otomatis: tidak ada aturan approval dengan approver selain pengaju.')
        continue
    path = ' → '.join('%s (%s)' % (Rules.browse(c[0]).x_label, Users.browse(c[1]).name) for c in chain)
    vals = {'x_state': 'submitted', 'x_amount': amount, 'x_budget_remaining': remaining, 'x_has_budget': has_budget, 'x_over_budget': over, 'x_chain': ','.join('r%s:%s' % c for c in chain), 'x_approval_path': path, 'x_step': 0, 'x_approver_id': chain[0][1], 'x_submitted_date': datetime.datetime.now(), 'x_reject_reason': False}
    if not rec.x_number:
        vals['x_number'] = env['ir.sequence'].sudo().next_by_code('x.ss.approval') or '/'
    rec.write(vals)
    note = 'Diajukan Rp {:,.0f}. Alur approval: {}.'.format(amount, path)
    if over:
        note += ' MELEBIHI ANGGARAN: sisa budget Rp {:,.0f}.'.format(remaining)
    rec.message_post(body=note)
    rec.activity_schedule('mail.mail_activity_data_todo', user_id=chain[0][1], summary='Approval %s: %s' % (Rules.browse(chain[0][0]).x_label, rec.x_number), note='Mohon review pengajuan %s senilai Rp {:,.0f}'.format(amount) % rec.x_name)
`;
  const APPROVE = `legacy = {'atasan': 'Atasan', 'finance': 'Finance Manager', 'direksi': 'Direksi'}
def label_of(key):
    if key.startswith('r') and key[1:].isdigit():
        return env['x_ss_approval_rule'].sudo().browse(int(key[1:])).x_label or 'Approver'
    return legacy.get(key, key)
for rec in records:
    if rec.x_state != 'submitted':
        raise UserError('Pengajuan ini tidak sedang menunggu approval.')
    if env.user != rec.x_approver_id and not env.user.has_group('base.group_system'):
        raise UserError('Tahap ini hanya bisa disetujui oleh %s.' % rec.x_approver_id.name)
    rec.activity_ids.filtered(lambda a: a.user_id == rec.x_approver_id).action_feedback(feedback='Disetujui')
    parts = [p.split(':') for p in (rec.x_chain or '').split(',') if p]
    key = parts[rec.x_step][0] if rec.x_step < len(parts) else 'direksi'
    rec.message_post(body='Disetujui oleh %s sebagai %s.' % (env.user.name, label_of(key)))
    nxt = rec.x_step + 1
    if nxt < len(parts):
        uid2 = int(parts[nxt][1])
        rec.write({'x_step': nxt, 'x_approver_id': uid2})
        rec.activity_schedule('mail.mail_activity_data_todo', user_id=uid2, summary='Approval %s: %s' % (label_of(parts[nxt][0]), rec.x_number), note='Pengajuan %s senilai Rp {:,.0f} sudah disetujui tahap sebelumnya.'.format(rec.x_amount) % rec.x_name)
    else:
        rec.write({'x_state': 'approved', 'x_approver_id': False, 'x_step': nxt, 'x_approved_date': datetime.datetime.now()})
        rec.message_post(body='Pengajuan DISETUJUI penuh. Silakan lanjutkan proses.')
        rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.x_requester_id.id, summary='Disetujui: lanjutkan %s' % rec.x_number, note='Pengajuan sudah disetujui seluruh approver.')
`;
  await kw('ir.actions.server', 'write', [[SA.submit], { code: SUBMIT }]);
  await kw('ir.actions.server', 'write', [[SA.approve], { code: APPROVE }]);
  console.log('rules ready; action', act);
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-6).join(String.fromCharCode(10))); process.exit(1); });
