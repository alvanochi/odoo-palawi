// Brand SS demo: master data for PT ShellaSaukia (company 13). Idempotent (find-or-create by name).
const { login, kw, CID } = require('./rpc');
const out = {};
async function foc(model, domain, vals, ctx) {
  const r = await kw(model, 'search', [domain], { limit: 1, context: Object.assign({ active_test: false }, ctx || {}) });
  if (r.length) return r[0];
  return kw(model, 'create', [vals], { context: ctx || {} });
}
async function acc(code, name, type) {
  return foc('account.account', [['code', '=', code], ['company_ids', 'in', [CID]]], { code, name, account_type: type, company_ids: [[6, 0, [CID]]] });
}
function ean13(base12) { let s = 0; for (let i = 0; i < 12; i++) s += (+base12[i]) * (i % 2 ? 3 : 1); return base12 + ((10 - s % 10) % 10); }

(async () => {
  await login();
  // ---------- Company settings ----------
  await kw('res.company', 'write', [[CID], { po_double_validation: 'two_step', po_double_validation_amount: 50000000, account_use_credit_limit: true }]);

  // ---------- Accounts ----------
  const A = {};
  A.fg = await acc('11300110', 'Persediaan Barang Jadi', 'asset_current');
  A.rm = await acc('11300120', 'Persediaan Bahan Baku & Kemasan', 'asset_current');
  A.mpRecv = await acc('11220010', 'Piutang Settlement Marketplace', 'asset_current');
  A.adminFee = await acc('61200050', 'Biaya Admin & Layanan Marketplace', 'expense');
  A.ttAds = await acc('61200010', 'Biaya Iklan TikTok Ads', 'expense');
  A.metaAds = await acc('61200020', 'Biaya Iklan Meta Ads', 'expense');
  A.kol = await acc('61200030', 'Biaya KOL & Endorsement', 'expense');
  A.aff = await acc('61200040', 'Komisi Affiliate', 'expense');
  A.live = await acc('61200060', 'Biaya Operasional Live Streaming', 'expense');
  A.event = await acc('61200070', 'Biaya Event & Brand Activation', 'expense');
  A.reject = await acc('51000020', 'Biaya Barang Reject Produksi', 'expense_direct_cost');
  out.A = A;

  // ---------- Journals ----------
  const J = {};
  J.bca = await foc('account.journal', [['code', '=', 'BCA'], ['company_id', '=', CID]], { name: 'Bank BCA Operasional', type: 'bank', code: 'BCA', company_id: CID });
  J.tts = await foc('account.journal', [['code', '=', 'TTS'], ['company_id', '=', CID]], { name: 'Saldo TikTok Shop (Settlement)', type: 'bank', code: 'TTS', company_id: CID });
  J.shp = await foc('account.journal', [['code', '=', 'SHP'], ['company_id', '=', CID]], { name: 'Saldo Shopee (Settlement)', type: 'bank', code: 'SHP', company_id: CID });
  out.J = J;

  // ---------- Analytic plans: Channel & Divisi ----------
  const planCh = await foc('account.analytic.plan', [['name', '=', 'SS - Channel Penjualan']], { name: 'SS - Channel Penjualan' });
  const planDiv = await foc('account.analytic.plan', [['name', '=', 'SS - Divisi']], { name: 'SS - Divisi' });
  const AN = {};
  for (const [k, n] of [['tts', 'TikTok Shop'], ['shp', 'Shopee'], ['live', 'Live Streaming'], ['res', 'Reseller & Distributor'], ['off', 'Offline Store']])
    AN[k] = await foc('account.analytic.account', [['name', '=', 'CH - ' + n], ['company_id', '=', CID]], { name: 'CH - ' + n, plan_id: planCh, company_id: CID });
  for (const [k, n] of [['mkt', 'Digital Marketing'], ['prod', 'Produksi'], ['wh', 'Gudang'], ['ops', 'Operasional Kantor'], ['crea', 'Creative & Media'], ['act', 'Brand Activation'], ['rnd', 'Product Development'], ['hr', 'HR & GA']])
    AN[k] = await foc('account.analytic.account', [['name', '=', 'DIV - ' + n], ['company_id', '=', CID]], { name: 'DIV - ' + n, plan_id: planDiv, company_id: CID });
  out.AN = AN;
  // analytic accounting group for the two demo users
  const [, gAn] = await kw('ir.model.data', 'check_object_reference', ['analytic', 'group_analytic_accounting']);
  await kw('res.users', 'write', [[2, 265], { groups_id: [[4, gAn]] }]);

  // ---------- Warehouses ----------
  const W = {};
  W.main = await foc('stock.warehouse', [['code', '=', 'SSGU'], ['company_id', '=', CID]], { name: 'SS - Gudang Utama Jakarta', code: 'SSGU', company_id: CID, reception_steps: 'two_steps', delivery_steps: 'pick_pack_ship' });
  W.store = await foc('stock.warehouse', [['code', '=', 'SSTK'], ['company_id', '=', CID]], { name: 'SS - Toko Offline Kemang', code: 'SSTK', company_id: CID, reception_steps: 'one_step', delivery_steps: 'ship_only' });
  out.W = W;

  // ---------- Categories (shared model, prefixed) ----------
  const C = {};
  C.root = await foc('product.category', [['name', '=', 'Brand SS'], ['parent_id', '=', false]], { name: 'Brand SS' });
  C.fashion = await foc('product.category', [['name', '=', 'Fashion'], ['parent_id', '=', C.root]], { name: 'Fashion', parent_id: C.root });
  C.beauty = await foc('product.category', [['name', '=', 'Beauty'], ['parent_id', '=', C.root]], { name: 'Beauty', parent_id: C.root });
  C.rm = await foc('product.category', [['name', '=', 'Bahan Baku & Kemasan'], ['parent_id', '=', C.root]], { name: 'Bahan Baku & Kemasan', parent_id: C.root });
  for (const [cat, valAcc] of [[C.root, A.fg], [C.fashion, A.fg], [C.beauty, A.fg], [C.rm, A.rm]])
    await kw('product.category', 'write', [[cat], { property_cost_method: 'average', property_valuation: 'real_time', property_stock_valuation_account_id: valAcc }]);
  out.C = C;

  // ---------- Attributes & tags ----------
  async function attr(name, vals) {
    const a = await foc('product.attribute', [['name', '=', name]], { name, create_variant: 'always', display_type: name.includes('Warna') ? 'color' : 'radio' });
    const ids = {};
    for (const [v, color] of vals) ids[v] = await foc('product.attribute.value', [['name', '=', v], ['attribute_id', '=', a]], Object.assign({ name: v, attribute_id: a }, color ? { html_color: color } : {}));
    return { id: a, v: ids };
  }
  const warna = await attr('Warna (Brand SS)', [['Hitam', '#111111'], ['Navy', '#1f2a44'], ['Mocca', '#a38068'], ['Dusty Pink', '#d8a7a7']]);
  const ukuran = await attr('Ukuran (Brand SS)', [['S'], ['M'], ['L'], ['XL']]);
  const T = {};
  for (const t of ['SS Koleksi Ramadhan 2026', 'SS Koleksi Daily Wear', 'SS Beauty Skincare', 'SS Beauty Makeup', 'SS Bestseller'])
    T[t] = await foc('product.tag', [['name', '=', t]], { name: t });

  // ---------- Products ----------
  const P = {};
  const uom = { unit: 1, m: 6, kg: 13 };
  async function tmpl(key, vals) {
    const base = Object.assign({ company_id: CID, type: 'consu', is_storable: true, sale_ok: true, purchase_ok: true, invoice_policy: 'delivery' }, vals);
    P[key] = await foc('product.template', [['name', '=', vals.name], ['company_id', '=', CID]], base);
    return P[key];
  }
  // raw materials
  const RM = [
    ['kain_wolfis', 'Kain Wolfis Premium', uom.m, 38000],
    ['kain_silk', 'Kain Silk Armani', uom.m, 52000],
    ['label', 'Label, Hangtag & Plastik Packing', uom.unit, 3500],
    ['botol30', 'Botol Kaca Pipet 30ml', uom.unit, 7500],
    ['tube_lip', 'Tube Lip Cream 5ml', uom.unit, 4200],
    ['bottle250', 'Botol Pump 250ml', uom.unit, 6800],
    ['tube100', 'Tube Facial Wash 100ml', uom.unit, 5200],
    ['base_serum', 'Bulk Serum Niacinamide (Maklon)', uom.kg, 950000],
    ['base_lip', 'Bulk Lip Matte Base (Maklon)', uom.kg, 1100000],
    ['base_lotion', 'Bulk Body Lotion Brightening (Maklon)', uom.kg, 180000],
    ['base_wash', 'Bulk Facial Wash Gel (Maklon)', uom.kg, 160000],
  ];
  let bc = 1;
  for (const [k, n, u, cost] of RM) {
    await tmpl(k, { name: n, categ_id: C.rm, uom_id: u, uom_po_id: u, sale_ok: false, list_price: 0, default_code: 'RM-' + String(bc).padStart(3, '0') });
    await kw('product.template', 'write', [[P[k]], { standard_price: cost }]);
    bc++;
  }
  // fashion with variants
  const FASH = [
    ['gamis', 'SS Gamis Syari Premium', 'GMS', 389000, 185000, true, [T['SS Koleksi Ramadhan 2026'], T['SS Bestseller']]],
    ['tunik', 'SS Tunik Daily Kemang', 'TNK', 249000, 112000, true, [T['SS Koleksi Daily Wear']]],
    ['pashmina', 'SS Pashmina Silk Signature', 'PSM', 129000, 52000, false, [T['SS Koleksi Daily Wear'], T['SS Bestseller']]],
  ];
  let seq = 1;
  for (const [k, n, code, price, cost, sized, tags] of FASH) {
    const lines = [[0, 0, { attribute_id: warna.id, value_ids: [[6, 0, Object.values(warna.v)]] }]];
    if (sized) lines.push([0, 0, { attribute_id: ukuran.id, value_ids: [[6, 0, Object.values(ukuran.v)]] }]);
    await tmpl(k, { name: n, categ_id: C.fashion, list_price: price, attribute_line_ids: lines, product_tag_ids: [[6, 0, tags]], purchase_ok: false, default_code: 'SS-' + code });
    const vars = await kw('product.product', 'search_read', [[['product_tmpl_id', '=', P[k]]]], { fields: ['id', 'product_template_attribute_value_ids', 'default_code'] });
    const ptav = await kw('product.template.attribute.value', 'search_read', [[['product_tmpl_id', '=', P[k]]]], { fields: ['id', 'name'] });
    const nm = Object.fromEntries(ptav.map(x => [x.id, x.name]));
    for (const v of vars) {
      const parts = v.product_template_attribute_value_ids.map(i => nm[i]);
      const sku = ['SS', code, ...parts.map(p => p.replace(/\s+/g, '').slice(0, 3).toUpperCase())].join('-');
      await kw('product.product', 'write', [[v.id], { default_code: sku, barcode: ean13('8997' + String(77000000 + seq++).slice(0, 8)), standard_price: cost }]);
    }
  }
  // beauty: lot + expiry
  const BEAU = [
    ['serum', 'SS Glow Serum Niacinamide 30ml', 'SRM', 159000, T['SS Beauty Skincare']],
    ['lip', 'SS Lip Cream Velvet Matte', 'LIP', 89000, T['SS Beauty Makeup']],
    ['lotion', 'SS Body Lotion Brightening 250ml', 'LTN', 119000, T['SS Beauty Skincare']],
    ['wash', 'SS Gentle Facial Wash 100ml', 'FWS', 79000, T['SS Beauty Skincare']],
  ];
  for (const [k, n, code, price, tag] of BEAU) {
    await tmpl(k, { name: n, categ_id: C.beauty, list_price: price, tracking: 'lot', use_expiration_date: true, expiration_time: 730, use_time: 700, removal_time: 670, alert_time: 90, product_tag_ids: [[6, 0, [tag, ...(k === 'serum' ? [T['SS Bestseller']] : [])]]], purchase_ok: false, default_code: 'SS-' + code, barcode: ean13('8997' + String(78000000 + seq++).slice(0, 8)) });
  }
  // service products for marketing bills
  for (const [k, n, a] of [['svc_ttads', 'Jasa Iklan TikTok Ads', A.ttAds], ['svc_meta', 'Jasa Iklan Meta Ads', A.metaAds], ['svc_kol', 'Fee KOL / Endorsement', A.kol], ['svc_aff', 'Komisi Affiliate', A.aff], ['svc_mpfee', 'Biaya Admin Marketplace', A.adminFee]]) {
    P[k] = await foc('product.template', [['name', '=', n], ['company_id', '=', CID]], { name: n, company_id: CID, type: 'service', sale_ok: false, purchase_ok: true });
    await kw('product.template', 'write', [[P[k]], { property_account_expense_id: a }]);
  }
  out.P = P;

  // ---------- BoMs ----------
  async function pid(t) { return (await kw('product.product', 'search', [[['product_tmpl_id', '=', P[t]]]], { limit: 1 }))[0]; }
  const BOMS = [
    ['gamis', [['kain_wolfis', 3.5], ['label', 1]]],
    ['tunik', [['kain_wolfis', 2.0], ['label', 1]]],
    ['pashmina', [['kain_silk', 1.8], ['label', 1]]],
    ['serum', [['botol30', 1], ['base_serum', 0.03], ['label', 1]]],
    ['lip', [['tube_lip', 1], ['base_lip', 0.005], ['label', 1]]],
    ['lotion', [['bottle250', 1], ['base_lotion', 0.25], ['label', 1]]],
    ['wash', [['tube100', 1], ['base_wash', 0.1], ['label', 1]]],
  ];
  for (const [fg, comps] of BOMS) {
    const lines = [];
    for (const [c, q] of comps) lines.push([0, 0, { product_id: await pid(c), product_qty: q }]);
    await foc('mrp.bom', [['product_tmpl_id', '=', P[fg]], ['company_id', '=', CID]], { product_tmpl_id: P[fg], product_qty: 1, type: 'normal', company_id: CID, bom_line_ids: lines, produce_delay: fg === 'gamis' ? 7 : 3 });
  }

  // ---------- Pricelists ----------
  const PL = {};
  PL.res = await foc('product.pricelist', [['name', '=', 'Harga Reseller (-25%)'], ['company_id', '=', CID]], { name: 'Harga Reseller (-25%)', company_id: CID, currency_id: 12, item_ids: [[0, 0, { applied_on: '3_global', compute_price: 'percentage', percent_price: 25 }]] });
  PL.dist = await foc('product.pricelist', [['name', '=', 'Harga Distributor (-35%)'], ['company_id', '=', CID]], { name: 'Harga Distributor (-35%)', company_id: CID, currency_id: 12, item_ids: [[0, 0, { applied_on: '3_global', compute_price: 'percentage', percent_price: 35 }]] });
  out.PL = PL;

  // ---------- Partners ----------
  const R = {};
  async function partner(k, vals) { R[k] = await foc('res.partner', [['name', '=', vals.name], ['company_id', '=', CID]], Object.assign({ company_id: CID, is_company: true, country_id: 100 }, vals)); }
  await partner('sup_tekstil', { name: 'CV Tekstil Bandung Jaya', city: 'Bandung', supplier_rank: 1, phone: '022-7300111' });
  await partner('sup_kemasan', { name: 'PT Kemasan Prima Indonesia', city: 'Tangerang', supplier_rank: 1 });
  await partner('sup_maklon', { name: 'PT Maklon Kosmetik Nusantara', city: 'Bekasi', supplier_rank: 1 });
  await partner('sup_tiktok', { name: 'TikTok Pte. Ltd. (Ads)', supplier_rank: 1 });
  await partner('sup_meta', { name: 'Meta Platforms Ireland (Ads)', supplier_rank: 1 });
  await partner('mp_tts', { name: 'TikTok Shop - SS Official', customer_rank: 1, comment: 'Akun toko marketplace (dummy). Settlement ke jurnal Saldo TikTok Shop.' });
  await partner('mp_shp', { name: 'Shopee - SS Official Store', customer_rank: 1, comment: 'Akun toko marketplace (dummy). Settlement ke jurnal Saldo Shopee.' });
  await partner('res_aisyah', { name: 'Butik Aisyah Bandung (Reseller)', city: 'Bandung', customer_rank: 1, property_product_pricelist: PL.res, credit_limit: 50000000 });
  await partner('res_medan', { name: 'Toko Hijab Medan Indah (Reseller)', city: 'Medan', customer_rank: 1, property_product_pricelist: PL.res, credit_limit: 40000000 });
  await partner('dist_sby', { name: 'CV Berkah Distribusi Surabaya (Distributor)', city: 'Surabaya', customer_rank: 1, property_product_pricelist: PL.dist, credit_limit: 250000000 });
  await partner('walkin', { name: 'Pelanggan Toko Kemang (Walk-in)', is_company: false, customer_rank: 1 });
  for (const k of ['res_aisyah', 'res_medan', 'dist_sby']) await kw('res.partner', 'write', [[R[k]], { property_product_pricelist: k === 'dist_sby' ? PL.dist : PL.res }]);
  out.R = R;

  // ---------- Sales teams (channels) ----------
  const TM = {};
  for (const [k, n, tgt] of [['tts', 'TikTok Shop', 250000000], ['shp', 'Shopee', 180000000], ['res', 'Reseller & Distributor', 120000000], ['off', 'Offline Store Kemang', 60000000]])
    TM[k] = await foc('crm.team', [['name', '=', 'SS - ' + n], ['company_id', '=', CID]], { name: 'SS - ' + n, company_id: CID, invoiced_target: tgt, user_id: 265, member_ids: [[6, 0, [265, 2]]] });
  out.TM = TM;

  // ---------- Departments & employees ----------
  const D = {};
  const DEPTS = ['Direksi', 'HR & General Affairs', 'Finance & Accounting', 'Tax', 'Purchasing & Procurement', 'Produksi', 'Gudang & Inventory', 'Marketplace & E-Commerce', 'Sales & Live Streaming', 'Digital Marketing, KOL & Affiliate', 'Creative & Media', 'Brand Activation & Partnership', 'Product Development', 'Offline Retail', 'Reseller & Distributor', 'Customer Experience', 'Legal & Business Development'];
  for (const d of DEPTS) D[d] = await foc('hr.department', [['name', '=', d], ['company_id', '=', CID]], { name: d, company_id: CID });
  const EMP = [
    ['Shella Saukia', 'Direksi', 'CEO / Owner', null],
    ['Rina Kartika', 'HR & General Affairs', 'HR & GA Manager', 'Shella Saukia'],
    ['Dewi Anggraini', 'Finance & Accounting', 'Finance Manager', 'Shella Saukia'],
    ['Agus Prasetyo', 'Tax', 'Tax Officer', 'Dewi Anggraini'],
    ['Budi Santoso', 'Purchasing & Procurement', 'Purchasing Supervisor', 'Dewi Anggraini'],
    ['Hendra Wijaya', 'Produksi', 'Production Manager', 'Shella Saukia'],
    ['Siti Nurhaliza', 'Produksi', 'QC Officer', 'Hendra Wijaya'],
    ['Joko Susilo', 'Gudang & Inventory', 'Kepala Gudang', 'Hendra Wijaya'],
    ['Andi Saputra', 'Gudang & Inventory', 'Staff Picking & Packing', 'Joko Susilo'],
    ['Maya Puspita', 'Marketplace & E-Commerce', 'Marketplace Manager', 'Shella Saukia'],
    ['Nadia Putri', 'Sales & Live Streaming', 'Host Live Streaming', 'Maya Puspita'],
    ['Citra Lestari', 'Sales & Live Streaming', 'Host Live Streaming', 'Maya Puspita'],
    ['Fajar Ramadhan', 'Sales & Live Streaming', 'Host Live Streaming', 'Maya Puspita'],
    ['Intan Permata', 'Sales & Live Streaming', 'Host Live Streaming', 'Maya Puspita'],
    ['Reza Firmansyah', 'Digital Marketing, KOL & Affiliate', 'Digital Marketing Lead', 'Shella Saukia'],
    ['Laras Wulandari', 'Creative & Media', 'Creative Lead', 'Reza Firmansyah'],
    ['Dimas Pratama', 'Creative & Media', 'Video Editor', 'Laras Wulandari'],
    ['Yuni Astuti', 'Product Development', 'R&D Formulator', 'Shella Saukia'],
    ['Eko Kurniawan', 'Offline Retail', 'Store Supervisor Kemang', 'Maya Puspita'],
    ['Wulan Sari', 'Reseller & Distributor', 'B2B Account Manager', 'Maya Puspita'],
    ['Putri Ayu', 'Customer Experience', 'CS Lead', 'Maya Puspita'],
    ['Taufik Hidayat', 'Legal & Business Development', 'Legal Officer', 'Shella Saukia'],
  ];
  const E = {};
  for (const [n, d, job] of EMP) E[n] = await foc('hr.employee', [['name', '=', n], ['company_id', '=', CID]], { name: n, department_id: D[d], job_title: job, company_id: CID });
  for (const [n, , , mgr] of EMP) if (mgr) await kw('hr.employee', 'write', [[E[n]], { parent_id: E[mgr], coach_id: E[mgr] }]);
  for (const [n, d] of EMP) if (['Direksi'].includes(d) || /Manager|Lead|Kepala|Supervisor/.test(EMP.find(e => e[0] === n)[2])) await kw('hr.department', 'write', [[D[d]], { manager_id: E[n] }]);
  out.D = D; out.E = E;

  require('fs').writeFileSync('ids.json', JSON.stringify(out, null, 1));
  console.log('OK', JSON.stringify({ products: Object.keys(P).length, employees: Object.keys(E).length }));
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-2000)); process.exit(1); });
