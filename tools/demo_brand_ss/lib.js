const { kw, CID } = require('./rpc');
const ids = require('./ids.json');
const VCTX = { skip_expired: true, skip_backorder: true, skip_sms: true, skip_scrap_attachment_check: false };

async function variant(tmplKey, codeLike) {
  const d = [['product_tmpl_id', '=', ids.P[tmplKey]]];
  if (codeLike) d.push(['default_code', 'like', codeLike]);
  return (await kw('product.product', 'search', [d], { limit: 1 }))[0];
}
async function variants(tmplKey) {
  return kw('product.product', 'search_read', [[['product_tmpl_id', '=', ids.P[tmplKey]]]], { fields: ['id', 'default_code', 'lst_price', 'display_name'] });
}
async function validatePicking(pid, date) {
  await kw('stock.picking', 'action_assign', [[pid]]);
  const mv = await kw('stock.move', 'search', [[['picking_id', '=', pid], ['state', 'not in', ['done', 'cancel']]]]);
  if (mv.length) await kw('stock.move', 'write', [mv, { picked: true }]);
  const r = await kw('stock.picking', 'button_validate', [[pid]], { context: VCTX });
  if (r && typeof r === 'object' && r.res_model) {
    if (r.res_model === 'stock.backorder.confirmation') {
      const w = await kw(r.res_model, 'create', [{ pick_ids: [[6, 0, [pid]]] }], { context: r.context });
      await kw(r.res_model, 'process_cancel_backorder', [[w]], { context: r.context });
    } else throw new Error('Unhandled wizard ' + r.res_model);
  }
  if (date) {
    await kw('stock.picking', 'write', [[pid], { date_done: date }]);
    const done = await kw('stock.move', 'search', [[['picking_id', '=', pid]]]);
    await kw('stock.move', 'write', [done, { date }]);
  }
}
// validate every open picking chained from an origin, in sequence (pick -> pack -> out / input -> stock)
async function processChain(origin, date, maxSteps = 5) {
  for (let i = 0; i < maxSteps; i++) {
    const p = await kw('stock.picking', 'search', [[['origin', '=', origin], ['company_id', '=', CID], ['state', 'in', ['assigned', 'confirmed', 'waiting']]]], { order: 'id' });
    const ready = [];
    for (const id of p) { const s = (await kw('stock.picking', 'read', [[id]], { fields: ['state'] }))[0].state; if (s === 'assigned') ready.push(id); else { await kw('stock.picking', 'action_assign', [[id]]); const s2 = (await kw('stock.picking', 'read', [[id]], { fields: ['state'] }))[0].state; if (s2 === 'assigned') ready.push(id); } }
    if (!ready.length) return;
    await validatePicking(ready[0], date);
  }
}
async function postInvoice(moveId, date) {
  await kw('account.move', 'write', [[moveId], { invoice_date: date, date }]);
  await kw('account.move', 'action_post', [[moveId]]);
}
async function pay(moveIds, journal, date, opts = {}) {
  const ctx = { active_model: 'account.move', active_ids: moveIds };
  const vals = Object.assign({ journal_id: journal, payment_date: date, group_payment: true }, opts);
  const w = await kw('account.payment.register', 'create', [vals], { context: ctx });
  return kw('account.payment.register', 'action_create_payments', [[w]], { context: ctx });
}
async function lot(productId, name, exp) {
  let l = (await kw('stock.lot', 'search', [[['name', '=', name], ['product_id', '=', productId], ['company_id', '=', CID]]]))[0];
  if (!l) l = await kw('stock.lot', 'create', [Object.assign({ name, product_id: productId, company_id: CID }, exp ? { expiration_date: exp + ' 00:00:00' } : {})]);
  return l;
}
module.exports = { ids, variant, variants, validatePicking, processChain, postInvoice, pay, lot, VCTX };
