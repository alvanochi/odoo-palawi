const {SA}=require('./approval_ids.json');const URL='https://palawi.rutekebangsaan.com';
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(j.error.data.message);return j.result};await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});return post;}
(async()=>{const y=await sess('ss.yuni',process.env.DEMO_PW);
const rec=(await y('/web/dataset/call_kw',{model:'x_ss_approval',method:'search_read',args:[[['x_number','=','APV/2026/0017']]],kwargs:{fields:['x_state','x_approver_id','x_requester_id'],context:{allowed_company_ids:[13]}}}))[0];console.log(rec);
try{await y('/web/action/run',{action_id:SA.approve,context:{active_model:'x_ss_approval',active_id:rec.id,active_ids:[rec.id],allowed_company_ids:[13]}});console.log('!! APPROVED by Yuni');}catch(e){console.log('Yuni klik Setujui ->',e.message);}
const after=(await y('/web/dataset/call_kw',{model:'x_ss_approval',method:'read',args:[[rec.id],['x_state','x_approver_id']],kwargs:{context:{allowed_company_ids:[13]}}}))[0];console.log('state after:',after);
})().catch(e=>console.error(e.message));
