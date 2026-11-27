// Seed R&D fund requests through the real flow, each step as the real user.
const { SA } = require('./approval_ids.json');
const { PRJ } = require('./rd_ids.json');
const ids = require('./ids.json');
const URL = 'https://palawi.rutekebangsaan.com', CID = 13;
class S {
  constructor(l, p) { this.l = l; this.p = p; this.c = ''; }
  async post(path, params) { const r = await fetch(URL + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: this.c }, body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params }) }); const sc = r.headers.get('set-cookie'); if (sc) this.c = sc.split(';')[0]; const j = await r.json(); if (j.error) throw new Error(`[${this.l}] ` + (j.error.data && j.error.data.message || j.error.message)); return j.result; }
  async auth() { const r = await this.post('/web/session/authenticate', { db: 'odoo18_palawi', login: this.l, password: this.p }); this.uid = r.uid; return this; }
  kw(m, me, a = [], k = {}) { k = Object.assign({}, k); k.context = Object.assign({ allowed_company_ids: [CID], tz: 'Asia/Jakarta' }, k.context || {}); return this.post('/web/dataset/call_kw', { model: m, method: me, args: a, kwargs: k }); }
  run(sa, id) { return this.post('/web/action/run', { action_id: sa, context: { active_model: 'x_ss_approval', active_id: id, active_ids: [id], allowed_company_ids: [CID] } }); }
}
(async () => {
  const PW = process.env.DEMO_PW;
  const yuni = await new S('ss.yuni', PW).auth(), shella = await new S('ss.shella', PW).auth(), dewi = await new S('ss.dewi', PW).auth();
  const admin = await new S('admin', process.env.ODOO_PASSWORD).auth();
  const dept = (await admin.kw('hr.department', 'search', [[['name', '=', 'Product Development'], ['company_id', '=', CID]]]))[0];
  let lab = (await admin.kw('res.partner', 'search', [[['name', '=', 'PT Lab Uji Kosmetik Indonesia'], ['company_id', '=', CID]]]))[0];
  if (!lab) lab = await admin.kw('res.partner', 'create', [{ name: 'PT Lab Uji Kosmetik Indonesia', company_id: CID, is_company: true, supplier_rank: 1, city: 'Jakarta Timur', country_id: 100 }]);
  const G = PRJ['R&D - SS Glow Serum Gen 2'].an, LIP = PRJ['R&D - SS Lip Cream 4 Shade Baru'].an, SUN = PRJ['R&D - SS Sunscreen SPF 50 PA++++'].an;
  const st = async id => (await admin.kw('x_ss_approval', 'read', [[id]], { fields: ['x_number', 'x_state', 'x_approver_id', 'x_approval_path', 'x_over_budget', 'x_transfer_move_id'] }))[0];
  // [name, analytic, amount, partner, reason, upto, transferDate]
  const REQ = [
    ['Bahan aktif niacinamide & ceramide untuk sampel formula', G, 8500000, ids.R.sup_maklon, 'Pembelian bahan aktif grade kosmetik untuk 3 varian formula awal.', 'transfer', '2026-10-14'],
    ['Uji stabilitas 3 bulan (lab eksternal) - Glow Serum Gen 2', G, 12000000, lab, 'Uji stabilitas suhu 25/40°C selama 3 bulan, syarat dossier BPOM.', 'transfer', '2026-11-10'],
    ['Sampel shade batch 1 dari maklon - Lip Cream', LIP, 4500000, ids.R.sup_maklon, '4 shade x 50 pcs untuk uji internal & panel tester.', 'transfer', '2026-10-28'],
    ['Notifikasi BPOM & dokumen regulasi - Glow Serum Gen 2', G, 6000000, false, 'Biaya notifikasi & konsultan regulasi.', 'finance', null],
    ['Sampel shade batch 2 (revisi warna Nude) - Lip Cream', LIP, 3750000, ids.R.sup_maklon, 'Revisi shade Nude yang terlalu pucat di batch 1.', 'director', null],
    ['Uji SPF & PA in-vivo di lab eksternal - Sunscreen', SUN, 22000000, lab, 'Uji SPF 50 & PA++++ (ISO 24444 & ISO 24442) untuk klaim label.', 'submit', null],
    ['Kemasan prototipe airless pump - Glow Serum Gen 2', G, 2500000, false, 'Prototipe kemasan 30ml airless untuk foto & uji pengguna.', 'draft', null],
  ];
  for (const [name, an, amt, partner, reason, upto, tdate] of REQ) {
    if ((await admin.kw('x_ss_approval', 'search_count', [[['x_name', '=', name]]]))) { console.log('exists', name); continue; }
    const id = await yuni.kw('x_ss_approval', 'create', [{ x_name: name, x_type: 'riset', x_company_id: CID, x_requester_id: yuni.uid, x_state: 'draft', x_department_id: dept, x_analytic_id: an, x_amount: amt, x_partner_id: partner, x_reason: reason, x_deadline: '2026-12-05' }]);
    if (upto !== 'draft') await yuni.run(SA.submit, id);
    if (['director', 'finance', 'transfer'].includes(upto)) await shella.run(SA.approve, id);
    if (['finance', 'transfer'].includes(upto)) await dewi.run(SA.approve, id);
    if (upto === 'transfer') {
      await dewi.run(SA.transfer, id);
      const mv = (await st(id)).x_transfer_move_id[0];
      await admin.kw('account.move', 'button_draft', [[mv]]);
      await admin.kw('account.move', 'write', [[mv], { date: tdate }]);
      await admin.kw('account.move', 'action_post', [[mv]]);
    }
    console.log(JSON.stringify(await st(id)));
  }
  const pb = await admin.kw('x_ss_project_budget', 'search_read', [[]], { fields: ['x_name', 'x_amount', 'x_actual', 'x_committed', 'x_remaining', 'x_usage'] });
  console.table(pb.map(p => ({ proyek: p.x_name, budget: p.x_amount, realisasi: p.x_actual, diajukan: p.x_committed, sisa: p.x_remaining, pakai: Math.round(p.x_usage) + '%' })));
})().catch(e => console.error('FAIL', e.message));
