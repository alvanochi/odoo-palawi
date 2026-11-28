const {login,kw,CID}=require('./rpc');const L=require('./lib');const {ids}=L;
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context:{active_test:false} }); return r.length ? r[0] : kw(model, 'create', [vals]); }
(async()=>{await login();
 const term30=(await kw('account.payment.term','search',[[['name','=','30 Days']]]))[0];
 const tabang=await foc('res.partner',[['name','=','PT Grosir Busana Muslim Tanah Abang (Distributor)'],['company_id','=',CID]],{name:'PT Grosir Busana Muslim Tanah Abang (Distributor)',company_id:CID,is_company:true,city:'Jakarta Pusat',country_id:100,customer_rank:1,credit_limit:400000000,property_product_pricelist:ids.PL.dist,property_payment_term_id:term30});
 await kw('res.partner','write',[[tabang],{property_product_pricelist:ids.PL.dist,property_payment_term_id:term30}]);
 await kw('res.partner','write',[[ids.R.dist_sby],{credit_limit:400000000}]);
 const fash=[...await L.variants('gamis'),...await L.variants('tunik'),...await L.variants('pashmina')];
 const beau=[...await L.variants('serum'),...await L.variants('lip'),...await L.variants('lotion'),...await L.variants('wash')];
 const ORD=[['B2B-BIG-1','2026-10-06',tabang,16,24,0,true],['B2B-BIG-2','2026-10-21',ids.R.dist_sby,14,22,7,true],['B2B-BIG-3','2026-11-04',tabang,14,20,3,false],['B2B-BIG-4','2026-11-13',ids.R.dist_sby,12,18,11,false]];
 for(const [ref,day,partner,qmin,qmax,seed,paid] of ORD){
  if(await kw('sale.order','search_count',[[['client_order_ref','=',ref]]])) {console.log('skip',ref);continue;}
  let s=seed+3;const r=()=>{s=(s*9301+49297)%233280;return s/233280;};
  const lines=[];
  for(const v of fash) if(r()<0.6) lines.push([0,0,{product_id:v.id,product_uom_qty:qmin+Math.floor(r()*(qmax-qmin)),analytic_distribution:{[String(ids.AN.res)]:100}}]);
  for(const v of beau) lines.push([0,0,{product_id:v.id,product_uom_qty:(qmin+Math.floor(r()*(qmax-qmin)))*4,analytic_distribution:{[String(ids.AN.res)]:100}}]);
  const so=await kw('sale.order','create',[{partner_id:partner,team_id:ids.TM.res,client_order_ref:ref,company_id:CID,warehouse_id:ids.W.main,order_line:lines,user_id:265,date_order:day+' 03:00:00',note:'Order grosir distributor (dummy)'}]);
  await kw('sale.order','action_confirm',[[so]]);
  await kw('sale.order','write',[[so],{date_order:day+' 03:00:00'}]);
  const name=(await kw('sale.order','read',[[so]],{fields:['name']}))[0].name;
  const ship=new Date(day+'T00:00:00Z');ship.setUTCDate(ship.getUTCDate()+2);const sd=ship.toISOString().slice(0,10);
  await L.processChain(name,sd+' 08:00:00',6);
  const ctx={active_model:'sale.order',active_ids:[so]};
  const w=await kw('sale.advance.payment.inv','create',[{advance_payment_method:'delivered'}],{context:ctx});
  await kw('sale.advance.payment.inv','create_invoices',[[w]],{context:ctx});
  const inv=(await kw('sale.order','read',[[so]],{fields:['invoice_ids','amount_total']}))[0];
  await L.postInvoice(inv.invoice_ids[0],sd);
  if(paid){ // direct payment + reconcile (wizard is unreliable on this DB)
    const pd=new Date(sd+'T00:00:00Z');pd.setUTCDate(pd.getUTCDate()+28);const pds=pd.toISOString().slice(0,10);
    const amt=(await kw('account.move','read',[[inv.invoice_ids[0]]],{fields:['amount_residual']}))[0].amount_residual;
    const p=await kw('account.payment','create',[{payment_type:'inbound',partner_type:'customer',partner_id:partner,amount:amt,date:pds,journal_id:ids.J.bca,company_id:CID,memo:name}]);
    await kw('account.payment','action_post',[[p]]);
    const pm=(await kw('account.payment','read',[[p]],{fields:['move_id']}))[0].move_id[0];
    const ls=await kw('account.move.line','search',[[['move_id','in',[pm,inv.invoice_ids[0]]],['account_id.account_type','=','asset_receivable'],['reconciled','=',false]]]);
    await kw('account.move.line','reconcile',[ls]);
  }
  console.log(ref,name,Math.round(inv.amount_total));
 }
})().catch(e=>{console.error(e.message);console.error((e.debug||'').split(String.fromCharCode(10)).filter(l=>l.includes('File')).slice(-6).join(String.fromCharCode(10)))});
