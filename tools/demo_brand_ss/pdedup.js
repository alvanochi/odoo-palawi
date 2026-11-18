const {login,kw,CID}=require('./rpc');(async()=>{await login();
 // 1) rule: only users whose main company is SS (excludes PALAWI admin)
 const r=(await kw('ir.rule','search',[[['name','=','SS Demo: kontak hanya PT ShellaSaukia']]]))[0];
 const old=(await kw('ir.rule','read',[[r]],{fields:['domain_force']}))[0].domain_force;
 await kw('ir.rule','write',[[r],{domain_force:old.replace("('user_ids.company_ids', 'in', [13])","('user_ids.company_id', '=', 13)")}]);
 // 2) employees linked to users: use the user's partner as work contact, archive the duplicate
 const emps=await kw('hr.employee','search_read',[[['company_id','=',CID],['user_id','!=',false]]],{fields:['name','user_id','work_contact_id']});
 for(const e of emps){
   const up=(await kw('res.users','read',[[e.user_id[0]]],{fields:['partner_id']}))[0].partner_id[0];
   if(e.work_contact_id && e.work_contact_id[0]!==up){
     const dup=e.work_contact_id[0];
     await kw('hr.employee','write',[[e.id],{work_contact_id:up}]);
     await kw('res.partner','write',[[up],{company_id:CID}]);
     await kw('res.partner','write',[[dup],{active:false}]).catch(x=>console.log('archive',e.name,x.message));
     console.log('merged',e.name);
   } else await kw('res.partner','write',[[up],{company_id:CID}]);
 }
 console.log((await kw('ir.rule','read',[[r]],{fields:['domain_force']}))[0].domain_force);
})().catch(e=>console.error(e.message));
