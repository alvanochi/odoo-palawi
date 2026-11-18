// Dummy multichannel sales: TikTok Shop, Shopee, Reseller/Distributor, Offline. Resumable (keyed on client_order_ref).
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const fs = require('fs');
const PHASE = process.argv[2] || 'history'; // history | recent
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const rand = rng(20261118);
const ri = (a, b) => a + Math.floor(rand() * (b - a + 1));
const pick = arr => arr[Math.floor(rand() * arr.length)];
const pad = n => String(n).padStart(2, '0');
const log = m => { console.log(m); fs.appendFileSync('t6.log', m + '\n'); };

(async () => {
  await login();
  // tags
  const TAG = {};
  for (const t of ['SS Live Streaming', 'SS Affiliate', 'SS Flash Sale']) {
    TAG[t] = (await kw('crm.tag', 'search', [[['name', '=', t]]]))[0] || await kw('crm.tag', 'create', [{ name: t }]);
  }
  const term30 = (await kw('account.payment.term', 'search', [[['name', '=', '30 Days']]]))[0];
  for (const k of ['res_aisyah', 'res_medan', 'dist_sby']) await kw('res.partner', 'write', [[ids.R[k]], { property_payment_term_id: term30 }]);

  // product pool with weights
  const pool = [];
  const add = (arr, w) => { for (const p of arr) for (let i = 0; i < w; i++) pool.push(p); };
  for (const [k, w] of [['gamis', 2], ['tunik', 2], ['pashmina', 5]]) add(await L.variants(k), w);
  for (const [k, w] of [['serum', 30], ['lip', 22], ['lotion', 10], ['wash', 14]]) add(await L.variants(k), w);
  const fashionOnly = pool.filter(p => /SS-(GMS|TNK|PSM)/.test(p.default_code));

  const wh = await kw('stock.warehouse', 'read', [[ids.W.main, ids.W.store]], { fields: ['lot_stock_id'] });

  // build order plan
  const plan = [];
  const start = new Date('2026-09-20T00:00:00Z'), end = new Date('2026-11-18T00:00:00Z');
  let n = 0;
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const day = d.toISOString().slice(0, 10);
    const dow = d.getUTCDay();
    const payday = [25, 26, 27, 28, 1, 2].includes(d.getUTCDate());
    const isFlash = ['2026-10-10', '2026-11-11'].includes(day);
    const tts = ri(3, 5) + (dow === 5 || dow === 6 ? 1 : 0) + (payday ? 2 : 0) + (isFlash ? 6 : 0);
    const shp = ri(1, 3) + (payday ? 1 : 0) + (isFlash ? 5 : 0);
    for (let i = 0; i < tts; i++) {
      const live = rand() < 0.45;
      const hour = live ? pick([2, 3, 4, 12, 13, 14]) : ri(0, 16); // UTC (WIB-7): live 09-12 & 19-22 WIB
      plan.push({ ch: 'tts', day, time: `${pad(hour)}:${pad(ri(0, 59))}:00`, ref: 'TTS-' + (5780000000 + (n++) * 7919), tags: [live && TAG['SS Live Streaming'], rand() < 0.15 && TAG['SS Affiliate'], isFlash && TAG['SS Flash Sale']].filter(Boolean), lines: ri(1, 3), qmax: 2 });
    }
    for (let i = 0; i < shp; i++) plan.push({ ch: 'shp', day, time: `${pad(ri(0, 16))}:${pad(ri(0, 59))}:00`, ref: 'SHP-' + (2610000000 + (n++) * 104729), tags: [isFlash && TAG['SS Flash Sale']].filter(Boolean), lines: ri(1, 3), qmax: 2 });
    if (d.getUTCDate() % 6 === 0) plan.push({ ch: 'res', day, time: '03:00:00', ref: 'B2B-' + day.replace(/-/g, ''), partner: pick(['res_aisyah', 'res_medan', 'dist_sby']), lines: ri(3, 5), qmin: 8, qmax: 24 });
    if (rand() < 0.6) plan.push({ ch: 'off', day, time: `${pad(ri(4, 13))}:${pad(ri(0, 59))}:00`, ref: 'KMG-' + day.replace(/-/g, '') + '-' + ri(10, 99), lines: ri(1, 3), qmax: 2, fashionBias: true });
  }
  const recentCut = '2026-11-16';
  const R0 = process.argv[3] || '0000', R1 = process.argv[4] || '9999';
  const todo = plan.filter(o => (PHASE === 'history' ? o.day < recentCut : o.day >= recentCut) && o.day >= R0 && o.day <= R1);
  log(`phase ${PHASE}: ${todo.length} orders (plan total ${plan.length})`);

  const CH = {
    tts: { partner: ids.R.mp_tts, team: ids.TM.tts, an: ids.AN.tts, wh: ids.W.main },
    shp: { partner: ids.R.mp_shp, team: ids.TM.shp, an: ids.AN.shp, wh: ids.W.main },
    res: { team: ids.TM.res, an: ids.AN.res, wh: ids.W.main },
    off: { partner: ids.R.walkin, team: ids.TM.off, an: ids.AN.off, wh: ids.W.store },
  };
  const days = [...new Set(todo.map(o => o.day))];
  let total = 0;
  for (const day of days) {
    const orders = todo.filter(o => o.day === day);
    const refs = orders.map(o => o.ref);
    const ex = await kw('sale.order', 'search_read', [[['client_order_ref', 'in', refs], ['company_id', '=', CID]]], { fields: ['client_order_ref', 'state'] });
    const byRef = Object.fromEntries(ex.map(e => [e.client_order_ref, e]));
    const toConfirm = []; const meta = {};
    for (const o of orders) {
      const c = CH[o.ch];
      let so = byRef[o.ref] && byRef[o.ref].id;
      if (!so && process.env.THIN && o.ch !== 'res' && (o.ref.charCodeAt(o.ref.length - 1) + o.ref.charCodeAt(o.ref.length - 2)) % 2 === 1) continue;
      if (!so) {
        const partner = o.partner ? ids.R[o.partner] : c.partner;
        const used = new Set(); const ol = [];
        for (let k = 0; k < o.lines; k++) {
          let p; let tries = 0;
          do { p = pick(o.fashionBias && rand() < 0.6 ? fashionOnly : pool); } while (used.has(p.id) && tries++ < 10);
          if (used.has(p.id)) continue; used.add(p.id);
          const an = {}; an[String(c.an)] = 100;
          ol.push([0, 0, { product_id: p.id, product_uom_qty: ri(o.qmin || 1, o.qmax), analytic_distribution: an }]);
        }
        so = await kw('sale.order', 'create', [{ partner_id: partner, team_id: c.team, client_order_ref: o.ref, company_id: CID, warehouse_id: c.wh, order_line: ol, tag_ids: [[6, 0, o.tags || []]], user_id: 265, date_order: `${o.day} ${o.time}` }]);
        if ((o.ch === 'tts' || o.ch === 'shp') && rand() < 0.04) {
          await kw('sale.order', 'write', [[so], { note: 'Dibatalkan pembeli di marketplace (dummy)' }]);
          await kw('sale.order', 'action_cancel', [[so]], { context: { disable_cancel_warning: true } });
          continue;
        }
        toConfirm.push(so);
      } else if (byRef[o.ref].state === 'cancel') continue;
      else if (byRef[o.ref].state === 'draft') toConfirm.push(so);
      meta[so] = o;
    }
    if (toConfirm.length) {
      await kw('sale.order', 'action_confirm', [toConfirm]);
      for (const so of toConfirm) await kw('sale.order', 'write', [[so], { date_order: `${meta[so].day} ${meta[so].time}` }]);
    }
    const soIds = Object.keys(meta).map(Number);
    if (PHASE === 'recent' || !soIds.length) { total += soIds.length; log(`${day}: ${soIds.length} orders open`); continue; }
    // deliveries: group by ship date (offline same day, others next day)
    const shipOf = o => { const s = new Date(o.day + 'T00:00:00Z'); s.setUTCDate(s.getUTCDate() + (o.ch === 'off' ? 0 : 1)); return s.toISOString().slice(0, 10); };
    const groups = {};
    for (const so of soIds) (groups[shipOf(meta[so])] = groups[shipOf(meta[so])] || []).push(so);
    for (const [sd, sos] of Object.entries(groups)) {
      const pk = await kw('stock.picking', 'search', [[['sale_id', 'in', sos], ['state', 'not in', ['done', 'cancel']]]]);
      if (pk.length) {
        await kw('stock.picking', 'action_assign', [pk]);
        const mv = await kw('stock.move', 'search', [[['picking_id', 'in', pk], ['state', '=', 'assigned']]]);
        if (mv.length) await kw('stock.move', 'write', [mv, { picked: true }]);
        for (const p of pk) {
          const r = await kw('stock.picking', 'button_validate', [[p]], { context: L.VCTX });
          if (r && r.res_model) throw new Error('wizard ' + r.res_model + ' on ' + day);
        }
        await kw('stock.picking', 'write', [pk, { date_done: sd + ' 08:00:00' }]);
        await kw('stock.move', 'write', [await kw('stock.move', 'search', [[['picking_id', 'in', pk]]]), { date: sd + ' 08:00:00' }]);
      }
      // invoices (one per order)
      const need = (await kw('sale.order', 'read', [sos], { fields: ['invoice_ids'] })).filter(x => !x.invoice_ids.length).map(x => x.id);
      if (need.length) {
        const ctx = { active_model: 'sale.order', active_ids: need };
        const w = await kw('sale.advance.payment.inv', 'create', [{ advance_payment_method: 'delivered', consolidated_billing: false }], { context: ctx });
        await kw('sale.advance.payment.inv', 'create_invoices', [[w]], { context: ctx });
      }
      const invs = await kw('account.move', 'search', [[['line_ids.sale_line_ids.order_id', 'in', sos], ['state', '=', 'draft']]]);
      if (invs.length) {
        await kw('account.move', 'write', [invs, { invoice_date: sd, date: sd }]);
        await kw('account.move', 'action_post', [invs]);
      }
      const offInv = await kw('account.move', 'search', [[['line_ids.sale_line_ids.order_id', 'in', sos.filter(s => meta[s].ch === 'off')], ['payment_state', '=', 'not_paid'], ['state', '=', 'posted']]]);
      if (offInv.length) await L.pay(offInv, ids.J.bca, sd, { group_payment: false });
    }
    total += soIds.length;
    log(`${day}: ${soIds.length} orders done (total ${total})`);
  }
  log('PHASE DONE ' + PHASE);
})().catch(e => { log('ERR ' + e.message + '\n' + (e.debug || '').slice(-1500)); process.exit(1); });
