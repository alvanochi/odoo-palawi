// Post-processing: settlements, reseller payments, returns, recent warehouse flow, live sessions, targets
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const STEP = process.argv[2];
const addDays = (d, n) => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };

async function settlement() {
  for (const [pk, jk, fee] of [['mp_tts', 'tts', 0.08], ['mp_shp', 'shp', 0.095]]) {
    const inv = await kw('account.move', 'search_read', [[['partner_id', '=', ids.R[pk]], ['move_type', '=', 'out_invoice'], ['state', '=', 'posted'], ['payment_state', '=', 'not_paid'], ['invoice_date', '<=', '2026-11-08']]], { fields: ['invoice_date', 'amount_residual'] });
    const weeks = {};
    for (const i of inv) { const d = new Date(i.invoice_date + 'T00:00:00Z'); const dow = (d.getUTCDay() + 6) % 7; const wk = addDays(i.invoice_date, 6 - dow); (weeks[wk] = weeks[wk] || []).push(i); }
    for (const [wkEnd, list] of Object.entries(weeks).sort()) {
      const total = list.reduce((a, x) => a + x.amount_residual, 0);
      const net = Math.round(total * (1 - fee));
      await L.pay(list.map(x => x.id), ids.J[jk], addDays(wkEnd, 7), { amount: net, payment_difference_handling: 'reconcile', writeoff_account_id: ids.A.adminFee, writeoff_label: 'Biaya admin & layanan marketplace', communication: `Settlement ${jk.toUpperCase()} minggu s/d ${wkEnd}` });
      console.log('settled', pk, wkEnd, list.length, total, '->', net);
    }
  }
}
async function resellers() {
  const inv = await kw('account.move', 'search_read', [[['partner_id', 'in', [ids.R.res_aisyah, ids.R.res_medan, ids.R.dist_sby]], ['move_type', '=', 'out_invoice'], ['state', '=', 'posted'], ['payment_state', '=', 'not_paid']]], { fields: ['partner_id', 'invoice_date', 'invoice_date_due', 'amount_residual', 'name'] });
  for (const i of inv) {
    const p = i.partner_id[0];
    if (p === ids.R.res_medan && i.invoice_date >= '2026-10-01') continue; // overdue piutang demo
    if (i.invoice_date > '2026-10-25') continue; // belum jatuh tempo
    const payDate = addDays(i.invoice_date, p === ids.R.dist_sby ? 28 : 21);
    if (p === ids.R.dist_sby && i.invoice_date > '2026-10-10') { await L.pay([i.id], ids.J.bca, payDate, { amount: Math.round(i.amount_residual * 0.5), payment_difference_handling: 'open' }); console.log('partial', i.name); continue; }
    await L.pay([i.id], ids.J.bca, payDate); console.log('paid', i.name);
  }
}
async function returns() {
  const sos = await kw('sale.order', 'search_read', [[['team_id', 'in', [ids.TM.tts, ids.TM.shp]], ['state', '=', 'sale'], ['date_order', '>=', '2026-10-05'], ['date_order', '<', '2026-11-05'], ['invoice_status', '=', 'invoiced']]], { fields: ['name', 'picking_ids', 'date_order'], limit: 200 });
  const pickN = [3, 17, 41, 66, 90].map(i => sos[i]).filter(Boolean);
  for (const so of pickN) {
    const pk = (await kw('stock.picking', 'search_read', [[['id', 'in', so.picking_ids], ['state', '=', 'done'], ['picking_type_code', '=', 'outgoing']]], { fields: ['id'] }))[0];
    if (!pk) continue;
    if (await kw('stock.picking', 'search_count', [[['return_id', '=', pk.id]]])) continue;
    const w = await kw('stock.return.picking', 'create', [{ picking_id: pk.id }], { context: { active_id: pk.id, active_model: 'stock.picking' } });
    const lines = await kw('stock.return.picking.line', 'search_read', [[['wizard_id', '=', w]]], { fields: ['move_id', 'quantity'] });
    const ml = await kw('stock.move', 'read', [lines.map(l => l.move_id[0])], { fields: ['quantity'] });
    await kw('stock.return.picking.line', 'write', [[lines[0].id], { quantity: ml[0].quantity }]);
    for (const l of lines.slice(1)) await kw('stock.return.picking.line', 'write', [[l.id], { quantity: 0 }]);
    const r = await kw('stock.return.picking', 'action_create_returns', [[w]]);
    const rd = addDays(so.date_order.slice(0, 10), 6);
    await L.validatePicking(r.res_id, rd + ' 07:00:00');
    const ctx = { active_model: 'sale.order', active_ids: [so.id] };
    const wz = await kw('sale.advance.payment.inv', 'create', [{ advance_payment_method: 'delivered' }], { context: ctx });
    await kw('sale.advance.payment.inv', 'create_invoices', [[wz]], { context: ctx });
    const cn = await kw('account.move', 'search', [[['line_ids.sale_line_ids.order_id', '=', so.id], ['move_type', '=', 'out_refund'], ['state', '=', 'draft']]]);
    for (const c of cn) { await kw('account.move', 'write', [[c], { ref: 'Retur/refund pembeli (dummy)' }]); await L.postInvoice(c, rd); }
    await kw('sale.order', 'message_post', [[so.id]], { body: 'Retur diterima: barang cacat/tidak sesuai. Refund diproses melalui marketplace.' });
    console.log('return', so.name);
  }
}
async function recentFlow() {
  // offline orders of recent days: deliver + invoice + pay immediately; marketplace: pick (16th,17th) and pack (16th)
  const sos = await kw('sale.order', 'search_read', [[['state', '=', 'sale'], ['date_order', '>=', '2026-11-15 17:00:00'], ['company_id', '=', CID]]], { fields: ['name', 'team_id', 'date_order', 'picking_ids', 'invoice_ids'] });
  for (const so of sos) {
    const day = so.date_order.slice(0, 10);
    if (so.team_id[0] === ids.TM.off) {
      await L.processChain(so.name, so.date_order);
      if (!so.invoice_ids.length) {
        const ctx = { active_model: 'sale.order', active_ids: [so.id] };
        const w = await kw('sale.advance.payment.inv', 'create', [{ advance_payment_method: 'delivered' }], { context: ctx });
        await kw('sale.advance.payment.inv', 'create_invoices', [[w]], { context: ctx });
        const inv = (await kw('sale.order', 'read', [[so.id]], { fields: ['invoice_ids'] }))[0].invoice_ids[0];
        await L.postInvoice(inv, day); await L.pay([inv], ids.J.bca, day);
      }
      continue;
    }
    const steps = day <= '2026-11-16' ? 2 : day === '2026-11-17' ? 1 : 0;
    for (let s = 0; s < steps; s++) {
      const p = await kw('stock.picking', 'search_read', [[['origin', '=', so.name], ['state', 'in', ['assigned', 'confirmed', 'waiting']]]], { fields: ['id', 'picking_type_id', 'state'], order: 'id' });
      const ready = p.find(x => x.state === 'assigned') || p[0];
      if (!ready) break;
      await L.validatePicking(ready.id, null);
    }
  }
  console.log('recent flow', sos.length);
}
async function live() {
  const hosts = ['Nadia Putri', 'Citra Lestari', 'Fajar Ramadhan', 'Intan Permata'];
  const emp = {};
  for (const h of hosts) emp[h] = (await kw('hr.employee', 'search', [[['name', '=', h], ['company_id', '=', CID]]]))[0];
  const skill = { 'Nadia Putri': 1.25, 'Citra Lestari': 1.0, 'Fajar Ramadhan': 0.8, 'Intan Permata': 1.1 };
  const prod = { fashion: [ids.P.gamis, ids.P.tunik, ids.P.pashmina], beauty: [ids.P.serum, ids.P.lip, ids.P.lotion, ids.P.wash] };
  const liveTag = (await kw('crm.tag', 'search', [[['name', '=', 'SS Live Streaming']]]))[0];
  let n = 0, seed = 11; const r = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  for (let d = '2026-09-20'; d <= '2026-11-25'; d = addDays(d, 1)) {
    const shifts = [['pagi', '02:00:00', '05:00:00', 'ss_beauty', 'beauty'], ['malam', '12:00:00', '15:00:00', 'ss_official', 'fashion']];
    for (let si = 0; si < shifts.length; si++) {
      const [shift, st, en, acc, cat] = shifts[si];
      const name = `LIVE ${d} ${shift === 'pagi' ? 'Pagi' : 'Malam'}`;
      if (await kw('x_ss_live_session', 'search_count', [[['x_name', 'like', name]]])) continue;
      const dayIdx = Math.round((new Date(d) - new Date('2026-09-20')) / 864e5);
      const host = hosts[(dayIdx * 2 + si) % 4];
      const start = `${d} ${st}`, end = `${d} ${en}`;
      const isPast = end < '2026-11-18 12:00:00';
      const isNow = d === '2026-11-18' && shift === 'malam';
      const flash = ['2026-10-10', '2026-11-11'].includes(d);
      const target = Math.round(((shift === 'malam' ? 650000 : 450000) * (flash ? 2.5 : 1)) / 50000) * 50000;
      const vals = { x_name: `${name} - ${host.split(' ')[0]}`, x_company_id: CID, x_host_id: emp[host], x_platform: 'tiktok', x_account: acc, x_shift: shift, x_start: start, x_end: end, x_target: target, x_state: isNow ? 'live' : isPast ? 'done' : 'plan', x_product_ids: [[6, 0, prod[cat].concat(r() < 0.5 ? [prod.beauty[0]] : [])]], x_viewers: isPast ? Math.round((800 + r() * 2200) * skill[host] * (flash ? 3 : 1)) : 0 };
      const sid = await kw('x_ss_live_session', 'create', [vals]);
      if (isPast || isNow) {
        const orders = await kw('sale.order', 'search', [[['tag_ids', 'in', [liveTag]], ['date_order', '>=', start], ['date_order', '<', end], ['company_id', '=', CID]]]);
        if (orders.length) await kw('sale.order', 'write', [orders, { x_live_session_id: sid }]);
        const s = (await kw('x_ss_live_session', 'read', [[sid]], { fields: ['x_achievement', 'x_actual'] }))[0];
        if (isPast) await kw('x_ss_live_session', 'write', [[sid], { x_notes: s.x_achievement >= 100 ? 'Target tercapai. Produk hero laku keras, pertahankan script promo.' : s.x_achievement >= 80 ? 'Mendekati target. Perbanyak flash deal di 30 menit terakhir.' : 'Di bawah target. Evaluasi: penonton rendah / script kurang menarik.' }]);
      }
      n++;
    }
  }
  console.log('live sessions', n);
}
async function targets() {
  const g = await kw('sale.order', 'read_group', [[['state', '=', 'sale'], ['date_order', '>=', '2026-10-01'], ['date_order', '<', '2026-11-01'], ['company_id', '=', CID]], ['amount_untaxed:sum'], ['team_id']], { lazy: false });
  const oct = Object.fromEntries(g.map(x => [x.team_id[0], x.amount_untaxed]));
  const factor = { [ids.TM.tts]: 1.1, [ids.TM.shp]: 0.85, [ids.TM.res]: 1.0, [ids.TM.off]: 1.0 };
  for (const [t, f] of Object.entries(factor)) {
    const tgt = Math.round(((oct[t] || 10000000) * f) / 1000000) * 1000000;
    await kw('crm.team', 'write', [[+t], { invoiced_target: tgt }]);
    console.log('target', t, oct[t], '->', tgt);
  }
}
(async () => {
  await login();
  const map = { settlement, resellers, returns, recentFlow, live, targets };
  for (const s of STEP.split(',')) { console.log('== ' + s); await map[s](); }
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-1500)); process.exit(1); });
