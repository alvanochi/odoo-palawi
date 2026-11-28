const {login,kw,CID}=require('./rpc');(async()=>{await login();
 const ps=await kw('res.partner','search_read',[[['company_id','in',[CID,false]],['is_company','=',false]]],{fields:['name','user_ids','employee_ids','company_id','email']});
 const byName={};for(const p of ps)(byName[p.name]=byName[p.name]||[]).push(p);
 for(const [n,list] of Object.entries(byName)){ if(list.length<2) continue;
   const keep=list.find(p=>p.user_ids.length)||list[0];
   for(const p of list){ if(p.id===keep.id) continue;
     // only archive orphans: no user, no employee link, no accounting/sales usage
     const used=await kw('account.move','search_count',[[['partner_id','=',p.id]]])+await kw('sale.order','search_count',[[['partner_id','=',p.id]]]);
     if(p.user_ids.length||p.employee_ids.length||used){console.log('keep (in use)',n,p.id);continue;}
     await kw('res.partner','write',[[p.id],{active:false}]);console.log('archived duplicate',n,p.id,'kept',keep.id);
   }
 }})().catch(e=>console.error(e.message));
