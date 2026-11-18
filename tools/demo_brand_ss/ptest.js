const URL='https://palawi.rutekebangsaan.com';
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(j.error.data.message);return j.result};await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});return (m,me,a,k={})=>post('/web/dataset/call_kw',{model:m,method:me,args:a,kwargs:Object.assign(k,{context:{allowed_company_ids:[13]}})});}
(async()=>{
 const maya=await sess('ss.maya',process.env.DEMO_PW);
 console.log('Maya sees partners:',await maya('res.partner','search_count',[[]]));
 const sample=await maya('res.partner','search_read',[[]],{fields:['name','company_id'],limit:60});
 console.log('non-SS visible:',sample.filter(p=>!p.company_id).map(p=>p.name));
 console.log('SO S00335 read:',(await maya('sale.order','search_read',[[['name','=','S00335']]],{fields:['partner_id','user_id','team_id']}))[0]);
 const inv=await maya('account.move','search_read',[[['name','=','INV/2026/00294']]],{fields:['partner_id','invoice_user_id']}).catch(e=>'ERR '+e.message);console.log('invoice read:',JSON.stringify(inv).slice(0,160));
 const admin=await sess('admin',process.env.ODOO_PASSWORD);
 console.log('Admin (PALAWI) still sees partners:',await admin('res.partner','search_count',[[]]));
})().catch(e=>console.error('FAIL',e.message));
