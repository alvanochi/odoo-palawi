const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');
(async()=>{await login();
 if(await kw('account.move','search_count',[[['ref','=','SETORAN-MODAL-AWAL'],['company_id','=',CID]]])) return console.log('exists');
 const bank=(await kw('account.journal','read',[[ids.J.bca]],{fields:['default_account_id']}))[0].default_account_id[0];
 const cap=(await kw('account.account','search',[[['code','=','31100020'],['company_ids','in',[CID]]]]))[0];
 const m=await kw('account.move','create',[{move_type:'entry',ref:'SETORAN-MODAL-AWAL',date:'2026-08-31',journal_id:ids.J.bca,company_id:CID,line_ids:[[0,0,{name:'Setoran modal disetor pemegang saham',account_id:bank,debit:750000000}],[0,0,{name:'Modal disetor',account_id:cap,credit:750000000}]]}]);
 await kw('account.move','action_post',[[m]]); console.log('capital posted',m);
})().catch(e=>{console.error(e.message)});
