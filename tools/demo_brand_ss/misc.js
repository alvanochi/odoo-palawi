// Tax (PPh 23), tax calendar, reorder rules, store stock request, fixed assets
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const STEP = process.argv[2] || 'all';
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function acc(code) { return (await kw('account.account', 'search', [[['code', '=', code], ['company_ids', 'in', [CID]]]]))[0]; }
async function ref(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
const has = s => STEP === 'all' || STEP.split(',').includes(s);

(async () => {
  await login();
  if (has('tax')) {
    const grp = (await kw('account.tax', 'read', [[(await kw('account.tax', 'search', [[['company_id', '=', CID], ['type_tax_use', '=', 'purchase']]], { limit: 1 }))[0]]], { fields: ['tax_group_id'] }))[0].tax_group_id[0];
    async function wht(name, amount, code) {
      let t = (await kw('account.tax', 'search', [[['name', '=', name], ['company_id', '=', CID]]]))[0];
      if (!t) t = await kw('account.tax', 'create', [{ name, amount: -amount, amount_type: 'percent', type_tax_use: 'purchase', company_id: CID, country_id: 100, tax_group_id: grp, description: name }]);
      const a = await acc(code);
      const rl = await kw('account.tax.repartition.line', 'search', [[['tax_id', '=', t], ['repartition_type', '=', 'tax']]]);
      await kw('account.tax.repartition.line', 'write', [rl, { account_id: a }]);
      return t;
    }
    const pph23 = await wht('PPh 23 Jasa (2%)', 2, '21210020');
    await wht('PPh 4(2) Sewa Bangunan (10%)', 10, '21210040');
    await kw('product.template', 'write', [[ids.P.svc_kol, ids.P.svc_aff], { supplier_taxes_id: [[6, 0, [pph23]]] }]);
    // apply PPh 23 on unpaid KOL bills
    const bills = await kw('account.move', 'search_read', [[['company_id', '=', CID], ['move_type', '=', 'in_invoice'], ['ref', 'like', 'KOL-'], ['payment_state', '=', 'not_paid']]], { fields: ['name', 'invoice_line_ids'] });
    for (const b of bills) {
      await kw('account.move', 'button_draft', [[b.id]]);
      await kw('account.move.line', 'write', [b.invoice_line_ids, { tax_ids: [[6, 0, [pph23]]] }]);
      await kw('account.move', 'action_post', [[b.id]]);
      console.log('PPh23 on', b.name);
    }
    // company NPWP (dummy) for e-Faktur demo
    await kw('res.company', 'write', [[CID], { vat: '0012345678901000' }]).catch(e => console.log('vat', e.message));
    // tax calendar project
    const p = await foc('project.project', [['name', '=', 'SS - Kalender & Kewajiban Pajak'], ['company_id', '=', CID]], { name: 'SS - Kalender & Kewajiban Pajak', company_id: CID, user_id: 268, color: 3, description: 'Pengingat jadwal setor & lapor pajak. Data transaksi pajak diambil dari Accounting.' });
    const st = {}; let seq = 1;
    for (const s of ['Akan Jatuh Tempo', 'Disiapkan', 'Sudah Disetor / Dilapor']) { let id = (await kw('project.task.type', 'search', [[['name', '=', s], ['project_ids', 'in', [p]]]]))[0]; if (!id) id = await kw('project.task.type', 'create', [{ name: s, sequence: seq, project_ids: [[6, 0, [p]]], fold: s.startsWith('Sudah') }]); st[s] = id; seq++; }
    const T = [
      ['Setor BPJS Ketenagakerjaan & Kesehatan - Oktober', 'Sudah Disetor / Dilapor', '2026-11-10 10:00:00', 'Akun 25110110 (dari payroll Oktober).'],
      ['Setor PPh 21 masa Oktober', 'Sudah Disetor / Dilapor', '2026-11-15 10:00:00', 'Dari slip gaji Oktober (akun 21210010).'],
      ['Lapor SPT Masa PPh 21/26 Oktober', 'Disiapkan', '2026-11-20 10:00:00', 'Lampirkan bukti potong dari payroll.'],
      ['Lapor SPT Masa PPN Oktober (Coretax)', 'Disiapkan', '2026-11-30 10:00:00', 'Rekap PPN keluaran vs masukan dari jurnal VAT Sales / VAT Purchase.'],
      ['Setor PPh 23 masa November (fee KOL)', 'Akan Jatuh Tempo', '2026-12-15 10:00:00', 'Akun 21210020 - dipotong otomatis di tagihan KOL.'],
      ['Setor PPh 4(2) sewa toko Kemang - November', 'Akan Jatuh Tempo', '2026-12-15 10:00:00', ''],
      ['Upload e-Faktur keluaran November', 'Akan Jatuh Tempo', '2026-12-15 10:00:00', 'Export dari invoice pelanggan (l10n_id e-Faktur / Coretax).'],
    ];
    for (const [n, s, d, desc] of T) if (!(await kw('project.task', 'search_count', [[['name', '=', n], ['project_id', '=', p]]]))) await kw('project.task', 'create', [{ name: n, project_id: p, stage_id: st[s], date_deadline: d, description: desc, user_ids: [[6, 0, [268]]], company_id: CID }]);
    console.log('tax ok');
  }
  if (has('reorder')) {
    const buy = await ref('purchase_stock.route_warehouse0_buy');
    const mfg = await ref('mrp.route_warehouse0_manufacture');
    const loc = (await kw('stock.warehouse', 'read', [[ids.W.main]], { fields: ['lot_stock_id'] }))[0].lot_stock_id[0];
    const SUP = { kain_wolfis: ['sup_tekstil', 38000, 14], kain_silk: ['sup_tekstil', 51000, 14], label: ['sup_kemasan', 3400, 7], botol30: ['sup_kemasan', 7400, 10], tube_lip: ['sup_kemasan', 4200, 10], bottle250: ['sup_kemasan', 6800, 10], tube100: ['sup_kemasan', 5200, 10], base_serum: ['sup_maklon', 950000, 21], base_lip: ['sup_maklon', 1100000, 21], base_lotion: ['sup_maklon', 180000, 21], base_wash: ['sup_maklon', 160000, 21] };
    for (const [k, [s, price, delay]] of Object.entries(SUP)) {
      await foc('product.supplierinfo', [['product_tmpl_id', '=', ids.P[k]], ['partner_id', '=', ids.R[s]]], { product_tmpl_id: ids.P[k], partner_id: ids.R[s], price, delay, min_qty: 1, company_id: CID });
      await kw('product.template', 'write', [[ids.P[k]], { route_ids: [[6, 0, [buy]]] }]);
    }
    const OP = [['kain_wolfis', 1500, 3000, buy], ['kain_silk', 400, 800, buy], ['label', 2000, 5000, buy], ['botol30', 800, 2000, buy], ['base_serum', 25, 60, buy], ['base_lip', 5, 15, buy], ['bottle250', 300, 1000, buy]];
    const fgOP = [['serum', 400, 1000], ['lip', 300, 800], ['lotion', 250, 600], ['wash', 250, 600]];
    let n = 0;
    for (const [k, mn, mx, route] of OP) { const p = await L.variant(k); if (!(await kw('stock.warehouse.orderpoint', 'search_count', [[['product_id', '=', p], ['location_id', '=', loc]]]))) { await kw('stock.warehouse.orderpoint', 'create', [{ product_id: p, location_id: loc, warehouse_id: ids.W.main, product_min_qty: mn, product_max_qty: mx, route_id: route, trigger: 'manual', company_id: CID }]); n++; } }
    for (const [k, mn, mx] of fgOP) { const p = await L.variant(k); await kw('product.template', 'write', [[ids.P[k]], { route_ids: [[6, 0, [mfg]]] }]); if (!(await kw('stock.warehouse.orderpoint', 'search_count', [[['product_id', '=', p], ['location_id', '=', loc]]]))) { await kw('stock.warehouse.orderpoint', 'create', [{ product_id: p, location_id: loc, warehouse_id: ids.W.main, product_min_qty: mn, product_max_qty: mx, route_id: mfg, trigger: 'manual', company_id: CID }]); n++; } }
    // fashion bestseller variants (pashmina) min stock
    for (const v of await L.variants('pashmina')) { if (!(await kw('stock.warehouse.orderpoint', 'search_count', [[['product_id', '=', v.id], ['location_id', '=', loc]]]))) { await kw('stock.warehouse.orderpoint', 'create', [{ product_id: v.id, location_id: loc, warehouse_id: ids.W.main, product_min_qty: 60, product_max_qty: 200, route_id: mfg, trigger: 'manual', company_id: CID }]); n++; } }
    await kw('product.template', 'write', [[ids.P.pashmina, ids.P.gamis, ids.P.tunik], { route_ids: [[6, 0, [mfg]]] }]);
    console.log('orderpoints', n);
  }
  if (has('transfer')) {
    const wh = await kw('stock.warehouse', 'read', [[ids.W.main, ids.W.store]], { fields: ['lot_stock_id', 'int_type_id'] });
    const src = wh[0].lot_stock_id[0], dst = wh[1].lot_stock_id[0], pt = wh[0].int_type_id[0];
    async function req(origin, date, lines, done) {
      if (await kw('stock.picking', 'search_count', [[['origin', '=', origin]]])) return;
      const mv = [];
      for (const [k, code, q] of lines) { const p = await L.variant(k, code); mv.push([0, 0, { product_id: p, product_uom_qty: q, location_id: src, location_dest_id: dst, name: 'Restock toko' }]); }
      const id = await kw('stock.picking', 'create', [{ picking_type_id: pt, location_id: src, location_dest_id: dst, origin, scheduled_date: date + ' 02:00:00', move_ids: mv, company_id: CID, note: 'Permintaan stok dari Toko Kemang (Eko Kurniawan).' }]);
      await kw('stock.picking', 'action_confirm', [[id]]); await kw('stock.picking', 'action_assign', [[id]]);
      if (done) await L.validatePicking(id, date + ' 06:00:00');
      console.log('transfer', origin);
    }
    await req('REQ-TOKO-KEMANG-2026-11-10', '2026-11-10', [['gamis', 'HIT-M', 6], ['gamis', 'NAV-L', 4], ['pashmina', 'MOC', 10], ['serum', null, 20]], true);
    await req('REQ-TOKO-KEMANG-2026-11-18', '2026-11-18', [['pashmina', 'NAV', 12], ['pashmina', 'DUS', 12], ['lip', null, 24], ['tunik', 'MOC-M', 6], ['gamis', 'DUS-M', 6]], false);
  }
  if (has('asset')) {
    const MISC = (await kw('account.journal', 'search', [[['code', '=', 'MISC'], ['company_id', '=', CID]]]))[0];
    const cat = await foc('account.asset.category', [['name', '=', 'SS - Peralatan Kantor, Gudang & Studio'], ['company_id', '=', CID]], { name: 'SS - Peralatan Kantor, Gudang & Studio', company_id: CID, account_asset_id: await acc('12210030'), account_depreciation_id: await acc('12281030'), account_depreciation_expense_id: await acc('67100030'), journal_id: MISC, method: 'linear', method_number: 48, method_period: 1, method_time: 'number', type: 'purchase', date_first_depreciation: 'last_day_period' });
    const AS = [['Kamera, lighting & mic studio live streaming', 45000000, '2026-07-01'], ['Rak gudang heavy duty (40 unit)', 60000000, '2026-06-01'], ['Laptop editing video (2 unit)', 28000000, '2026-08-15'], ['Printer label barcode + 2 scanner gudang (APV/2026/0005)', 4500000, '2026-11-14']];
    for (const [n, v, d] of AS) {
      if (await kw('account.asset.asset', 'search_count', [[['name', '=', n]]])) continue;
      const a = await kw('account.asset.asset', 'create', [{ name: n, value: v, date: d, category_id: cat, company_id: CID, currency_id: 12, method: 'linear', method_number: 48, method_period: 1, method_time: 'number', type: 'purchase', date_first_depreciation: 'last_day_period' }]);
      await kw('account.asset.asset', 'compute_depreciation_board', [[a]]).catch(e => console.log('board', e.message));
      await kw('account.asset.asset', 'validate', [[a]]).catch(e => console.log('validate', e.message));
      // post depreciation lines up to Oct 2026
      const lines = await kw('account.asset.depreciation.line', 'search_read', [[['asset_id', '=', a], ['depreciation_date', '<=', '2026-10-31'], ['move_check', '=', false]]], { fields: ['id'] }).catch(() => []);
      if (lines.length) await kw('account.asset.depreciation.line', 'create_move', [lines.map(l => l.id)]).catch(e => console.log('dep move', e.message));
      console.log('asset', n);
    }
  }
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File')).slice(-6).join(String.fromCharCode(10))); process.exit(1); });
