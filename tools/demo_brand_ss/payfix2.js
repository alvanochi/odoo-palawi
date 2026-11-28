const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');const fs=require('fs');
(async()=>{await login();
 const b=JSON.parse(fs.readFileSync('pays_backup.json'));
 const misc=(await kw('account.journal','search',[[['code','=','MISC'],['company_id','=',CID]]]))[0];
 let n=0;
 for(const p of b){
   // still has the original payment (not yet deleted)? delete it
   const orig=await kw('account.payment','search_read',[[['id','=',p.id]]],{fields:['move_id']});
   if(orig.length && !orig[0].move_id){ await kw('account.payment','action_draft',[[p.id]]); await kw('account.payment','unlink',[[p.id]]); }
   const inv=await kw('account.move','read',[p.invoice_ids],{fields:['partner_id','move_type','amount_residual','line_ids','payment_state']});
   if(inv.every(i=>i.payment_state==='paid'||i.payment_state==='in_payment'||i.payment_state==='partial')) { process.stdout.write('s'); continue; }
   const inbound=p.payment_type==='inbound';
   const partner=inv[0].partner_id[0];
   let pid=(await kw('account.payment','search',[[['company_id','=',CID],['journal_id','=',p.journal_id[0]],['amount','=',p.amount],['date','=',p.date],['partner_id','=',partner],['move_id','!=',false]]]))[0];
   if(!pid){ pid=await kw('account.payment','create',[{payment_type:p.payment_type,partner_type:inbound?'customer':'supplier',partner_id:partner,amount:p.amount,date:p.date,journal_id:p.journal_id[0],company_id:CID,memo:p.memo||false}]);
     await kw('account.payment','action_post',[[pid]]); }
   const pmove=(await kw('account.payment','read',[[pid]],{fields:['move_id']}))[0].move_id[0];
   const accType=inbound?'asset_receivable':'liability_payable';
   const invLines=await kw('account.move.line','search',[[['move_id','in',p.invoice_ids],['account_id.account_type','=',accType],['reconciled','=',false]]]);
   const payLines=await kw('account.move.line','search',[[['move_id','=',pmove],['account_id.account_type','=',accType],['reconciled','=',false]]]);
   const resid=inv.reduce((a,x)=>a+x.amount_residual,0);
   let feeLines=[];
   const isMp=p.journal_id[0]===ids.J.tts||p.journal_id[0]===ids.J.shp;
   if(isMp && resid-p.amount>1){
     const fee=Math.round((resid-p.amount)*100)/100;
     const rl=(await kw('account.move.line','read',[invLines.slice(0,1)],{fields:['account_id']}))[0].account_id[0];
     const je=await kw('account.move','create',[{move_type:'entry',journal_id:misc,date:p.date,ref:'Biaya admin marketplace - '+(p.memo||''),company_id:CID,line_ids:[[0,0,{name:'Biaya admin & layanan marketplace',account_id:ids.A.adminFee,debit:fee,analytic_distribution:{[String(p.journal_id[0]===ids.J.tts?ids.AN.tts:ids.AN.shp)]:100}}],[0,0,{name:'Potongan settlement marketplace',account_id:rl,partner_id:partner,credit:fee}]]}]);
     await kw('account.move','action_post',[[je]]);
     feeLines=await kw('account.move.line','search',[[['move_id','=',je],['account_id','=',rl]]]);
   }
   await kw('account.move.line','reconcile',[[...invLines,...payLines,...feeLines]]);
   n++; process.stdout.write('.');
 }
 const g=await kw('account.move.line','read_group',[[['parent_state','=','posted'],['account_id.account_type','=','asset_receivable'],['reconciled','=',false],['company_id','=',CID]],['amount_residual:sum'],['partner_id']],{lazy:false});
 console.log('\nredone',n,'\n',g.map(x=>[x.partner_id&&x.partner_id[1],Math.round(x.amount_residual)]));
 console.log('payments w/o move:',await kw('account.payment','search_count',[[['company_id','=',CID],['move_id','=',false]]]));
})().catch(e=>{console.error(e.message);console.error((e.debug||"").split(String.fromCharCode(10)).filter(l=>l.includes("File")).slice(-14).join(String.fromCharCode(10)))});
