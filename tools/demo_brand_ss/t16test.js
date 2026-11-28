const {SA}=require('./approval_ids.json');const URL='https://palawi.rutekebangsaan.com',CID=13;
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(l+': '+j.error.data.message);return j.result};const a=await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});
 const kw=(m,me,args,k={})=>post('/web/dataset/call_kw',{model:m,method:me,args,kwargs:Object.assign(k,{context:{allowed_company_ids:[CID]}})});kw.run=(sa,id)=>post('/web/action/run',{action_id:sa,context:{active_model:'x_ss_approval',active_id:id,active_ids:[id],allowed_company_ids:[CID]}});kw.uid=a.uid;return kw;}
(async()=>{const PW=process.env.DEMO_PW;const yuni=await sess('ss.yuni',PW),shella=await sess('ss.shella',PW),dewi=await sess('ss.dewi',PW),admin=await sess('admin',process.env.ODOO_PASSWORD);
 const rd=async id=>(await admin('x_ss_approval','read',[[id],['x_state','x_journal_id','x_transfer_move_id']]))[0];
 const an=(await admin('account.analytic.account','search',[[['name','=','R&D - SS Glow Serum Gen 2']]]))[0];
 const cash=(await admin('account.journal','search',[[['code','=','CSH1'],['company_id','=',CID]]]))[0];
 let id,mv;
 try{
  id=await yuni('x_ss_approval','create',[{x_name:'TEST transfer source',x_type:'riset',x_company_id:CID,x_requester_id:yuni.uid,x_state:'draft',x_analytic_id:an,x_amount:1000}]);
  await yuni.run(SA.submit,id);await shella.run(SA.approve,id);await dewi.run(SA.approve,id);
  console.log('after approval (prefill):',JSON.stringify(await rd(id)));
  await dewi('x_ss_approval','write',[[id],{x_journal_id:cash}]);
  await dewi.run(SA.transfer||1009,id);
  const r=await rd(id);mv=r.x_transfer_move_id&&r.x_transfer_move_id[0];
  const m=(await admin('account.move','read',[[mv],['journal_id','line_ids']]))[0];
  const ls=await admin('account.move.line','read',[m.line_ids,['account_id','debit','credit']]);
  console.log('transfer journal:',m.journal_id[1],'| lines:',ls.map(l=>l.account_id[1]+' D'+l.debit+' C'+l.credit).join(' ; '));
 } finally {
  if(mv){await admin('account.move','button_draft',[[mv]]);await admin('account.move','unlink',[[mv]]);}
  if(id) await admin('x_ss_approval','unlink',[[id]]);
  console.log('test data removed');
 }
 for(const [u,kw] of [['ss.dewi',dewi],['ss.shella',shella],['ss.yuni',yuni],['admin',admin]]){
  const menus=await kw('ir.ui.menu','load_web_menus',[[],false]);const names=new Set(Object.values(menus).map(m=>m&&m.name));
  const w=await kw('x_ss_approval_type_conf','check_access_rights',['write'],{raise_exception:false});
  console.log(u.padEnd(9),'Pengaturan Jenis Pengajuan:',names.has('Pengaturan Jenis Pengajuan'),'| Aturan Approval:',names.has('Aturan Approval'),'| boleh ubah pengaturan:',w);}
})().catch(e=>console.error('FAIL',e.message));
