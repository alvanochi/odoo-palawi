// Seed approval requests, each step executed as the real demo user (multi-session JSON-RPC).
const ids = require('./ids.json');
const { SA } = require('./approval_ids.json');
const URL = 'https://palawi.rutekebangsaan.com';
const PW = process.env.DEMO_PW;
const CID = 13;
class S {
  constructor(login, pw) { this.login = login; this.pw = pw; this.cookie = ''; }
  async post(path, params) {
    const r = await fetch(URL + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: this.cookie }, body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params }) });
    const sc = r.headers.get('set-cookie'); if (sc) this.cookie = sc.split(';')[0];
    const j = await r.json(); if (j.error) { const e = new Error(`[${this.login}] ` + (j.error.data && j.error.data.message || j.error.message)); throw e; } return j.result;
  }
  async auth() { const r = await this.post('/web/session/authenticate', { db: 'odoo18_palawi', login: this.login, password: this.pw }); this.uid = r.uid; return this; }
  kw(model, method, args = [], kwargs = {}) { kwargs = Object.assign({}, kwargs); kwargs.context = Object.assign({ allowed_company_ids: [CID], tz: 'Asia/Jakarta' }, kwargs.context || {}); return this.post('/web/dataset/call_kw', { model, method, args, kwargs }); }
  run(sa, recId) { return this.post('/web/action/run', { action_id: sa, context: { active_model: 'x_ss_approval', active_id: recId, active_ids: [recId], allowed_company_ids: [CID] } }); }
}
const pp = async (s, tmpl) => (await s.kw('product.product', 'search', [[['product_tmpl_id', '=', ids.P[tmpl]]]], { limit: 1 }))[0];
const dept = async (s, n) => (await s.kw('hr.department', 'search', [[['name', '=', n], ['company_id', '=', CID]]]))[0];

