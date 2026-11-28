const URL='https://palawi.rutekebangsaan.com',CID=13;
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(j.error.data.message);return j.result};const a=await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});const kw=(m,me,args,k={})=>post('/web/dataset/call_kw',{model:m,method:me,args,kwargs:Object.assign(k,{context:{allowed_company_ids:[CID]}})});kw.run=(sa,id)=>post('/web/action/run',{action_id:sa,context:{active_model:'x_ss_approval',active_id:id,active_ids:[id],allowed_company_ids:[CID]}});kw.uid=a.uid;return kw;}
(async()=>{const PW=process.env.DEMO_PW;const yuni=await sess('ss.yuni',PW),shella=await sess('ss.shella',PW),dewi=await sess('ss.dewi',PW),admin=await sess('admin',process.env.ODOO_PASSWORD);
const an=(await admin('account.analytic.account','search',[[['name','=','R&D - SS Glow Serum Gen 2']]]))[0];let id,mv;
try{id=await yuni('x_ss_approval','create',[{x_name:'TEST transfer rights',x_type:'riset',x_company_id:CID,x_requester_id:yuni.uid,x_state:'draft',x_analytic_id:an,x_amount:1000}]);
 await yuni.run(1001-1001+ (await admin('ir.actions.server','search',[[['name','=','SS Approval: submit']]]))[0],id);
 const ap=(await admin('ir.actions.server','search',[[['name','=','SS Approval: approve']]]))[0];await shella.run(ap,id);await dewi.run(ap,id);
 try{await shella.run(1009,id);console.log('!! Shella could transfer');}catch(e){console.log('Shella Transfer ->',e.message);}
 await dewi.run(1009,id);const r=(await admin('x_ss_approval','read',[[id],['x_state','x_transfer_move_id']]))[0];mv=r.x_transfer_move_id&&r.x_transfer_move_id[0];console.log('Dewi Transfer -> state',r.x_state);
}finally{if(mv){await admin('account.move','button_draft',[[mv]]);await admin('account.move','unlink',[[mv]]);}if(id)await admin('x_ss_approval','unlink',[[id]]);console.log('test data removed');}
})().catch(e=>console.error('FAIL',e.message));
