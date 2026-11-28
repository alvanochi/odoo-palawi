// HR: payroll structure (Indonesia, simplified), contracts, payslips, leave types/allocations/requests. Idempotent-ish.
const { login, kw, CID } = require('./rpc');
const ids = require('./ids.json');
const STEP = process.argv[2] || 'all';
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context: { active_test: false } }); return r.length ? r[0] : kw(model, 'create', [vals]); }
async function ref(x) { const [m, n] = x.split('.'); return (await kw('ir.model.data', 'check_object_reference', [m, n]))[1]; }
async function acc(code) { return (await kw('account.account', 'search', [[['code', '=', code], ['company_ids', 'in', [CID]]]]))[0]; }

const WAGE = {
  'Shella Saukia': [35000000, 5000000], 'Rina Kartika': [14000000, 2000000], 'Dewi Anggraini': [16000000, 2500000], 'Agus Prasetyo': [8500000, 750000],
  'Budi Santoso': [9000000, 1000000], 'Hendra Wijaya': [15000000, 2000000], 'Siti Nurhaliza': [6500000, 500000], 'Joko Susilo': [9500000, 1000000],
  'Andi Saputra': [5200000, 0], 'Maya Puspita': [16000000, 2500000], 'Nadia Putri': [7500000, 500000], 'Citra Lestari': [7000000, 500000],
  'Fajar Ramadhan': [6500000, 500000], 'Intan Permata': [7000000, 500000], 'Reza Firmansyah': [14000000, 2000000], 'Laras Wulandari': [10000000, 1000000],
  'Dimas Pratama': [6500000, 0], 'Yuni Astuti': [11000000, 1000000], 'Eko Kurniawan': [8000000, 750000], 'Wulan Sari': [9000000, 750000],
  'Putri Ayu': [7500000, 500000], 'Taufik Hidayat': [10000000, 1000000],
};

