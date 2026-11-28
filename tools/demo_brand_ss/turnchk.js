const URL='https://palawi.rutekebangsaan.com';
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(j.error.data.message);return j.result};await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});return post;}
(async()=>{for(const u of ['ss.yuni','ss.shella','ss.dewi']){const s=await sess(u,process.env.DEMO_PW);
const r=(await s('/web/dataset/call_kw',{model:'x_ss_approval',method:'read',args:[[21],['x_is_my_turn','x_approver_id']],kwargs:{context:{allowed_company_ids:[13]}}}))[0];
console.log(u.padEnd(10),'tombol approve tampil:',r.x_is_my_turn);}})().catch(e=>console.error(e.message));
