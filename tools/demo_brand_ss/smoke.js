// Smoke test of the demo flows, each step as the real demo user (records are kept as normal demo data dated today).
const ids = require('./ids.json');
const URL = 'https://palawi.rutekebangsaan.com', CID = 13;
class S {
  constructor(l, p) { this.l = l; this.p = p; this.c = ''; }
  async post(path, params) { const r = await fetch(URL + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: this.c }, body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params }) }); const sc = r.headers.get('set-cookie'); if (sc) this.c = sc.split(';')[0]; const j = await r.json(); if (j.error) { const e = new Error(`[${this.l}] ` + (j.error.data && j.error.data.message || j.error.message)); e.debug = j.error.data && j.error.data.debug; throw e; } return j.result; }
  async auth() { const r = await this.post('/web/session/authenticate', { db: 'odoo18_palawi', login: this.l, password: this.p }); this.uid = r.uid; return this; }
  kw(m, me, a = [], k = {}) { k = Object.assign({}, k); k.context = Object.assign({ allowed_company_ids: [CID], tz: 'Asia/Jakarta' }, k.context || {}); return this.post('/web/dataset/call_kw', { model: m, method: me, args: a, kwargs: k }); }
}
const results = [];
async function step(name, fn) {
  try { const r = await fn(); results.push(['OK  ', name, r || '']); return r; }
  catch (e) { results.push(['FAIL', name, e.message + ' ' + ((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File')).slice(-2).join(' | '))]); return null; }
}
async function validate(s, pid) {
  const r = await s.kw('stock.picking', 'button_validate', [[pid]]);
  if (r && r.res_model) throw new Error('wizard ' + r.res_model);
  return (await s.kw('stock.picking', 'read', [[pid]], { fields: ['name', 'state'] }))[0];
}
async function payWizard(s, moveIds, journal) {
  const ctx = { active_model: 'account.move', active_ids: moveIds };
  const w = await s.kw('account.payment.register', 'create', [{ journal_id: journal }], { context: ctx });
  await s.kw('account.payment.register', 'action_create_payments', [[w]], { context: ctx });
  return (await s.kw('account.move', 'read', [moveIds], { fields: ['name', 'payment_state'] }));
}
(async () => {
  const PW = process.env.DEMO_PW;
  const u = {}; for (const l of ['maya', 'joko', 'dewi', 'budi', 'reza', 'eko']) u[l] = await new S('ss.' + l, PW).auth();
  const serum = (await u.maya.kw('product.product', 'search', [[['default_code', '=', 'SS-SRM']]]))[0];
  const gamis = (await u.maya.kw('product.product', 'search', [[['default_code', '=', 'SS-GMS-NAV-M']]]))[0];

  // 1. Sales order (Maya) -> 3-step delivery (Joko) -> invoice (Maya) -> payment wizard (Dewi)
  const so = await step('Maya: buat & konfirmasi sales order TikTok', async () => {
    const id = await u.maya.kw('sale.order', 'create', [{ partner_id: ids.R.mp_tts, team_id: ids.TM.tts, client_order_ref: 'TTS-5790001234', order_line: [[0, 0, { product_id: serum, product_uom_qty: 2 }], [0, 0, { product_id: gamis, product_uom_qty: 1 }]] }]);
    await u.maya.kw('sale.order', 'action_confirm', [[id]]);
    return id;
  });
  if (so) {
    const name = (await u.maya.kw('sale.order', 'read', [[so]], { fields: ['name'] }))[0].name;
    for (let i = 0; i < 3; i++) {
      await step(`Joko: validasi transfer tahap ${i + 1} (${name})`, async () => {
        const p = await u.joko.kw('stock.picking', 'search_read', [[['origin', '=', name], ['state', '=', 'assigned']]], { fields: ['name'], limit: 1, order: 'id' });
        if (!p.length) throw new Error('tidak ada picking siap');
        const r = await validate(u.joko, p[0].id); return r.name + ' ' + r.state;
      });
    }
    const inv = await step('Maya: buat invoice dari SO', async () => {
      const ctx = { active_model: 'sale.order', active_ids: [so] };
      const w = await u.maya.kw('sale.advance.payment.inv', 'create', [{ advance_payment_method: 'delivered' }], { context: ctx });
      await u.maya.kw('sale.advance.payment.inv', 'create_invoices', [[w]], { context: ctx });
      return (await u.maya.kw('sale.order', 'read', [[so]], { fields: ['invoice_ids'] }))[0].invoice_ids[0];
    });
    if (inv) {
      await step('Dewi: posting invoice', async () => { await u.dewi.kw('account.move', 'action_post', [[inv]]); return (await u.dewi.kw('account.move', 'read', [[inv]], { fields: ['name', 'amount_total'] }))[0]; });
      await step('Dewi: Register Payment (wizard) ke Saldo TikTok Shop', async () => JSON.stringify(await payWizard(u.dewi, [inv], ids.J.tts)));
    }
  }
  // 2. PO (Budi) -> receipt 2 steps (Joko) -> bill + payment wizard (Dewi)
  const po = await step('Budi: buat & konfirmasi PO kecil', async () => {
    const lab = (await u.budi.kw('product.product', 'search', [[['default_code', '=', 'RM-003']]]))[0];
    const id = await u.budi.kw('purchase.order', 'create', [{ partner_id: ids.R.sup_kemasan, order_line: [[0, 0, { product_id: lab, product_qty: 500, price_unit: 3400 }]] }]);
    await u.budi.kw('purchase.order', 'button_confirm', [[id]]);
    return id;
  });
  if (po) {
    const pname = (await u.budi.kw('purchase.order', 'read', [[po]], { fields: ['name', 'state'] }))[0];
    results.push(['INFO', 'status PO', pname.name + ' ' + pname.state]);
    for (let i = 0; i < 2; i++) await step(`Joko: terima barang tahap ${i + 1}`, async () => {
      const p = await u.joko.kw('stock.picking', 'search_read', [[['origin', '=', pname.name], ['state', '=', 'assigned']]], { fields: ['name'], limit: 1, order: 'id' });
      if (!p.length) throw new Error('tidak ada picking siap');
      const r = await validate(u.joko, p[0].id); return r.name + ' ' + r.state;
    });
    const bill = await step('Dewi: buat & posting tagihan dari PO', async () => {
      await u.dewi.kw('purchase.order', 'action_create_invoice', [[po]]);
      const b = (await u.dewi.kw('purchase.order', 'read', [[po]], { fields: ['invoice_ids'] }))[0].invoice_ids[0];
      await u.dewi.kw('account.move', 'write', [[b], { invoice_date: '2026-11-18' }]);
      await u.dewi.kw('account.move', 'action_post', [[b]]);
      return b;
    });
    if (bill) await step('Dewi: Register Payment tagihan dari BCA', async () => JSON.stringify(await payWizard(u.dewi, [bill], ids.J.bca)));
  }
  // 3. MO with lot (Joko)
  await step('Joko: MO Lip Cream 20 pcs + generate lot + selesai', async () => {
    const bom = (await u.joko.kw('mrp.bom', 'search', [[['product_tmpl_id', '=', ids.P.lip]]]))[0];
    const lip = (await u.joko.kw('product.product', 'search', [[['product_tmpl_id', '=', ids.P.lip]]]))[0];
    const id = await u.joko.kw('mrp.production', 'create', [{ product_id: lip, product_qty: 20, bom_id: bom, origin: 'Produksi sampel shade baru' }]);
    await u.joko.kw('mrp.production', 'action_confirm', [[id]]);
    await u.joko.kw('mrp.production', 'action_generate_serial', [[id]]);
    await u.joko.kw('mrp.production', 'write', [[id], { qty_producing: 20 }]);
    const raws = await u.joko.kw('stock.move', 'search', [[['raw_material_production_id', '=', id]]]);
    await u.joko.kw('stock.move', 'write', [raws, { picked: true }]);
    const r = await u.joko.kw('mrp.production', 'button_mark_done', [[id]]);
    if (r && r.res_model) throw new Error('wizard ' + r.res_model);
    return (await u.joko.kw('mrp.production', 'read', [[id]], { fields: ['name', 'state', 'lot_producing_id'] }))[0];
  });
  // 4. Access checks
  await step('Reza TIDAK boleh lihat tagihan vendor (hak akses)', async () => { try { await u.reza.kw('account.move', 'search', [[['move_type', '=', 'in_invoice']]], { limit: 1 }); throw new Error('Reza bisa membaca tagihan vendor'); } catch (e) { if (e.message.includes('bisa membaca')) throw e; return 'ditolak (benar)'; } });
  await step('Joko TIDAK boleh buka Executive Dashboard data budget', async () => { try { await u.joko.kw('crossovered.budget.lines', 'search', [[]], { limit: 1 }); throw new Error('Joko bisa membaca budget'); } catch (e) { if (e.message.includes('bisa membaca')) throw e; return 'ditolak (benar)'; } });
  await step('Eko: baca sesi POS terbuka', async () => (await u.eko.kw('pos.session', 'search_read', [[['state', '=', 'opened']]], { fields: ['name', 'user_id'] })));
  console.table(results.map(([s, n, r]) => ({ status: s, langkah: n, hasil: String(typeof r === 'object' ? JSON.stringify(r) : r).slice(0, 110) })));
})().catch(e => { console.error('ABORT', e.message); console.table(results); });
