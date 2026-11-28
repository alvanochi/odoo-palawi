const {login,kw,CID}=require('./rpc');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context:{active_test:false} }); return r.length ? r[0] : kw(model, 'create', [vals]); }
(async()=>{await login();
 const users=(await kw('res.users','search',[[['login','like','ss.%']]])).concat([265]);
 const g=await foc('res.groups',[['name','=','SS Demo / Kontak hanya PT ShellaSaukia']],{name:'SS Demo / Kontak hanya PT ShellaSaukia',comment:'Anggota grup ini hanya melihat kontak PT ShellaSaukia (database dipakai bersama PALAWI). Jangan masukkan admin utama.'});
 await kw('res.groups','write',[[g],{users:[[6,0,users]]}]);
 const comp=(await kw('res.company','read',[[CID]],{fields:['partner_id']}))[0].partner_id[0];
 const bot=(await kw('res.partner','search',[[['name','=','OdooBot']]],{context:{active_test:false}}))[0]||0;
 const model=(await kw('ir.model','search',[[['model','=','res.partner']]]))[0];
 const dom=`['|', '|', '|', ('company_id', '=', ${CID}), ('id', '=', ${comp}), ('user_ids.company_ids', 'in', [${CID}]), ('id', '=', ${bot})]`;
 const r=await foc('ir.rule',[['name','=','SS Demo: kontak hanya PT ShellaSaukia']],{name:'SS Demo: kontak hanya PT ShellaSaukia',model_id:model,groups:[[6,0,[g]]],domain_force:dom,perm_read:true,perm_write:true,perm_create:true,perm_unlink:true});
 await kw('ir.rule','write',[[r],{domain_force:dom}]);
 console.log('group',g,'users',users.length,'rule',r,dom);
})().catch(e=>console.error(e.message));
