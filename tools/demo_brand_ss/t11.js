// Demo users per jabatan + Pengajuan & Approval module (manual models + server actions). Idempotent.
const { login, kw, CID } = require('./rpc');
const ids = require('./ids.json');
const DEMO_PW = process.env.DEMO_PW;
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function gid(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
async function xid(module, name, model, res_id) { const e = await kw('ir.model.data', 'search', [[['module', '=', module], ['name', '=', name]]]); if (!e.length) await kw('ir.model.data', 'create', [{ module, name, model, res_id, noupdate: true }]); }

(async () => {
  await login();
  // ---------- groups ----------
  const gDemo = (await kw('res.groups', 'search', [[['name', '=', 'Brand SS Demo']]]))[0];
  const gApvUser = await foc('res.groups', [['name', '=', 'SS Approval / Pengguna']], { name: 'SS Approval / Pengguna' });
  const gApvMgr = await foc('res.groups', [['name', '=', 'SS Approval / Manager']], { name: 'SS Approval / Manager', implied_ids: [[4, gApvUser]] });
  await xid('ss_demo', 'group_approval_user', 'res.groups', gApvUser);
  await xid('ss_demo', 'group_approval_manager', 'res.groups', gApvMgr);
  await kw('res.users', 'write', [[2, 265], { groups_id: [[4, gApvMgr], [4, gDemo]] }]);

  // ---------- demo users ----------
  const G = {};
  for (const x of ['base.group_user', 'sales_team.group_sale_salesman_all_leads', 'sales_team.group_sale_manager', 'purchase.group_purchase_user', 'purchase.group_purchase_manager', 'stock.group_stock_user', 'stock.group_stock_manager', 'mrp.group_mrp_user', 'mrp.group_mrp_manager', 'account.group_account_invoice', 'account.group_account_manager', 'hr.group_hr_user', 'hr.group_hr_manager', 'project.group_project_user', 'project.group_project_manager', 'point_of_sale.group_pos_user', 'point_of_sale.group_pos_manager', 'analytic.group_analytic_accounting', 'hr_attendance.group_hr_attendance_manager'])
    G[x] = await gid(x).catch(() => null);
  const USERS = [
    ['ss.shella', 'Shella Saukia', 'Shella Saukia', ['sales_team.group_sale_manager', 'purchase.group_purchase_manager', 'stock.group_stock_manager', 'mrp.group_mrp_manager', 'account.group_account_manager', 'hr.group_hr_manager', 'project.group_project_manager', 'point_of_sale.group_pos_manager', 'analytic.group_analytic_accounting', 'hr_attendance.group_hr_attendance_manager'], [gApvMgr, gDemo]],
    ['ss.dewi', 'Dewi Anggraini', 'Dewi Anggraini', ['account.group_account_manager', 'purchase.group_purchase_user', 'sales_team.group_sale_salesman_all_leads', 'project.group_project_user', 'analytic.group_analytic_accounting', 'stock.group_stock_user'], [gApvMgr]],
    ['ss.reza', 'Reza Firmansyah', 'Reza Firmansyah', ['sales_team.group_sale_salesman_all_leads', 'project.group_project_user'], [gApvUser]],
    ['ss.budi', 'Budi Santoso', 'Budi Santoso', ['purchase.group_purchase_user', 'stock.group_stock_user', 'project.group_project_user'], [gApvUser]],
    ['ss.joko', 'Joko Susilo', 'Joko Susilo', ['stock.group_stock_user', 'mrp.group_mrp_user', 'project.group_project_user'], [gApvUser]],
    ['ss.maya', 'Maya Puspita', 'Maya Puspita', ['sales_team.group_sale_manager', 'stock.group_stock_user', 'project.group_project_user'], [gApvUser, gDemo]],
    ['ss.eko', 'Eko Kurniawan', 'Eko Kurniawan', ['point_of_sale.group_pos_user', 'stock.group_stock_user', 'sales_team.group_sale_salesman_all_leads'], [gApvUser]],
  ];
  const U = {};
  for (const [loginName, name, empName, groups, extra] of USERS) {
    let u = (await kw('res.users', 'search', [[['login', '=', loginName]]], { context: { active_test: false } }))[0];
    const gids = [G['base.group_user'], ...groups.map(g => G[g]).filter(Boolean), ...extra];
    if (!u) u = await kw('res.users', 'create', [{ name, login: loginName, company_id: CID, company_ids: [[6, 0, [CID]]], groups_id: [[6, 0, gids]], tz: 'Asia/Jakarta', lang: 'en_US' }], { context: { no_reset_password: true } });
    else await kw('res.users', 'write', [[u], { groups_id: gids.map(g => [4, g]) }]);
    if (DEMO_PW) await kw('res.users', 'write', [[u], { password: DEMO_PW }]);
    const emp = (await kw('hr.employee', 'search', [[['name', '=', empName], ['company_id', '=', CID]]]))[0];
    if (emp) {
      // unlink any auto-created duplicate employee for this user
      const dup = await kw('hr.employee', 'search', [[['user_id', '=', u], ['id', '!=', emp]]]);
      if (dup.length) await kw('hr.employee', 'write', [dup, { user_id: false, active: false }]);
      await kw('hr.employee', 'write', [[emp], { user_id: u }]);
    }
    U[loginName] = u;
  }
  console.log('users', U);

  // ---------- sequence ----------
  await foc('ir.sequence', [['code', '=', 'x.ss.approval']], { name: 'SS Pengajuan', code: 'x.ss.approval', prefix: 'APV/%(year)s/', padding: 4, company_id: CID });

  // ---------- models ----------
  async function model(m, name, mail) {
    let id = (await kw('ir.model', 'search', [[['model', '=', m]]]))[0];
    if (!id) id = await kw('ir.model', 'create', [{ name, model: m, state: 'manual', is_mail_thread: !!mail, is_mail_activity: !!mail }]);
    return id;
  }
  async function field(mid, vals) {
    const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]);
    if (ex.length) return ex[0];
    return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]);
  }
  const sel = arr => arr.map(([v, n], i) => [0, 0, { value: v, name: n, sequence: i + 1 }]);
  const M = await model('x_ss_approval', 'Pengajuan & Approval', true);
  const ML = await model('x_ss_approval_line', 'Rincian Pengajuan', false);
  const F = [
    { name: 'x_number', field_description: 'Nomor', ttype: 'char', readonly: true, copied: false },
    { name: 'x_type', field_description: 'Jenis Pengajuan', ttype: 'selection', required: true, tracking: 1, selection_ids: sel([['pembelian', 'Pembelian Barang'], ['pembayaran', 'Pembayaran Supplier/Vendor'], ['campaign', 'Campaign / Iklan / KOL'], ['produksi', 'Permintaan Produksi'], ['event', 'Event & Partnership'], ['kantor', 'Kebutuhan Operasional Kantor']]) },
    { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company', required: true, on_delete: 'cascade' },
    { name: 'x_requester_id', field_description: 'Diajukan oleh (PIC)', ttype: 'many2one', relation: 'res.users', required: true, tracking: 1, on_delete: 'restrict' },
    { name: 'x_department_id', field_description: 'Divisi', ttype: 'many2one', relation: 'hr.department' },
    { name: 'x_analytic_id', field_description: 'Pos Anggaran (Analytic)', ttype: 'many2one', relation: 'account.analytic.account' },
    { name: 'x_partner_id', field_description: 'Supplier / Vendor / Partner', ttype: 'many2one', relation: 'res.partner' },
    { name: 'x_amount', field_description: 'Nominal (Rp)', ttype: 'float', tracking: 1 },
    { name: 'x_deadline', field_description: 'Dibutuhkan Tanggal', ttype: 'date', tracking: 1 },
    { name: 'x_reason', field_description: 'Alasan / Keterangan', ttype: 'text' },
    { name: 'x_state', field_description: 'Status', ttype: 'selection', tracking: 1, selection_ids: sel([['draft', 'Draft'], ['submitted', 'Menunggu Approval'], ['approved', 'Disetujui'], ['rejected', 'Ditolak'], ['done', 'Selesai Diproses']]) },
    { name: 'x_approver_id', field_description: 'Approver Saat Ini', ttype: 'many2one', relation: 'res.users', tracking: 1, readonly: true },
    { name: 'x_chain', field_description: 'Rantai Approval (teknis)', ttype: 'char', readonly: true, copied: false },
    { name: 'x_approval_path', field_description: 'Alur Approval', ttype: 'char', readonly: true, copied: false },
    { name: 'x_step', field_description: 'Tahap', ttype: 'integer', readonly: true, copied: false },
    { name: 'x_has_budget', field_description: 'Ada Budget', ttype: 'boolean', readonly: true, copied: false },
    { name: 'x_budget_remaining', field_description: 'Sisa Budget Bulan Ini (Rp)', ttype: 'float', readonly: true, copied: false },
    { name: 'x_over_budget', field_description: 'Melebihi Anggaran', ttype: 'boolean', readonly: true, copied: false, tracking: 1 },
    { name: 'x_submitted_date', field_description: 'Tanggal Diajukan', ttype: 'datetime', readonly: true, copied: false },
    { name: 'x_approved_date', field_description: 'Tanggal Disetujui', ttype: 'datetime', readonly: true, copied: false },
    { name: 'x_reject_reason', field_description: 'Alasan Ditolak / Revisi', ttype: 'text', copied: false },
    { name: 'x_purchase_id', field_description: 'Purchase Order', ttype: 'many2one', relation: 'purchase.order', readonly: true, copied: false },
    { name: 'x_bill_id', field_description: 'Tagihan Vendor terkait', ttype: 'many2one', relation: 'account.move' },
    { name: 'x_attachment_ids', field_description: 'Lampiran (penawaran, invoice, brief)', ttype: 'many2many', relation: 'ir.attachment', relation_table: 'x_ss_approval_attachment_rel', column1: 'approval_id', column2: 'attachment_id' },
  ];
  for (const f of F) await field(M, f);
  for (const f of [
    { name: 'x_approval_id', field_description: 'Pengajuan', ttype: 'many2one', relation: 'x_ss_approval', required: true, on_delete: 'cascade' },
    { name: 'x_product_id', field_description: 'Produk / Bahan', ttype: 'many2one', relation: 'product.product', required: true, on_delete: 'restrict' },
    { name: 'x_qty', field_description: 'Qty', ttype: 'float' },
    { name: 'x_price', field_description: 'Estimasi Harga Satuan', ttype: 'float' },
    { name: 'x_subtotal', field_description: 'Subtotal', ttype: 'float', store: true, readonly: true, depends: 'x_qty,x_price', compute: "for rec in self:\n    rec['x_subtotal'] = (rec.x_qty or 0.0) * (rec.x_price or 0.0)" },
  ]) await field(ML, f);
  await field(M, { name: 'x_line_ids', field_description: 'Rincian Barang', ttype: 'one2many', relation: 'x_ss_approval_line', relation_field: 'x_approval_id' });

  // access & rules
  for (const [m, g, w, c, u] of [[M, gApvUser, true, true, false], [M, gApvMgr, true, true, true], [ML, gApvUser, true, true, true]])
    await foc('ir.model.access', [['model_id', '=', m], ['group_id', '=', g]], { name: 'access ' + m + ' ' + g, model_id: m, group_id: g, perm_read: true, perm_write: w, perm_create: c, perm_unlink: u });
  await foc('ir.rule', [['model_id', '=', M], ['name', '=', 'Approval multi-company']], { name: 'Approval multi-company', model_id: M, domain_force: "[('x_company_id', 'in', company_ids)]" });

  // ---------- server actions ----------
  const LABELS = "labels = {'atasan': 'Atasan', 'finance': 'Finance Manager', 'direksi': 'Direksi'}\n";
  const CODE = {
    submit: LABELS + `for rec in records:
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
    Users = env['res.users'].sudo()
    fin = Users.search([('login', '=', 'ss.dewi')], limit=1)
    direksi = Users.search([('login', '=', 'ss.shella')], limit=1)
    emp = env['hr.employee'].sudo().search([('user_id', '=', rec.x_requester_id.id)], limit=1)
    boss = emp.parent_id.user_id
    steps = []
    if boss:
        steps.append(('atasan', boss))
    if amount >= 10000000 or over or not boss:
        steps.append(('finance', fin))
    if amount > 50000000 or over:
        steps.append(('direksi', direksi))
    chain = []
    for lvl, u in steps:
        if not u or u == rec.x_requester_id:
            continue
        chain = [c for c in chain if c[1] != u.id]
        chain.append((lvl, u.id))
    if not chain:
        chain = [('direksi', direksi.id)]
    path = ' → '.join('%s (%s)' % (labels[c[0]], Users.browse(c[1]).name) for c in chain)
    vals = {'x_state': 'submitted', 'x_amount': amount, 'x_budget_remaining': remaining, 'x_has_budget': has_budget, 'x_over_budget': over, 'x_chain': ','.join('%s:%s' % c for c in chain), 'x_approval_path': path, 'x_step': 0, 'x_approver_id': chain[0][1], 'x_submitted_date': datetime.datetime.now(), 'x_reject_reason': False}
    if not rec.x_number:
        vals['x_number'] = env['ir.sequence'].sudo().next_by_code('x.ss.approval') or '/'
    rec.write(vals)
    note = 'Diajukan Rp {:,.0f}. Alur approval: {}.'.format(amount, path)
    if over:
        note += ' ⚠️ MELEBIHI ANGGARAN: sisa budget Rp {:,.0f} → wajib approval Direksi.'.format(remaining)
    rec.message_post(body=note)
    rec.activity_schedule('mail.mail_activity_data_todo', user_id=chain[0][1], summary='Approval %s: %s' % (labels[chain[0][0]], rec.x_number), note='Mohon review pengajuan %s senilai Rp {:,.0f}'.format(amount) % rec.x_name)
`,
    approve: LABELS + `for rec in records:
    if rec.x_state != 'submitted':
        raise UserError('Pengajuan ini tidak sedang menunggu approval.')
    if env.user != rec.x_approver_id and not env.user.has_group('base.group_system'):
        raise UserError('Tahap ini hanya bisa disetujui oleh %s.' % rec.x_approver_id.name)
    rec.activity_ids.filtered(lambda a: a.user_id == rec.x_approver_id).action_feedback(feedback='Disetujui')
    parts = [p.split(':') for p in (rec.x_chain or '').split(',') if p]
    lvl = parts[rec.x_step][0] if rec.x_step < len(parts) else 'direksi'
    rec.message_post(body='✅ Disetujui oleh %s sebagai %s.' % (env.user.name, labels.get(lvl, lvl)))
    nxt = rec.x_step + 1
    if nxt < len(parts):
        uid2 = int(parts[nxt][1])
        rec.write({'x_step': nxt, 'x_approver_id': uid2})
        rec.activity_schedule('mail.mail_activity_data_todo', user_id=uid2, summary='Approval %s: %s' % (labels[parts[nxt][0]], rec.x_number), note='Pengajuan %s senilai Rp {:,.0f} sudah disetujui tahap sebelumnya.'.format(rec.x_amount) % rec.x_name)
    else:
        rec.write({'x_state': 'approved', 'x_approver_id': False, 'x_step': nxt, 'x_approved_date': datetime.datetime.now()})
        rec.message_post(body='🎉 Pengajuan DISETUJUI penuh. Silakan lanjutkan proses.')
        rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.x_requester_id.id, summary='Disetujui: lanjutkan %s' % rec.x_number, note='Pengajuan sudah disetujui seluruh approver.')
`,
    reject: `for rec in records:
    if rec.x_state != 'submitted':
        raise UserError('Pengajuan ini tidak sedang menunggu approval.')
    if env.user != rec.x_approver_id and not env.user.has_group('base.group_system'):
        raise UserError('Hanya %s yang dapat menolak pada tahap ini.' % rec.x_approver_id.name)
    if not rec.x_reject_reason:
        raise UserError('Isi kolom "Alasan Ditolak / Revisi" terlebih dahulu.')
    rec.activity_ids.unlink()
    rec.write({'x_state': 'rejected', 'x_approver_id': False})
    rec.message_post(body='❌ Ditolak oleh %s. Alasan: %s' % (env.user.name, rec.x_reject_reason))
    rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.x_requester_id.id, summary='Ditolak: %s' % rec.x_number, note=rec.x_reject_reason)
`,
    revise: `for rec in records:
    if rec.x_state != 'submitted':
        raise UserError('Pengajuan ini tidak sedang menunggu approval.')
    if env.user != rec.x_approver_id and not env.user.has_group('base.group_system'):
        raise UserError('Hanya %s yang dapat mengembalikan pada tahap ini.' % rec.x_approver_id.name)
    if not rec.x_reject_reason:
        raise UserError('Isi kolom "Alasan Ditolak / Revisi" terlebih dahulu.')
    rec.activity_ids.unlink()
    rec.write({'x_state': 'draft', 'x_approver_id': False, 'x_step': 0})
    rec.message_post(body='↩️ Dikembalikan untuk revisi oleh %s: %s' % (env.user.name, rec.x_reject_reason))
    rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.x_requester_id.id, summary='Revisi: %s' % rec.x_number, note=rec.x_reject_reason)
`,
    make_po: `po = False
for rec in records:
    if rec.x_type != 'pembelian' or rec.x_state != 'approved':
        raise UserError('PO hanya bisa dibuat dari pengajuan pembelian yang sudah disetujui.')
    if not rec.x_partner_id:
        raise UserError('Isi Supplier terlebih dahulu.')
    if not rec.x_line_ids:
        raise UserError('Isi rincian barang terlebih dahulu.')
    po = env['purchase.order'].create({'partner_id': rec.x_partner_id.id, 'company_id': rec.x_company_id.id, 'origin': rec.x_number, 'order_line': [(0, 0, {'product_id': l.x_product_id.id, 'product_qty': l.x_qty, 'price_unit': l.x_price}) for l in rec.x_line_ids]})
    po.sudo().button_confirm()
    if po.state == 'to approve':
        po.sudo().button_approve()
    rec.write({'x_purchase_id': po.id, 'x_state': 'done'})
    rec.message_post(body='🧾 Purchase Order %s dibuat & dikonfirmasi otomatis (sudah melalui approval).' % po.name)
if po:
    action = {'type': 'ir.actions.act_window', 'res_model': 'purchase.order', 'res_id': po.id, 'views': [[False, 'form']], 'target': 'current'}
`,
    done: `for rec in records:
    if rec.x_state != 'approved':
        raise UserError('Hanya pengajuan yang sudah disetujui yang bisa ditandai selesai.')
    rec.write({'x_state': 'done'})
    rec.message_post(body='✔️ Ditandai selesai diproses oleh %s.' % env.user.name)
`,
  };
  const SA = {};
  for (const [k, code] of Object.entries(CODE)) {
    const name = 'SS Approval: ' + k;
    const ex = await kw('ir.actions.server', 'search', [[['name', '=', name]]]);
    if (ex.length) { await kw('ir.actions.server', 'write', [ex, { code }]); SA[k] = ex[0]; }
    else SA[k] = await kw('ir.actions.server', 'create', [{ name, model_id: M, state: 'code', code }]);
  }

  // ---------- views ----------
  async function view(name, type, arch, model = 'x_ss_approval') {
    const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]);
    if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; }
    return kw('ir.ui.view', 'create', [{ name, type, model, arch_db: arch }]);
  }
  await view('x_ss_approval_line.list', 'list', `<list editable="bottom"><field name="x_product_id"/><field name="x_qty"/><field name="x_price"/><field name="x_subtotal" sum="Total"/></list>`, 'x_ss_approval_line');
  await view('x_ss_approval.form', 'form', `<form>
  <header>
    <button name="${SA.submit}" type="action" string="Ajukan" class="btn-primary" invisible="x_state != 'draft'"/>
    <button name="${SA.approve}" type="action" string="Setujui" class="btn-success" invisible="x_state != 'submitted'"/>
    <button name="${SA.revise}" type="action" string="Kembalikan untuk Revisi" invisible="x_state != 'submitted'"/>
    <button name="${SA.reject}" type="action" string="Tolak" class="btn-danger" invisible="x_state != 'submitted'"/>
    <button name="${SA.make_po}" type="action" string="Buat Purchase Order" class="btn-primary" invisible="x_state != 'approved' or x_type != 'pembelian'"/>
    <button name="${SA.done}" type="action" string="Tandai Selesai" invisible="x_state != 'approved' or x_type == 'pembelian'"/>
    <field name="x_state" widget="statusbar" statusbar_visible="draft,submitted,approved,done"/>
  </header>
  <sheet>
    <div class="alert alert-danger" role="alert" invisible="not x_over_budget"><b>Melebihi anggaran.</b> Nominal pengajuan lebih besar dari sisa budget divisi bulan ini, jadi wajib approval Direksi.</div>
    <div class="alert alert-info" role="alert" invisible="x_state != 'submitted'">Menunggu approval: <field name="x_approver_id" readonly="1" class="fw-bold"/> · Alur: <field name="x_approval_path" readonly="1"/></div>
    <div class="oe_title">
      <div class="text-muted"><field name="x_number" readonly="1" placeholder="Nomor otomatis saat diajukan"/></div>
      <h1><field name="x_name" placeholder="cth: Restock kain wolfis untuk produksi Desember" readonly="x_state not in ('draft',)"/></h1>
    </div>
    <group>
      <group string="Pengajuan">
        <field name="x_type" readonly="x_state != 'draft'"/>
        <field name="x_requester_id" readonly="x_state != 'draft'" widget="many2one_avatar_user"/>
        <field name="x_department_id" readonly="x_state != 'draft'"/>
        <field name="x_partner_id" readonly="x_state != 'draft'"/>
        <field name="x_deadline" readonly="x_state != 'draft'"/>
        <field name="x_company_id" invisible="1"/>
      </group>
      <group string="Nominal &amp; Anggaran">
        <field name="x_amount" readonly="x_state != 'draft'" help="Untuk pembelian, nominal otomatis dihitung dari rincian barang saat diajukan."/>
        <field name="x_analytic_id" readonly="x_state != 'draft'"/>
        <field name="x_budget_remaining" invisible="not x_has_budget"/>
        <field name="x_over_budget" invisible="not x_has_budget"/>
        <field name="x_has_budget" invisible="1"/>
        <field name="x_approval_path" invisible="not x_approval_path"/>
        <field name="x_submitted_date" invisible="not x_submitted_date"/>
        <field name="x_approved_date" invisible="not x_approved_date"/>
        <field name="x_purchase_id" invisible="not x_purchase_id"/>
        <field name="x_bill_id" invisible="x_type != 'pembayaran'"/>
      </group>
    </group>
    <notebook>
      <page string="Rincian Barang" invisible="x_type not in ('pembelian', 'produksi')">
        <field name="x_line_ids" readonly="x_state != 'draft'"/>
      </page>
      <page string="Keterangan">
        <field name="x_reason" placeholder="Jelaskan kebutuhan, alasan, dan dampaknya…" readonly="x_state != 'draft'"/>
        <field name="x_attachment_ids" widget="many2many_binary" string="Lampiran"/>
      </page>
      <page string="Penolakan / Revisi">
        <field name="x_reject_reason" placeholder="Wajib diisi approver sebelum menolak / mengembalikan"/>
      </page>
    </notebook>
  </sheet>
  <chatter/>
</form>`);
  await view('x_ss_approval.list', 'list', `<list decoration-muted="x_state in ('done','rejected')" decoration-danger="x_over_budget and x_state == 'submitted'" default_order="x_submitted_date desc">
  <field name="x_number"/><field name="x_name"/><field name="x_type"/><field name="x_requester_id" widget="many2one_avatar_user"/>
  <field name="x_department_id" optional="show"/><field name="x_amount" sum="Total"/><field name="x_deadline" optional="show"/>
  <field name="x_approver_id" widget="many2one_avatar_user"/><field name="x_over_budget" optional="show"/>
  <field name="x_state" widget="badge" decoration-info="x_state == 'submitted'" decoration-success="x_state in ('approved','done')" decoration-danger="x_state == 'rejected'"/>
</list>`);
  await view('x_ss_approval.kanban', 'kanban', `<kanban default_group_by="x_state" quick_create="false">
  <field name="x_state"/><field name="x_over_budget"/>
  <templates><t t-name="card">
    <div class="d-flex justify-content-between"><field name="x_number" class="text-muted small"/><field name="x_type" class="badge text-bg-light"/></div>
    <field name="x_name" class="fw-bold"/>
    <div class="d-flex justify-content-between align-items-center mt-1">
      <span>Rp <field name="x_amount" widget="integer"/></span>
      <field name="x_requester_id" widget="many2one_avatar_user"/>
    </div>
    <div t-if="record.x_over_budget.raw_value" class="text-danger small">⚠ Melebihi anggaran</div>
    <div class="small text-muted" t-if="record.x_state.raw_value == 'submitted'">Menunggu: <field name="x_approver_id"/></div>
  </t></templates>
</kanban>`);
  await view('x_ss_approval.search', 'search', `<search>
  <field name="x_name"/><field name="x_number"/><field name="x_requester_id"/><field name="x_approver_id"/>
  <filter name="my_approval" string="Menunggu Approval Saya" domain="[('x_approver_id','=',uid),('x_state','=','submitted')]"/>
  <filter name="mine" string="Pengajuan Saya" domain="[('x_requester_id','=',uid)]"/>
  <separator/>
  <filter name="waiting" string="Menunggu Approval" domain="[('x_state','=','submitted')]"/>
  <filter name="over" string="Melebihi Anggaran" domain="[('x_over_budget','=',True)]"/>
  <group expand="0"><filter name="g_type" string="Jenis" context="{'group_by':'x_type'}"/><filter name="g_dept" string="Divisi" context="{'group_by':'x_department_id'}"/><filter name="g_state" string="Status" context="{'group_by':'x_state'}"/></group>
</search>`);

  // ---------- actions & menus ----------
  async function act(name, domain, ctx) {
    const ex = await kw('ir.actions.act_window', 'search', [[['name', '=', name], ['res_model', '=', 'x_ss_approval']]]);
    const vals = { name, res_model: 'x_ss_approval', view_mode: 'kanban,list,form', domain, context: ctx, help: '<p class="o_view_nocontent_smiling_face">Buat pengajuan pertama</p><p>Setiap pengajuan punya PIC, nominal, deadline, alur approval berjenjang, dan riwayat aktivitas.</p>' };
    if (ex.length) { await kw('ir.actions.act_window', 'write', [ex, vals]); return ex[0]; }
    return kw('ir.actions.act_window', 'create', [vals]);
  }
  const baseCtx = "'default_x_requester_id': uid, 'default_x_company_id': allowed_company_ids[0], 'default_x_state': 'draft'";
  const aMine = await act('Pengajuan Saya', "[('x_requester_id','=',uid)]", `{${baseCtx}}`);
  const aWait = await act('Menunggu Approval Saya', "[('x_approver_id','=',uid),('x_state','=','submitted')]", `{${baseCtx}}`);
  const aAll = await act('Semua Pengajuan', '[]', `{${baseCtx}, 'search_default_waiting': 0}`);
  const root = await foc('ir.ui.menu', [['name', '=', 'Pengajuan & Approval'], ['parent_id', '=', false]], { name: 'Pengajuan & Approval', sequence: 2, web_icon: 'hr_expense,static/description/icon.png', groups_id: [[6, 0, [gApvUser]]] });
  await foc('ir.ui.menu', [['name', '=', 'Pengajuan Saya'], ['parent_id', '=', root]], { name: 'Pengajuan Saya', parent_id: root, action: 'ir.actions.act_window,' + aMine, sequence: 1 });
  await foc('ir.ui.menu', [['name', '=', 'Menunggu Approval Saya'], ['parent_id', '=', root]], { name: 'Menunggu Approval Saya', parent_id: root, action: 'ir.actions.act_window,' + aWait, sequence: 2 });
  await foc('ir.ui.menu', [['name', '=', 'Semua Pengajuan'], ['parent_id', '=', root]], { name: 'Semua Pengajuan', parent_id: root, action: 'ir.actions.act_window,' + aAll, sequence: 3, groups_id: [[6, 0, [gApvMgr]]] });
  require('fs').writeFileSync('approval_ids.json', JSON.stringify({ SA, U, M }, null, 1));
  console.log('approval module ready', SA);
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-2500)); process.exit(1); });
