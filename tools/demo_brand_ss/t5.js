// Purchasing + Production demo flows
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const ONLY = process.argv[2] || 'all';

async function po(key, partner, lines, { date, planned, receive, bill, payDate, toApprove, draft, note }) {
  const exist = await kw('purchase.order', 'search', [[['partner_ref', '=', key], ['company_id', '=', CID]]]);
  let id;
  if (exist.length) { id = exist[0]; const st = (await kw('purchase.order', 'read', [[id]], { fields: ['state'] }))[0].state; if (st !== 'purchase') { console.log('skip', key); return id; } }
  else {
  const pt = (await kw('stock.picking.type', 'search', [[['code', '=', 'incoming'], ['warehouse_id', '=', ids.W.main]]]))[0];
  const ol = [];
  for (const [tk, q, price] of lines) ol.push([0, 0, { product_id: await L.variant(tk), product_qty: q, price_unit: price, date_planned: planned + ' 03:00:00' }]);
  id = await kw('purchase.order', 'create', [{ partner_id: ids.R[partner], partner_ref: key, company_id: CID, picking_type_id: pt, date_order: date + ' 02:00:00', date_planned: planned + ' 03:00:00', order_line: ol, notes: note || false, user_id: 2 }]);
  if (draft) return id;
  if (toApprove) { await kw('purchase.order', 'write', [[id], { state: 'to approve' }]); return id; }
  await kw('purchase.order', 'button_confirm', [[id]]);
  await kw('purchase.order', 'write', [[id], { date_approve: date + ' 04:00:00', date_order: date + ' 02:00:00' }]);
  }
  const name = (await kw('purchase.order', 'read', [[id]], { fields: ['name'] }))[0].name;
  if (receive) await L.processChain(name, receive + ' 06:00:00');
  const hasInv = (await kw('purchase.order', 'read', [[id]], { fields: ['invoice_ids'] }))[0].invoice_ids.length;
  if (bill && !hasInv) {
    await kw('purchase.order', 'action_create_invoice', [[id]]);
    const inv = (await kw('purchase.order', 'read', [[id]], { fields: ['invoice_ids'] }))[0].invoice_ids[0];
    await L.postInvoice(inv, bill);
    if (payDate) await L.pay([inv], ids.J.bca, payDate);
  }
  console.log('PO', name, key);
  return id;
}

async function mo(tk, code, qty, { start, finish, lotName, exp, state, deadline, origin, scrap }) {
  const prod = await L.variant(tk, code);
  const ex = await kw('mrp.production', 'search', [[['origin', '=', origin], ['product_id', '=', prod], ['company_id', '=', CID]]]);
  if (ex.length) { console.log('skip MO', origin); return ex[0]; }
  const bom = (await kw('mrp.bom', 'search', [[['product_tmpl_id', '=', ids.P[tk]], ['company_id', '=', CID]]]))[0];
  const pt = (await kw('stock.picking.type', 'search', [[['code', '=', 'mrp_operation'], ['warehouse_id', '=', ids.W.main]]]))[0];
  const id = await kw('mrp.production', 'create', [{ product_id: prod, product_qty: qty, bom_id: bom, company_id: CID, picking_type_id: pt, date_start: start + ' 01:00:00', date_deadline: deadline ? deadline + ' 10:00:00' : false, origin, user_id: 2 }]);
  if (state === 'draft') return id;
  await kw('mrp.production', 'action_confirm', [[id]]);
  await kw('mrp.production', 'write', [[id], { date_start: start + ' 01:00:00' }]);
  await kw('mrp.production', 'action_assign', [[id]]);
  if (state === 'confirmed') return id;
  const produce = state === 'progress' ? Math.round(qty * 0.4) : qty;
  if (lotName) await kw('mrp.production', 'write', [[id], { lot_producing_id: await L.lot(prod, lotName, exp) }]);
  await kw('mrp.production', 'write', [[id], { qty_producing: produce }]);
  if (state === 'progress') return id;
  const raws = await kw('stock.move', 'search', [[['raw_material_production_id', '=', id]]]);
  await kw('stock.move', 'write', [raws, { picked: true }]);
  const r = await kw('mrp.production', 'button_mark_done', [[id]], { context: L.VCTX });
  if (r && r.res_model) throw new Error('MO wizard ' + r.res_model);
  await kw('mrp.production', 'write', [[id], { date_finished: finish + ' 09:00:00' }]);
  if (scrap) {
    const att = await kw('ir.attachment', 'create', [{ name: 'Laporan QC Reject ' + origin + '.txt', datas: Buffer.from('Laporan QC (demo): ' + scrap.reason).toString('base64'), mimetype: 'text/plain' }]);
    const loc = (await kw('stock.warehouse', 'read', [[ids.W.main]], { fields: ['lot_stock_id'] }))[0].lot_stock_id[0];
    const s = await kw('stock.scrap', 'create', [{ product_id: prod, scrap_qty: scrap.qty, production_id: id, company_id: CID, location_id: loc, lot_id: lotName ? await L.lot(prod, lotName) : false, attachment_ids: [[6, 0, [att]]], origin }]);
    await kw('stock.scrap', 'action_validate', [[s]]);
  }
  console.log('MO', origin, state || 'done');
  return id;
}

