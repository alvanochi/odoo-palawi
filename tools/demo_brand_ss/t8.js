// Live Streaming management (manual x_ model, Studio-style, no code deploy). Idempotent.
const { login, kw, CID } = require('./rpc');
const ids = require('./ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function xid(module, name, model, res_id) { const e = await kw('ir.model.data', 'search', [[['module', '=', module], ['name', '=', name]]]); if (!e.length) await kw('ir.model.data', 'create', [{ module, name, model, res_id, noupdate: true }]); }

(async () => {
  await login();
  // demo group
  const grp = await foc('res.groups', [['name', '=', 'Brand SS Demo']], { name: 'Brand SS Demo', users: [[6, 0, [2, 265]]] });
  await kw('res.groups', 'write', [[grp], { users: [[4, 2], [4, 265]] }]);
  await xid('ss_demo', 'group_brand_ss_demo', 'res.groups', grp);

  // model
  const M = 'x_ss_live_session';
  let model = (await kw('ir.model', 'search', [[['model', '=', M]]]))[0];
  if (!model) model = await kw('ir.model', 'create', [{ name: 'Sesi Live Streaming', model: M, state: 'manual', is_mail_thread: true, is_mail_activity: true }]);
  const somodel = (await kw('ir.model', 'search', [[['model', '=', 'sale.order']]]))[0];
  async function field(mid, vals) {
    const ex = await kw('ir.model.fields', 'search', [[['model_id', '=', mid], ['name', '=', vals.name]]]);
    if (ex.length) return ex[0];
    return kw('ir.model.fields', 'create', [Object.assign({ model_id: mid, state: 'manual' }, vals)]);
  }
  await field(somodel, { name: 'x_live_session_id', field_description: 'Sesi Live Streaming', ttype: 'many2one', relation: M, on_delete: 'set null', index: true });
  const F = [
    { name: 'x_company_id', field_description: 'Company', ttype: 'many2one', relation: 'res.company', required: true, on_delete: 'cascade' },
    { name: 'x_host_id', field_description: 'Host', ttype: 'many2one', relation: 'hr.employee', tracking: 1 },
    { name: 'x_account', field_description: 'Akun Live', ttype: 'selection', selection_ids: [[0, 0, { value: 'ss_official', name: '@shellasaukia.official', sequence: 1 }], [0, 0, { value: 'ss_beauty', name: '@ssbeauty.id', sequence: 2 }], [0, 0, { value: 'ss_hijab', name: '@sshijab.store', sequence: 3 }]] },
    { name: 'x_platform', field_description: 'Platform', ttype: 'selection', selection_ids: [[0, 0, { value: 'tiktok', name: 'TikTok Shop', sequence: 1 }], [0, 0, { value: 'shopee', name: 'Shopee Live', sequence: 2 }]] },
    { name: 'x_shift', field_description: 'Shift', ttype: 'selection', selection_ids: [[0, 0, { value: 'pagi', name: 'Pagi (09.00-12.00)', sequence: 1 }], [0, 0, { value: 'siang', name: 'Siang (13.00-16.00)', sequence: 2 }], [0, 0, { value: 'malam', name: 'Malam (19.00-22.00)', sequence: 3 }]] },
    { name: 'x_state', field_description: 'Status', ttype: 'selection', tracking: 1, selection_ids: [[0, 0, { value: 'plan', name: 'Terjadwal', sequence: 1 }], [0, 0, { value: 'live', name: 'Sedang Live', sequence: 2 }], [0, 0, { value: 'done', name: 'Selesai', sequence: 3 }]] },
    { name: 'x_start', field_description: 'Mulai', ttype: 'datetime' },
    { name: 'x_end', field_description: 'Selesai', ttype: 'datetime' },
    { name: 'x_target', field_description: 'Target Penjualan (Rp)', ttype: 'float', tracking: 1 },
    { name: 'x_viewers', field_description: 'Penonton (peak)', ttype: 'integer' },
    { name: 'x_notes', field_description: 'Catatan / Evaluasi', ttype: 'text' },
    { name: 'x_product_ids', field_description: 'Produk Dipromosikan', ttype: 'many2many', relation: 'product.template', relation_table: 'x_ss_live_product_rel', column1: 'session_id', column2: 'product_id' },
    { name: 'x_order_ids', field_description: 'Pesanan dari Live', ttype: 'one2many', relation: 'sale.order', relation_field: 'x_live_session_id' },
    { name: 'x_duration', field_description: 'Durasi (jam)', ttype: 'float', store: true, readonly: true, depends: 'x_start,x_end',
      compute: "for rec in self:\n    rec['x_duration'] = ((rec.x_end - rec.x_start).total_seconds() / 3600.0) if (rec.x_start and rec.x_end) else 0.0" },
    { name: 'x_actual', field_description: 'Realisasi Penjualan (Rp)', ttype: 'float', store: true, readonly: true, depends: 'x_order_ids,x_order_ids.amount_untaxed,x_order_ids.state',
      compute: "for rec in self:\n    rec['x_actual'] = sum(o.amount_untaxed for o in rec.x_order_ids if o.state == 'sale')" },
    { name: 'x_order_count', field_description: 'Jumlah Pesanan', ttype: 'integer', store: true, readonly: true, depends: 'x_order_ids,x_order_ids.state',
      compute: "for rec in self:\n    rec['x_order_count'] = len([o for o in rec.x_order_ids if o.state == 'sale'])" },
    { name: 'x_achievement', field_description: 'Pencapaian (%)', ttype: 'float', store: true, readonly: true, depends: 'x_actual,x_target',
      compute: "for rec in self:\n    rec['x_achievement'] = (rec.x_actual / rec.x_target * 100.0) if rec.x_target else 0.0" },
    { name: 'x_sales_per_hour', field_description: 'Penjualan per Jam (Rp)', ttype: 'float', store: true, readonly: true, depends: 'x_actual,x_duration',
      compute: "for rec in self:\n    rec['x_sales_per_hour'] = (rec.x_actual / rec.x_duration) if rec.x_duration else 0.0" },
  ];
  for (const f of F) await field(model, f);

  // access + multi-company rule
  await foc('ir.model.access', [['model_id', '=', model], ['group_id', '=', grp]], { name: 'x_ss_live_session demo', model_id: model, group_id: grp, perm_read: true, perm_write: true, perm_create: true, perm_unlink: true });
  await foc('ir.rule', [['model_id', '=', model], ['name', '=', 'Live session multi-company']], { name: 'Live session multi-company', model_id: model, domain_force: "[('x_company_id', 'in', company_ids)]" });

  // views
  const G = 'ss_demo.group_brand_ss_demo';
  async function view(name, type, arch, inherit) {
    const ex = await kw('ir.ui.view', 'search', [[['name', '=', name]]]);
    const vals = { name, type, model: inherit ? inherit.model : M, arch_db: arch };
    if (inherit) { vals.inherit_id = inherit.id; vals.mode = 'extension'; delete vals.type; }
    if (ex.length) { await kw('ir.ui.view', 'write', [ex, { arch_db: arch }]); return ex[0]; }
    return kw('ir.ui.view', 'create', [vals]);
  }
  await view('x_ss_live_session.form', 'form', `<form>
  <header><field name="x_state" widget="statusbar" options="{'clickable': '1'}"/></header>
  <sheet>
    <div class="oe_title"><h1><field name="x_name" placeholder="cth: LIVE TikTok 11.11 Pagi - Nadia"/></h1></div>
    <group>
      <group string="Jadwal">
        <field name="x_host_id"/><field name="x_platform"/><field name="x_account"/><field name="x_shift"/>
        <field name="x_start"/><field name="x_end"/><field name="x_duration" widget="float_time"/>
      </group>
      <group string="Target &amp; Hasil">
        <field name="x_target"/>
        <field name="x_actual"/><field name="x_achievement" widget="progressbar"/>
        <field name="x_order_count"/><field name="x_sales_per_hour"/><field name="x_viewers"/>
        <field name="x_company_id" groups="base.group_multi_company"/>
      </group>
    </group>
    <notebook>
      <page string="Pesanan dari Live"><field name="x_order_ids" readonly="1"><list><field name="name"/><field name="client_order_ref"/><field name="date_order"/><field name="amount_untaxed" sum="Total"/><field name="state"/></list></field></page>
      <page string="Produk Dipromosikan"><field name="x_product_ids" widget="many2many_tags"/></page>
      <page string="Catatan / Evaluasi"><field name="x_notes"/></page>
    </notebook>
  </sheet>
  <chatter/>
</form>`);
  await view('x_ss_live_session.list', 'list', `<list decoration-danger="x_state == 'done' and x_achievement &lt; 80" decoration-success="x_achievement &gt;= 100" default_order="x_start desc">
  <field name="x_start"/><field name="x_name"/><field name="x_host_id" widget="many2one_avatar_employee"/><field name="x_platform"/><field name="x_account"/>
  <field name="x_duration" widget="float_time" sum="Total"/><field name="x_target" sum="Total"/><field name="x_actual" sum="Total"/>
  <field name="x_achievement" widget="progressbar"/><field name="x_order_count" sum="Total"/><field name="x_state" widget="badge" decoration-info="x_state == 'plan'" decoration-warning="x_state == 'live'" decoration-success="x_state == 'done'"/>
</list>`);
  await view('x_ss_live_session.calendar', 'calendar', `<calendar date_start="x_start" date_stop="x_end" color="x_host_id" mode="week" quick_create="0">
  <field name="x_host_id" filters="1"/><field name="x_platform"/><field name="x_target"/><field name="x_actual"/>
</calendar>`);
  await view('x_ss_live_session.pivot', 'pivot', `<pivot><field name="x_host_id" type="row"/><field name="x_start" interval="week" type="col"/><field name="x_actual" type="measure"/><field name="x_target" type="measure"/></pivot>`);
  await view('x_ss_live_session.graph', 'graph', `<graph type="bar"><field name="x_host_id"/><field name="x_actual" type="measure"/></graph>`);
  await view('x_ss_live_session.search', 'search', `<search>
  <field name="x_name"/><field name="x_host_id"/>
  <filter name="f_tiktok" string="TikTok" domain="[('x_platform','=','tiktok')]"/>
  <filter name="f_under" string="Di bawah target (&lt;80%)" domain="[('x_state','=','done'),('x_achievement','&lt;',80)]"/>
  <filter name="f_plan" string="Terjadwal" domain="[('x_state','=','plan')]"/>
  <separator/><filter name="f_month" string="Bulan ini" domain="[('x_start','&gt;=', (context_today() + relativedelta(day=1)).strftime('%Y-%m-%d'))]"/>
  <group expand="0"><filter name="g_host" string="Host" context="{'group_by':'x_host_id'}"/><filter name="g_acc" string="Akun" context="{'group_by':'x_account'}"/><filter name="g_day" string="Hari" context="{'group_by':'x_start:day'}"/></group>
</search>`);
  // add live session on sale order form, visible only to demo group
  const soForm = (await kw('ir.model.data', 'check_object_reference', ['sale', 'view_order_form']))[1];
  await view('sale.order.form.x_live_session', null, `<data><xpath expr="//field[@name='client_order_ref']" position="after"><field name="x_live_session_id" groups="${G}"/></xpath></data>`, { id: soForm, model: 'sale.order' });

  // action + menu
  let act = (await kw('ir.actions.act_window', 'search', [[['res_model', '=', M]]]))[0];
  if (!act) act = await kw('ir.actions.act_window', 'create', [{ name: 'Live Streaming', res_model: M, view_mode: 'list,calendar,form,pivot,graph', context: "{'default_x_company_id': allowed_company_ids[0], 'default_x_state': 'plan', 'default_x_platform': 'tiktok'}", help: '<p class="o_view_nocontent_smiling_face">Jadwalkan sesi live pertama</p><p>Atur host, shift, target penjualan, dan pantau realisasinya per sesi.</p>' }]);
  const saleRoot = (await kw('ir.model.data', 'check_object_reference', ['sale', 'sale_menu_root']))[1];
  await foc('ir.ui.menu', [['name', '=', 'Live Streaming'], ['parent_id', '=', saleRoot]], { name: 'Live Streaming', parent_id: saleRoot, action: 'ir.actions.act_window,' + act, sequence: 3, groups_id: [[6, 0, [grp]]] });
  console.log('live model ready', model, act);
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-2000)); process.exit(1); });