(async () => {
  await login();
  const emps = await kw('hr.employee', 'search_read', [[['company_id', '=', CID], ['name', 'in', Object.keys(WAGE)]]], { fields: ['name', 'parent_id', 'user_id', 'resource_calendar_id'] });
  const E = Object.fromEntries(emps.map(e => [e.name, e]));

  if (STEP === 'all' || STEP === 'payroll') {
    const cat = {}; for (const c of ['BASIC', 'ALW', 'GROSS', 'DED', 'NET']) cat[c] = await ref('om_hr_payroll.' + c);
    const A = { sal: await acc('61100010'), ben: await acc('61100020'), bpjs: await acc('25110110'), pph21: await acc('21210010'), dep: await acc('21100040') };
    const RULES = [
      ['SS Gaji Pokok', 'SS_BASIC', 1, 'BASIC', 'result = contract.wage', A.sal, A.dep],
      ['SS Tunjangan Jabatan', 'SS_TJAB', 3, 'ALW', 'result = contract.hra', A.ben, A.dep],
      ['SS Tunjangan Makan & Transport', 'SS_TMT', 5, 'ALW', 'result = contract.meal_allowance + contract.travel_allowance', A.ben, A.dep],
      ['SS Gaji Bruto', 'SS_GROSS', 100, 'GROSS', 'result = categories.BASIC + categories.ALW', false, false],
      ['SS BPJS Kesehatan (1%)', 'SS_BPJSKES', 110, 'DED', 'result = -round(min(contract.wage, 12000000) * 0.01)', A.bpjs, A.dep],
      ['SS BPJS JHT (2%)', 'SS_JHT', 111, 'DED', 'result = -round(contract.wage * 0.02)', A.bpjs, A.dep],
      ['SS BPJS Jaminan Pensiun (1%)', 'SS_JP', 112, 'DED', 'result = -round(min(contract.wage, 10042300) * 0.01)', A.bpjs, A.dep],
      ['SS PPh 21 (TER, disederhanakan)', 'SS_PPH21', 120, 'DED', "g = categories.BASIC + categories.ALW\nrate = 0.0 if g <= 5400000 else 0.01 if g <= 7500000 else 0.025 if g <= 10000000 else 0.05 if g <= 15000000 else 0.09 if g <= 25000000 else 0.15\nresult = -round(g * rate)", A.pph21, A.dep],
      ['SS Gaji Bersih (THP)', 'SS_NET', 200, 'NET', 'result = categories.BASIC + categories.ALW + categories.DED', false, false],
    ];
    const ruleIds = [];
    for (const [name, code, seq, c, py, deb, cred] of RULES) {
      const r = await foc('hr.salary.rule', [['code', '=', code], ['company_id', '=', CID]], { name, code, sequence: seq, category_id: cat[c], company_id: CID, condition_select: 'none', amount_select: 'code', amount_python_compute: py, account_debit: deb, account_credit: cred });
      await kw('hr.salary.rule', 'write', [[r], { amount_python_compute: py, account_debit: deb, account_credit: cred }]);
      ruleIds.push(r);
    }
    const struct = await foc('hr.payroll.structure', [['code', '=', 'SS-ID'], ['company_id', '=', CID]], { name: 'SS - Struktur Gaji Bulanan (Indonesia)', code: 'SS-ID', company_id: CID, rule_ids: [[6, 0, ruleIds]] });
    await kw('hr.payroll.structure', 'write', [[struct], { rule_ids: [[6, 0, ruleIds]] }]);
    // journal for payroll
    const jSal = await foc('account.journal', [['code', '=', 'GAJI'], ['company_id', '=', CID]], { name: 'Jurnal Gaji (Payroll)', code: 'GAJI', type: 'general', company_id: CID });
    // contracts
    const ctype = (await kw('hr.contract.type', 'search', [[]], { limit: 1 }))[0];
    let cal = (await kw('resource.calendar', 'search', [[['company_id', '=', CID]]], { limit: 1 }))[0];
    if (!cal) cal = await kw('resource.calendar', 'create', [{ name: 'SS - Jam Kerja 08.00-17.00 (Sen-Jum)', company_id: CID }]);
    const C = {};
    let i = 0;
    for (const [name, [wage, tjab]] of Object.entries(WAGE)) {
      const e = E[name]; if (!e) continue;
      const pkwt = ['Andi Saputra', 'Dimas Pratama', 'Fajar Ramadhan', 'Siti Nurhaliza'].includes(name);
      const start = pkwt ? '2025-12-15' : ['2023-03-01', '2024-01-08', '2024-07-01', '2025-02-03'][i++ % 4];
      const end = pkwt ? (name === 'Andi Saputra' || name === 'Dimas Pratama' ? '2026-12-14' : '2027-06-14') : false;
      let c = (await kw('hr.contract', 'search', [[['employee_id', '=', e.id], ['company_id', '=', CID]]]))[0];
      if (!c) {
        c = await kw('hr.contract', 'create', [{ name: `${pkwt ? 'PKWT' : 'PKWTT'} - ${name}`, employee_id: e.id, company_id: CID, date_start: start, date_end: end, wage, hra: tjab, meal_allowance: 750000, travel_allowance: 500000, struct_id: struct, journal_id: jSal, type_id: ctype, resource_calendar_id: cal, schedule_pay: 'monthly', department_id: undefined }]);
        await kw('hr.contract', 'write', [[c], { state: 'open' }]);
      }
      C[name] = c;
    }
    console.log('contracts', Object.keys(C).length);
    // remove manual October salary JE (replaced by payslips)
    const man = await kw('account.move', 'search', [[['ref', '=', 'GAJI-2026-10-28'], ['company_id', '=', CID]]]);
    if (man.length) { await kw('account.move', 'button_draft', [man]); await kw('account.move', 'unlink', [man]); console.log('removed manual Oct salary JE'); }
    // payslips
    async function run(from, to, done, label) {
      const batch = await foc('hr.payslip.run', [['name', '=', label], ['company_id', '=', CID]], { name: label, date_start: from, date_end: to, journal_id: jSal, company_id: CID }).catch(async () => foc('hr.payslip.run', [['name', '=', label]], { name: label, date_start: from, date_end: to, journal_id: jSal }));
      const slips = [];
      for (const [name, c] of Object.entries(C)) {
        let s = (await kw('hr.payslip', 'search', [[['employee_id', '=', E[name].id], ['date_from', '=', from]]]))[0];
        if (!s) s = await kw('hr.payslip', 'create', [{ name: `Slip Gaji ${name} - ${label.replace('Payroll ', '')}`, employee_id: E[name].id, contract_id: c, struct_id: struct, date_from: from, date_to: to, journal_id: jSal, payslip_run_id: batch, company_id: CID }]);
        slips.push(s);
      }
      await kw('hr.payslip', 'compute_sheet', [slips]);
      if (done) {
        for (const s of slips) { const st = (await kw('hr.payslip', 'read', [[s]], { fields: ['state'] }))[0].state; if (st !== 'done') await kw('hr.payslip', 'action_payslip_done', [[s]]); }
        const moves = (await kw('hr.payslip', 'read', [slips], { fields: ['move_id'] })).map(x => x.move_id && x.move_id[0]).filter(Boolean);
        if (moves.length) await kw('account.move', 'write', [moves, { date: to }]).catch(() => {});
      }
      return slips;
    }
    const oct = await run('2026-10-01', '2026-10-31', true, 'Payroll Oktober 2026');
    await run('2026-11-01', '2026-11-30', false, 'Payroll November 2026');
    // pay October net salaries from BCA
    if (!(await kw('account.move', 'search_count', [[['ref', '=', 'TRANSFER-GAJI-2026-10'], ['company_id', '=', CID]]]))) {
      const net = (await kw('hr.payslip.line', 'search_read', [[['slip_id', 'in', oct], ['code', '=', 'SS_NET']]], { fields: ['total'] })).reduce((a, x) => a + x.total, 0);
      const bank = (await kw('account.journal', 'read', [[ids.J.bca]], { fields: ['default_account_id'] }))[0].default_account_id[0];
      const m = await kw('account.move', 'create', [{ move_type: 'entry', ref: 'TRANSFER-GAJI-2026-10', date: '2026-10-28', journal_id: ids.J.bca, company_id: CID, line_ids: [[0, 0, { name: 'Transfer gaji bersih Oktober 2026', account_id: A.dep, debit: net }], [0, 0, { name: 'Transfer gaji bersih Oktober 2026', account_id: bank, credit: net }]] }]);
      await kw('account.move', 'action_post', [[m]]);
      console.log('paid net Oct', net);
    }
  }

  if (STEP === 'all' || STEP === 'leave') {
    // leave managers = direct manager's user
    for (const e of emps) { if (e.parent_id) { const p = emps.find(x => x.id === e.parent_id[0]); if (p && p.user_id) await kw('hr.employee', 'write', [[e.id], { leave_manager_id: p.user_id[0] }]); } }
    const tAnnual = await foc('hr.leave.type', [['name', '=', 'SS Cuti Tahunan'], ['company_id', '=', CID]], { name: 'SS Cuti Tahunan', company_id: CID, requires_allocation: 'yes', leave_validation_type: 'manager', request_unit: 'day', employee_requests: 'no' });
    const tSick = await foc('hr.leave.type', [['name', '=', 'SS Sakit (dengan surat dokter)'], ['company_id', '=', CID]], { name: 'SS Sakit (dengan surat dokter)', company_id: CID, requires_allocation: 'no', leave_validation_type: 'manager', request_unit: 'day', support_document: true });
    const tIzin = await foc('hr.leave.type', [['name', '=', 'SS Izin (keperluan pribadi)'], ['company_id', '=', CID]], { name: 'SS Izin (keperluan pribadi)', company_id: CID, requires_allocation: 'no', leave_validation_type: 'manager', request_unit: 'half_day' });
    for (const e of emps) {
      if (await kw('hr.leave.allocation', 'search_count', [[['employee_id', '=', e.id], ['holiday_status_id', '=', tAnnual]]])) continue;
      const a = await kw('hr.leave.allocation', 'create', [{ name: 'Cuti Tahunan 2026', employee_id: e.id, holiday_status_id: tAnnual, number_of_days: 12, date_from: '2026-01-01', date_to: '2026-12-31', allocation_type: 'regular' }]);
      await kw('hr.leave.allocation', 'action_approve', [[a]]).catch(async () => kw('hr.leave.allocation', 'action_validate', [[a]]));
    }
    const LEAVES = [
      ['Citra Lestari', tAnnual, '2026-10-12', '2026-10-14', 'Cuti tahunan - acara keluarga', 'approve'],
      ['Andi Saputra', tSick, '2026-10-21', '2026-10-22', 'Demam (surat dokter terlampir)', 'approve'],
      ['Laras Wulandari', tAnnual, '2026-11-03', '2026-11-04', 'Cuti tahunan', 'approve'],
      ['Agus Prasetyo', tIzin, '2026-11-18', '2026-11-18', 'Izin urus SIM', 'approve'],
      ['Nadia Putri', tAnnual, '2026-12-22', '2026-12-26', 'Cuti akhir tahun (pulang kampung)', 'pending'],
      ['Dimas Pratama', tAnnual, '2026-11-27', '2026-11-28', 'Cuti tahunan - wisuda adik', 'pending'],
      ['Wulan Sari', tIzin, '2026-11-20', '2026-11-20', 'Izin setengah hari - urusan bank', 'pending'],
    ];
    for (const [n, t, f, to, desc, st] of LEAVES) {
      const e = E[n];
      if (await kw('hr.leave', 'search_count', [[['employee_id', '=', e.id], ['request_date_from', '=', f]]])) continue;
      const l = await kw('hr.leave', 'create', [{ name: desc, employee_id: e.id, holiday_status_id: t, request_date_from: f, request_date_to: to }]);
      if (st === 'approve') { await kw('hr.leave', 'action_approve', [[l]]).catch(e2 => console.log('approve', n, e2.message)); }
    }
    console.log('leaves ok');
  }
})().catch(e => { console.error(e.message); console.error((e.debug || '').split(String.fromCharCode(10)).filter(l => l.includes('File')).slice(-8).join(String.fromCharCode(10))); process.exit(1); });
