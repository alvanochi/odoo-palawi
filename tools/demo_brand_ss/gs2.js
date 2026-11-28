// Tidy up the user's "Goreng Sosis" budget and prepare a full purchase -> bill -> payment demo against it.
const { login, kw, CID } = require('./rpc');
const ids = require('./ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
(async () => {
  await login();
  // 1) expense accounts
  const accAlat = await foc('account.account', [['code', '=', '51000030'], ['company_ids', 'in', [CID]]], { code: '51000030', name: 'Biaya Peralatan Produksi', account_type: 'expense_direct_cost', company_ids: [[6, 0, [CID]]] });
  const accBahan = await foc('account.account', [['code', '=', '51000040'], ['company_ids', 'in', [CID]]], { code: '51000040', name: 'Biaya Bahan Baku Langsung', account_type: 'expense_direct_cost', company_ids: [[6, 0, [CID]]] });
  // 2) budgetary positions -> correct accounts
  const posAlat = (await kw('account.budget.post', 'search', [[['name', '=', 'SS - Alat Masak'], ['company_id', '=', CID]]]))[0];
  const posBahan = (await kw('account.budget.post', 'search', [[['name', '=', 'SS - Bahan Baku'], ['company_id', '=', CID]]]))[0];
  await kw('account.budget.post', 'write', [[posAlat], { account_ids: [[6, 0, [accAlat]]] }]);
  await kw('account.budget.post', 'write', [[posBahan], { account_ids: [[6, 0, [accBahan]]] }]);
  // 3) budget: negative planned, period 1 Nov - 31 Dec
  const b = (await kw('crossovered.budget', 'search_read', [[['name', '=', 'Goreng Sosis'], ['company_id', '=', CID]]], { fields: ['crossovered_budget_line'] }))[0];
  await kw('crossovered.budget', 'write', [[b.id], { date_from: '2026-11-01', date_to: '2026-12-31' }]);
  const lines = await kw('crossovered.budget.lines', 'read', [b.crossovered_budget_line], { fields: ['general_budget_id', 'planned_amount'] });
  for (const l of lines) await kw('crossovered.budget.lines', 'write', [[l.id], { date_from: '2026-11-01', date_to: '2026-12-31', planned_amount: -Math.abs(l.planned_amount) }]);
  // 4) supplier + consumable products booked straight to the expense accounts
  const sup = await foc('res.partner', [['name', '=', 'Toko Bahan Makanan Sumber Rejeki'], ['company_id', '=', CID]], { name: 'Toko Bahan Makanan Sumber Rejeki', company_id: CID, is_company: true, supplier_rank: 1, city: 'Jakarta Selatan', country_id: 100 });
  const cat = await foc('product.category', [['name', '=', 'Operasional Dapur'], ['parent_id', '=', ids.C.root]], { name: 'Operasional Dapur', parent_id: ids.C.root });
  const PRODUCTS = [
    ['Sosis Sapi 500 gr', 45000, accBahan], ['Minyak Goreng 2 L', 38000, accBahan], ['Tepung Panir 1 kg', 22000, accBahan],
    ['Wajan Penggorengan 28 cm', 75000, accAlat], ['Spatula Stainless', 20000, accAlat],
  ];
  const P = {};
  for (const [name, price, acc] of PRODUCTS) {
    const t = await foc('product.template', [['name', '=', name], ['company_id', '=', CID]], { name, company_id: CID, type: 'consu', is_storable: false, sale_ok: false, purchase_ok: true, categ_id: cat, standard_price: price });
    await kw('product.template', 'write', [[t], { property_account_expense_id: acc }]);
    await foc('product.supplierinfo', [['product_tmpl_id', '=', t], ['partner_id', '=', sup]], { product_tmpl_id: t, partner_id: sup, price, company_id: CID });
    P[name] = (await kw('product.product', 'search', [[['product_tmpl_id', '=', t]]]))[0];
  }
  // 5) draft purchase request by Budi (Purchasing) against DIV - Produksi
  const budi = (await kw('res.users', 'search', [[['login', '=', 'ss.budi']]]))[0];
  const dept = (await kw('hr.department', 'search', [[['name', '=', 'Produksi'], ['company_id', '=', CID]]]))[0];
  const name = 'Belanja bahan & alat produksi Goreng Sosis';
  let apv = (await kw('x_ss_approval', 'search', [[['x_name', '=', name]]]))[0];
  if (!apv) apv = await kw('x_ss_approval', 'create', [{ x_name: name, x_type: 'pembelian', x_company_id: CID, x_requester_id: budi, x_state: 'draft', x_department_id: dept, x_analytic_id: ids.AN.prod, x_partner_id: sup, x_deadline: '2026-12-02', x_reason: 'Bahan dan alat untuk produksi Goreng Sosis (budget "Goreng Sosis", DIV - Produksi).',
    x_line_ids: [[0, 0, { x_product_id: P['Sosis Sapi 500 gr'], x_qty: 6, x_price: 45000 }], [0, 0, { x_product_id: P['Minyak Goreng 2 L'], x_qty: 2, x_price: 38000 }], [0, 0, { x_product_id: P['Tepung Panir 1 kg'], x_qty: 3, x_price: 22000 }], [0, 0, { x_product_id: P['Wajan Penggorengan 28 cm'], x_qty: 1, x_price: 75000 }], [0, 0, { x_product_id: P['Spatula Stainless'], x_qty: 1, x_price: 20000 }]] }]);
  // verify
  const out = await kw('crossovered.budget.lines', 'read', [b.crossovered_budget_line], { fields: ['general_budget_id', 'analytic_account_id', 'date_from', 'date_to', 'planned_amount', 'practical_amount'] });
  console.log(out.map(l => [l.general_budget_id[1], l.analytic_account_id[1], l.date_from, l.date_to, l.planned_amount, l.practical_amount]));
  console.log('accounts', { accAlat, accBahan }, 'supplier', sup, 'approval draft', apv, 'products', P);
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File') || l.includes('Error')).slice(-4).join(String.fromCharCode(10))); process.exit(1); });