(async () => {
  const u = {};
  for (const l of ['shella', 'dewi', 'reza', 'budi', 'joko', 'maya']) u[l] = await new S('ss.' + l, PW).auth();
  const admin = await new S(process.env.ODOO_LOGIN, process.env.ODOO_PASSWORD).auth();
  async function create(s, vals) {
    const ex = await admin.kw('x_ss_approval', 'search', [[['x_name', '=', vals.x_name]]]);
    if (ex.length) { console.log('exists', vals.x_name); return null; }
    return s.kw('x_ss_approval', 'create', [Object.assign({ x_company_id: CID, x_requester_id: s.uid, x_state: 'draft' }, vals)]);
  }
  const st = async id => (await admin.kw('x_ss_approval', 'read', [[id]], { fields: ['x_number', 'x_state', 'x_approver_id', 'x_approval_path', 'x_over_budget'] }))[0];

  // 1) Pembelian - full flow -> PO
  let id = await create(u.budi, { x_name: 'Restock kain wolfis & silk untuk produksi Desember', x_type: 'pembelian', x_partner_id: ids.R.sup_tekstil, x_department_id: await dept(u.budi, 'Purchasing & Procurement'), x_analytic_id: ids.AN.prod, x_deadline: '2026-11-25', x_reason: 'Stok kain wolfis tinggal ~30% dan PO sebelumnya (P00023) terlambat. Dibutuhkan untuk produksi gamis koleksi Ramadhan.', x_line_ids: [[0, 0, { x_product_id: await pp(u.budi, 'kain_wolfis'), x_qty: 1000, x_price: 38000 }], [0, 0, { x_product_id: await pp(u.budi, 'kain_silk'), x_qty: 200, x_price: 51000 }]] });
  if (id) { await u.budi.run(SA.submit, id); await u.dewi.run(SA.approve, id); await u.budi.run(SA.make_po, id); console.log(await st(id)); }

  // 2) Pembelian kecil - menunggu atasan (untuk demo live)
  id = await create(u.budi, { x_name: 'Botol pump 250ml untuk produksi Body Lotion', x_type: 'pembelian', x_partner_id: ids.R.sup_kemasan, x_department_id: await dept(u.budi, 'Purchasing & Procurement'), x_analytic_id: ids.AN.prod, x_deadline: '2026-11-22', x_reason: 'Kebutuhan MO Body Lotion 300 pcs (PROD-NOV-04).', x_line_ids: [[0, 0, { x_product_id: await pp(u.budi, 'bottle250'), x_qty: 1000, x_price: 6800 }]] });
  if (id) { await u.budi.run(SA.submit, id); console.log(await st(id)); }

  // 3) Campaign melebihi anggaran -> Finance sudah approve, menunggu Direksi
  id = await create(u.reza, { x_name: 'Campaign 12.12 - TikTok Ads + 3 KOL Glow Serum', x_type: 'campaign', x_department_id: await dept(u.reza, 'Digital Marketing, KOL & Affiliate'), x_analytic_id: ids.AN.mkt, x_amount: 35000000, x_deadline: '2026-11-28', x_reason: 'Target penjualan 12.12 Rp 250 jt (ROAS target 7x). Rincian: TikTok Ads Rp 20 jt, 3 KOL Rp 12 jt, affiliate boost Rp 3 jt.' });
  if (id) { await u.reza.run(SA.submit, id); await u.dewi.run(SA.approve, id); console.log(await st(id)); }

  // 4) Kebutuhan kantor - disetujui & selesai
  id = await create(u.joko, { x_name: 'Printer label barcode + 2 scanner untuk gudang', x_type: 'kantor', x_department_id: await dept(u.joko, 'Gudang & Inventory'), x_analytic_id: ids.AN.wh, x_amount: 4500000, x_deadline: '2026-11-15', x_reason: 'Untuk mempercepat picking & packing order marketplace (barcode per SKU).' });
  if (id) { await u.joko.run(SA.submit, id); await u.dewi.run(SA.approve, id); await u.joko.run(SA.done, id); console.log(await st(id)); }

  // 5) Event - ditolak finance
  id = await create(u.maya, { x_name: 'Pop-up store Muslim Fashion Festival (JCC)', x_type: 'event', x_department_id: await dept(u.maya, 'Brand Activation & Partnership'), x_analytic_id: ids.AN.act, x_amount: 45000000, x_deadline: '2026-11-30', x_reason: 'Booth 6x3m selama 4 hari. Estimasi penjualan Rp 120 jt.' });
  if (id) {
    await u.maya.run(SA.submit, id); await u.shella.run(SA.approve, id);
    await u.dewi.kw('x_ss_approval', 'write', [[id], { x_reject_reason: 'Cashflow Desember diprioritaskan untuk stok campaign 12.12. Ajukan ulang dengan skema sponsor / bagi hasil dengan penyelenggara.' }]);
    await u.dewi.run(SA.reject, id); console.log(await st(id));
  }

  // 6) Pembayaran supplier - menunggu Direksi
  const bill = (await admin.kw('account.move', 'search', [[['partner_id', '=', ids.R.sup_kemasan], ['move_type', '=', 'in_invoice'], ['payment_state', '=', 'not_paid'], ['company_id', '=', CID]]], { limit: 1 }))[0];
  id = await create(u.dewi, { x_name: 'Pembayaran tagihan PT Kemasan Prima (PO P00022)', x_type: 'pembayaran', x_partner_id: ids.R.sup_kemasan, x_department_id: await dept(u.dewi, 'Finance & Accounting'), x_amount: 28305000, x_deadline: '2026-11-20', x_bill_id: bill || false, x_reason: 'Jatuh tempo 30 hari. Barang sudah diterima lengkap.' });
  if (id) { await u.dewi.run(SA.submit, id); console.log(await st(id)); }

  // 7) Permintaan produksi - menunggu Direksi (atasan Maya)
  id = await create(u.maya, { x_name: 'Produksi tambahan Glow Serum 500 pcs untuk 12.12', x_type: 'produksi', x_department_id: await dept(u.maya, 'Marketplace & E-Commerce'), x_analytic_id: ids.AN.prod, x_deadline: '2026-12-05', x_reason: 'Proyeksi penjualan serum naik 3x saat 12.12 berdasarkan tren 11.11.', x_line_ids: [[0, 0, { x_product_id: await pp(u.maya, 'serum'), x_qty: 500, x_price: 48000 }]] });
  if (id) { await u.maya.run(SA.submit, id); console.log(await st(id)); }

  // 8) Draft - untuk demo live: kecil tapi melebihi anggaran -> wajib Direksi
  id = await create(u.reza, { x_name: 'Fee KOL @glowwithkirana - video Desember', x_type: 'campaign', x_partner_id: (await admin.kw('res.partner', 'search', [[['name', 'like', 'glowwithkirana'], ['company_id', '=', CID]]]))[0], x_department_id: await dept(u.reza, 'Digital Marketing, KOL & Affiliate'), x_analytic_id: ids.AN.mkt, x_amount: 5000000, x_deadline: '2026-12-01', x_reason: '1 video review + 3 story. Link affiliate SSKIRANA.' });
  if (id) console.log('draft', await st(id));
})().catch(e => { console.error(e.message); process.exit(1); });
