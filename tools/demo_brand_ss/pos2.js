// POS demo: one closed session (yesterday) + one open session (today) with orders, as user Eko.
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const CFG = 6;
const STEP = process.argv[2] || 'all';
(async () => {
  await login();
  await kw('pos.config', 'write', [[CFG], { crm_team_id: ids.TM.off }]);
  const cfg = (await kw('pos.config', 'read', [[CFG]], { fields: ['pricelist_id', 'payment_method_ids', 'current_session_id'] }))[0];
  const pms = await kw('pos.payment.method', 'read', [cfg.payment_method_ids], { fields: ['name', 'is_cash_count'] });
  const cash = pms.find(p => p.is_cash_count).id, qris = pms.find(p => !p.is_cash_count).id;
  const pool = [...await L.variants('pashmina'), ...(await L.variants('gamis')).slice(0, 6), ...(await L.variants('tunik')).slice(0, 4), ...await L.variants('serum'), ...await L.variants('lip'), ...await L.variants('wash')];
  const taxOf = {};
  for (const p of pool) taxOf[p.id] = (await kw('product.product', 'read', [[p.id]], { fields: ['taxes_id'] }))[0].taxes_id;
  let seed = 5; const r = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };

  async function order(session, when) {
    const n = 1 + Math.floor(r() * 3); const lines = []; let untaxed = 0, total = 0;
    const used = new Set();
    for (let i = 0; i < n; i++) {
      const p = pool[Math.floor(r() * pool.length)]; if (used.has(p.id)) continue; used.add(p.id);
      const qty = 1 + Math.floor(r() * 2);
      const ca = await kw('account.tax', 'compute_all', [taxOf[p.id], p.lst_price], { quantity: qty });
      lines.push([0, 0, { product_id: p.id, full_product_name: p.display_name, qty, price_unit: p.lst_price, price_subtotal: ca.total_excluded, price_subtotal_incl: ca.total_included, tax_ids: [[6, 0, taxOf[p.id]]], discount: 0 }]);
      untaxed += ca.total_excluded; total += ca.total_included;
    }
    total = Math.round(total);
    let oid = await kw('pos.order', 'create', [{ session_id: session, company_id: CID, pricelist_id: cfg.pricelist_id[0], lines, amount_tax: total - untaxed, amount_total: total, amount_paid: 0, amount_return: 0, date_order: when, user_id: 273, pos_reference: 'Order ' + String(session).padStart(5, '0') + '-001-' + String(Date.now() % 100000).padStart(5, '0') + Math.floor(r() * 90 + 10), crm_team_id: ids.TM.off }]);
    if (Array.isArray(oid)) oid = oid[0];
    if (!oid) throw new Error('pos.order create returned ' + JSON.stringify(oid));
    const pm = r() < 0.55 ? qris : cash;
    await kw('pos.payment', 'create', [{ pos_order_id: oid, amount: total, payment_method_id: pm, session_id: session, payment_date: when }]);
    await kw('pos.order', 'write', [[oid], { amount_paid: total }]);
    await kw('pos.order', 'action_pos_order_paid', [[oid]]);
    return [oid, total, pm === cash];
  }
  async function newSession(openAt) {
    const s = await kw('pos.session', 'create', [{ config_id: CFG, user_id: 273 }]);
    await kw('pos.session', 'set_opening_control', [[s], 500000, 'Modal kas awal Rp500.000']).catch(e => console.log('opening', e.message));
    await kw('pos.session', 'write', [[s], { start_at: openAt }]).catch(() => {});
    return s;
  }
  if ((STEP === 'all' || STEP === 'closed') && !(await kw('pos.session', 'search_count', [[['config_id', '=', CFG], ['state', '=', 'closed']]]))) {
    const s = cfg.current_session_id ? cfg.current_session_id[0] : await newSession('2026-11-17 02:00:00');
    let cashIn = 0;
    const have = await kw('pos.order', 'search_count', [[['session_id', '=', s]]]);
    for (let i = have; i < 9; i++) { const [, t, isCash] = await order(s, `2026-11-17 ${String(3 + i).padStart(2, '0')}:${String(10 + i * 4).padStart(2, '0')}:00`); if (isCash) cashIn += t; }
    await kw('pos.session', 'post_closing_cash_details', [[s], 500000 + cashIn]).catch(e => console.log('cash details', e.message));
    const res = await kw('pos.session', 'close_session_from_ui', [[s]]).catch(e => ({ err: e.message, dbg: (e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File')).slice(-4).join(' | ') }));
    console.log('close yesterday', JSON.stringify(res).slice(0, 400));
    await kw('pos.session', 'write', [[s], { start_at: '2026-11-17 02:00:00', stop_at: '2026-11-17 14:00:00' }]).catch(() => {});
  }
  if (STEP === 'all' || STEP === 'open') {
    const cur = (await kw('pos.config', 'read', [[CFG]], { fields: ['current_session_id'] }))[0].current_session_id;
    const s = cur ? cur[0] : await newSession('2026-11-18 02:00:00');
    if (!(await kw('pos.order', 'search_count', [[['session_id', '=', s]]]))) for (let i = 0; i < 5; i++) await order(s, `2026-11-18 ${String(3 + i * 2).padStart(2, '0')}:15:00`);
    console.log('open session', s, (await kw('pos.session', 'read', [[s]], { fields: ['name', 'state', 'order_count'] }))[0]);
  }
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File')).slice(-6).join(String.fromCharCode(10))); process.exit(1); });