(async () => {
  await login();
  if (ONLY === 'all' || ONLY === 'po') {
    await po('SS-PO-DEMO-01', 'sup_tekstil', [['kain_wolfis', 600, 37500], ['kain_silk', 250, 51000]], { date: '2026-09-15', planned: '2026-09-22', receive: '2026-09-23', bill: '2026-09-23', payDate: '2026-10-07' });
    await po('SS-PO-DEMO-02', 'sup_maklon', [['base_serum', 12, 950000], ['base_lip', 3, 1100000], ['base_wash', 20, 160000]], { date: '2026-09-20', planned: '2026-10-01', receive: '2026-10-03', bill: '2026-10-03', payDate: '2026-10-17' });
    await po('SS-PO-DEMO-03', 'sup_kemasan', [['botol30', 1500, 7400], ['tube_lip', 1000, 4200], ['label', 3000, 3400]], { date: '2026-10-05', planned: '2026-10-15', receive: '2026-10-16', bill: '2026-10-16' }); // utang belum dibayar
    await po('SS-PO-DEMO-04', 'sup_tekstil', [['kain_wolfis', 800, 38000]], { date: '2026-10-28', planned: '2026-11-10', note: 'Supplier konfirmasi mundur karena antrian celup warna.' }); // TERLAMBAT
    await po('SS-PO-DEMO-05', 'sup_maklon', [['base_serum', 40, 950000], ['base_lip', 15, 1100000]], { date: '2026-11-16', planned: '2026-11-30', toApprove: true, note: 'Restock bahan serum untuk campaign 12.12 - butuh approval direksi (> Rp50 juta).' });
    await po('SS-PO-DEMO-06', 'sup_kemasan', [['bottle250', 1000, 6800], ['tube100', 1500, 5200]], { date: '2026-11-17', planned: '2026-11-28', draft: true });
  }
  if (ONLY === 'all' || ONLY === 'mo') {
    await mo('gamis', 'HTM-M', 60, { start: '2026-09-05', finish: '2026-09-12', origin: 'PROD-SEP-01' });
    await mo('gamis', 'NAV-L', 50, { start: '2026-09-25', finish: '2026-10-02', origin: 'PROD-SEP-02', scrap: { qty: 3, reason: 'Jahitan miring / noda kain' } });
    await mo('tunik', 'MOC-M', 60, { start: '2026-10-01', finish: '2026-10-06', origin: 'PROD-OKT-01' });
    await mo('serum', null, 300, { start: '2026-10-05', finish: '2026-10-08', lotName: 'SRM-2610C', exp: '2028-10-08', origin: 'PROD-OKT-02', scrap: { qty: 6, reason: 'Botol retak / pipet bocor' } });
    await mo('lip', null, 250, { start: '2026-10-20', finish: '2026-10-22', lotName: 'LIP-2610B', exp: '2028-10-22', origin: 'PROD-OKT-03' });
    await mo('wash', null, 150, { start: '2026-11-02', finish: '2026-11-04', lotName: 'FWS-2611B', exp: '2028-11-04', origin: 'PROD-NOV-01' });
    await mo('gamis', 'DUS-M', 80, { start: '2026-11-12', deadline: '2026-11-22', origin: 'PROD-NOV-02', state: 'progress', lotName: null });
    await mo('tunik', 'HTM-L', 50, { start: '2026-11-05', deadline: '2026-11-14', origin: 'PROD-NOV-03 (TERLAMBAT)', state: 'confirmed' });
    await mo('lotion', null, 300, { start: '2026-11-25', deadline: '2026-11-28', origin: 'PROD-NOV-04', state: 'confirmed' });
    await mo('serum', null, 500, { start: '2026-12-01', deadline: '2026-12-05', origin: 'PROD-DES-01 (Campaign 12.12)', state: 'draft' });
  }
  console.log('DONE');
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-2000)); process.exit(1); });
