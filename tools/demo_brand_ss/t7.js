// Marketing spend, operating expenses, budget, projects, HR attendance (company 13)
const { login, kw, CID } = require('./rpc');
const L = require('./lib');
const { ids } = L;
const STEP = process.argv[2] || 'all';
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
const an = k => ({ [String(ids.AN[k])]: 100 });

async function bill(partner, date, lines, ref, payDate) {
  const ex = await kw('account.move', 'search', [[['ref', '=', ref], ['company_id', '=', CID]]]);
  if (ex.length) return ex[0];
  const id = await kw('account.move', 'create', [{ move_type: 'in_invoice', partner_id: partner, ref, invoice_date: date, date, company_id: CID, journal_id: undefined,
    invoice_line_ids: lines.map(([name, acc, amt, ank]) => [0, 0, { name, account_id: acc, price_unit: amt, quantity: 1, tax_ids: [[6, 0, []]], analytic_distribution: an(ank) }]) }].map(v => { delete v.journal_id; return v; }));
  await kw('account.move', 'action_post', [[id]]);
  if (payDate) await L.pay([id], ids.J.bca, payDate);
  return id;
}

(async () => {
  await login();
  const A = ids.A;
  if (STEP === 'all' || STEP === 'exp') {
    const kols = {};
    for (const n of ['KOL - @nadyahijabstyle (Nadya)', 'KOL - @glowwithkirana (Kirana)', 'KOL - @dailyoutfit.ayu (Ayu)', 'Affiliate Network - TikTok Affiliate'])
      kols[n] = await foc('res.partner', [['name', '=', n], ['company_id', '=', CID]], { name: n, company_id: CID, supplier_rank: 1, comment: 'Data KOL/affiliate (dummy)' });
    const landlord = await foc('res.partner', [['name', '=', 'PT Kemang Square Properti'], ['company_id', '=', CID]], { name: 'PT Kemang Square Properti', company_id: CID, supplier_rank: 1, is_company: true });
    // TikTok Ads weekly, Meta monthly, KOL, affiliate, rent
    const weeks = ['2026-09-21', '2026-09-28', '2026-10-05', '2026-10-12', '2026-10-19', '2026-10-26', '2026-11-02', '2026-11-09', '2026-11-16'];
    const tt = [2600000, 2800000, 2900000, 3400000, 3100000, 3000000, 3600000, 5200000, 4900000];
    for (let i = 0; i < weeks.length; i++)
      await bill(ids.R.sup_tiktok, weeks[i], [['TikTok Ads - top up saldo iklan minggu ' + weeks[i], A.ttAds, tt[i], 'mkt']], 'TTADS-' + weeks[i], i < 8 ? weeks[i] : false);
    for (const [d, amt] of [['2026-09-30', 3800000], ['2026-10-31', 4200000], ['2026-11-15', 3900000]])
      await bill(ids.R.sup_meta, d, [['Meta Ads (Instagram & Facebook) periode s/d ' + d, A.metaAds, amt, 'mkt']], 'META-' + d, d < '2026-11-01' ? d : false);
    const kolBills = [['KOL - @nadyahijabstyle (Nadya)', '2026-09-28', 3500000], ['KOL - @glowwithkirana (Kirana)', '2026-10-09', 4500000], ['KOL - @dailyoutfit.ayu (Ayu)', '2026-10-24', 2500000], ['KOL - @glowwithkirana (Kirana)', '2026-11-08', 5000000], ['KOL - @nadyahijabstyle (Nadya)', '2026-11-10', 3500000]];
    for (const [k, d, amt] of kolBills) await bill(kols[k], d, [['Fee endorsement / video review ' + d, A.kol, amt, 'mkt']], 'KOL-' + k.slice(6, 14) + '-' + d, d < '2026-11-05' ? d : false);
    for (const [d, amt] of [['2026-09-30', 1450000], ['2026-10-31', 2380000]])
      await bill(kols['Affiliate Network - TikTok Affiliate'], d, [['Komisi affiliate TikTok s/d ' + d, A.aff, amt, 'mkt']], 'AFF-' + d, d);
    const rent = (await kw('account.account', 'search', [[['code', '=', '65110040'], ['company_ids', 'in', [CID]]]]))[0];
    for (const d of ['2026-09-01', '2026-10-01', '2026-11-01'])
      await bill(landlord, d, [['Sewa toko Kemang bulan ' + d.slice(0, 7), rent, 15000000, 'ops']], 'SEWA-' + d, d);
    // monthly salary journal entries
    const sal = (await kw('account.account', 'search', [[['code', '=', '61100010'], ['company_ids', 'in', [CID]]]]))[0];
    for (const d of ['2026-09-28', '2026-10-28']) {
      const ref = 'GAJI-' + d;
      if (!(await kw('account.move', 'search_count', [[['ref', '=', ref], ['company_id', '=', CID]]]))) {
        const m = await kw('account.move', 'create', [{ move_type: 'entry', ref, date: d, journal_id: ids.J.bca, company_id: CID, line_ids: [
          [0, 0, { name: 'Gaji karyawan ' + d.slice(0, 7), account_id: sal, debit: 118000000, analytic_distribution: an('hr') }],
          [0, 0, { name: 'Pembayaran gaji ' + d.slice(0, 7), account_id: (await kw('account.journal', 'read', [[ids.J.bca]], { fields: ['default_account_id'] }))[0].default_account_id[0], credit: 118000000 }]] }]);
        await kw('account.move', 'action_post', [[m]]);
      }
    }
    console.log('expenses ok');
  }
  if (STEP === 'all' || STEP === 'budget') {
    const posMkt = await foc('account.budget.post', [['name', '=', 'SS - Biaya Marketing & Iklan'], ['company_id', '=', CID]], { name: 'SS - Biaya Marketing & Iklan', company_id: CID, account_ids: [[6, 0, [A.ttAds, A.metaAds, A.kol, A.aff]]] });
    const posOps = await foc('account.budget.post', [['name', '=', 'SS - Biaya Operasional Toko'], ['company_id', '=', CID]], { name: 'SS - Biaya Operasional Toko', company_id: CID, account_ids: [[6, 0, await kw('account.account', 'search', [[['code', 'in', ['65110040', '63110080', '63110060']], ['company_ids', 'in', [CID]]]])]] });
    const ex = await kw('crossovered.budget', 'search', [[['name', '=', 'Budget Q4 2026 - Brand SS'], ['company_id', '=', CID]]]);
    if (!ex.length) {
      const lines = [];
      for (const [f, t, mkt, ops] of [['2026-09-01', '2026-09-30', 18000000, 16000000], ['2026-10-01', '2026-10-31', 22000000, 16000000], ['2026-11-01', '2026-11-30', 22000000, 16000000], ['2026-12-01', '2026-12-31', 35000000, 16000000]]) {
        lines.push([0, 0, { general_budget_id: posMkt, analytic_account_id: ids.AN.mkt, date_from: f, date_to: t, planned_amount: -mkt }]);
        lines.push([0, 0, { general_budget_id: posOps, analytic_account_id: ids.AN.ops, date_from: f, date_to: t, planned_amount: -ops }]);
      }
      const b = await kw('crossovered.budget', 'create', [{ name: 'Budget Q4 2026 - Brand SS', company_id: CID, date_from: '2026-09-01', date_to: '2026-12-31', user_id: 2, crossovered_budget_line: lines }]);
      for (const m of ['action_budget_confirm', 'action_budget_validate']) await kw('crossovered.budget', m, [[b]]).catch(e => console.log(m, e.message));
    }
    console.log('budget ok');
  }
  if (STEP === 'all' || STEP === 'project') {
    async function project(name, stages, tasks, color) {
      const p = await foc('project.project', [['name', '=', name], ['company_id', '=', CID]], { name, company_id: CID, user_id: 265, color, privacy_visibility: 'employees' });
      const st = {};
      let seq = 1;
      for (const s of stages) {
        let id = (await kw('project.task.type', 'search', [[['name', '=', s], ['project_ids', 'in', [p]]]]))[0];
        if (!id) id = await kw('project.task.type', 'create', [{ name: s, sequence: seq, project_ids: [[6, 0, [p]]], fold: /Selesai|Done|Launching$/.test(s) }]);
        st[s] = id; seq++;
      }
      for (const [tn, stage, deadline, prio, desc, tags] of tasks) {
        if (await kw('project.task', 'search_count', [[['name', '=', tn], ['project_id', '=', p]]])) continue;
        await kw('project.task', 'create', [{ name: tn, project_id: p, stage_id: st[stage], date_deadline: deadline, priority: prio ? '1' : '0', description: desc || false, user_ids: [[6, 0, [265]]], company_id: CID }]);
      }
      return p;
    }
    await project('SS - Creative Request (Desain & Konten)', ['Request Masuk', 'Briefing', 'Produksi Konten', 'Review / Approval', 'Revisi', 'Selesai'], [
      ['Banner campaign 12.12 (TikTok Shop & Shopee)', 'Produksi Konten', '2026-11-25', true, 'PIC: Laras. Requester: Maya (Marketplace).'],
      ['Video review SS Glow Serum - 5 varian hook', 'Review / Approval', '2026-11-19', true, 'PIC: Dimas. Approval: Reza.'],
      ['Foto katalog Gamis Syari Premium warna Dusty Pink', 'Revisi', '2026-11-14', false, 'Revisi ke-2: tone warna kurang sesuai. TERLAMBAT.'],
      ['Konten live streaming backdrop Desember', 'Briefing', '2026-11-28', false],
      ['Desain kemasan Lip Cream shade baru', 'Request Masuk', '2026-12-05', false, 'Requester: Product Development'],
      ['Feed IG minggu ke-3 November', 'Selesai', '2026-11-15', false],
      ['Thumbnail live 11.11', 'Selesai', '2026-11-09', true],
    ], 4);
    await project('SS - Product Development', ['Ide & Riset', 'Formulasi', 'Sampel & Revisi', 'Uji Stabilitas & Notifikasi BPOM', 'Kemasan', 'Siap Launching'], [
      ['SS Glow Serum Gen 2 (Niacinamide 10% + Ceramide)', 'Uji Stabilitas & Notifikasi BPOM', '2027-01-15', true, 'Maklon: PT Maklon Kosmetik Nusantara. Estimasi biaya R&D Rp 35 jt. Target launching Feb 2027.'],
      ['SS Lip Cream - 4 shade baru', 'Sampel & Revisi', '2026-12-20', true, 'Sampel ke-3 sedang direview tim. Kendala: shade Nude terlalu pucat.'],
      ['SS Sunscreen SPF 50 PA++++', 'Formulasi', '2027-03-01', false],
      ['Gamis Koleksi Ramadhan 2027', 'Ide & Riset', '2027-01-10', true, 'Moodboard & pemilihan kain.'],
      ['SS Body Lotion - kemasan refill pouch', 'Kemasan', '2026-12-10', false],
    ], 10);
    await project('SS - Event & Partnership', ['Perencanaan', 'Approval Budget', 'Persiapan', 'Pelaksanaan', 'Evaluasi', 'Selesai'], [
      ['Pop-up store Muslim Fashion Festival 2026', 'Persiapan', '2026-12-06', true, 'Budget Rp 45 jt (menunggu realisasi). Partner: JCC.'],
      ['Kolaborasi brand x Kampus (beauty class)', 'Approval Budget', '2026-12-15', false],
      ['Meet & greet Shella Saukia - Bandung', 'Evaluasi', '2026-11-02', false, 'Hasil: 1.200 pengunjung, penjualan booth Rp 38 jt.'],
    ], 7);
    await project('SS - Legal & Perizinan', ['Draft', 'Review Legal', 'Approval Direksi', 'Aktif / Berlaku', 'Perlu Perpanjangan'], [
      ['Notifikasi BPOM SS Glow Serum - berlaku s/d 2026-12-31', 'Perlu Perpanjangan', '2026-12-01', true, 'Pengingat perpanjangan dokumen.'],
      ['Kontrak maklon PT Maklon Kosmetik Nusantara 2027', 'Review Legal', '2026-11-30', true],
      ['Kontrak sewa toko Kemang (s/d Agustus 2027)', 'Aktif / Berlaku', '2027-06-01', false],
      ['Sertifikat Halal produk beauty', 'Draft', '2027-01-31', false],
    ], 1);
    console.log('projects ok');
  }
  if (STEP === 'all' || STEP === 'hr') {
    const emps = await kw('hr.employee', 'search_read', [[['company_id', '=', CID]]], { fields: ['id', 'name'] });
    const days = ['2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17', '2026-11-18'];
    let n = 0, s = 7;
    const r = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    for (const d of days) for (const e of emps) {
      if (r() < 0.06) continue; // absent
      if (await kw('hr.attendance', 'search_count', [[['employee_id', '=', e.id], ['check_in', '>=', d + ' 00:00:00'], ['check_in', '<=', d + ' 23:59:59']]])) continue;
      const late = r() < 0.15 ? Math.floor(r() * 50) + 10 : Math.floor(r() * 10);
      const inT = new Date(`${d}T01:00:00Z`); inT.setUTCMinutes(late); // 08:00 WIB + late
      const outT = new Date(inT); outT.setUTCHours(outT.getUTCHours() + 9 + (r() < 0.2 ? 2 : 0));
      if (d === '2026-11-18') { await kw('hr.attendance', 'create', [{ employee_id: e.id, check_in: inT.toISOString().slice(0, 19).replace('T', ' ') }]); n++; continue; }
      await kw('hr.attendance', 'create', [{ employee_id: e.id, check_in: inT.toISOString().slice(0, 19).replace('T', ' '), check_out: outT.toISOString().slice(0, 19).replace('T', ' ') }]);
      n++;
    }
    console.log('attendance', n);
  }
})().catch(e => { console.error(e.message); console.error((e.debug || '').slice(-1500)); process.exit(1); });
