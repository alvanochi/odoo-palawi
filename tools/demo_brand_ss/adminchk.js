const URL='https://palawi.rutekebangsaan.com';
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];return (await r.json()).result};await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});return (m,me,a,k={})=>post('/web/dataset/call_kw',{model:m,method:me,args:a,kwargs:k});}
(async()=>{for(const [u,pw] of [['ss.shella',process.env.DEMO_PW],['ss.dewi',process.env.DEMO_PW],['ss.yuni',process.env.DEMO_PW],['admin',process.env.ODOO_PASSWORD]]){const kw=await sess(u,pw);
 const menus=await kw('ir.ui.menu','load_web_menus',[[],false]);const has=Object.values(menus||{}).some(m=>m&&m.name==='Aturan Approval');
 const w=await kw('x_ss_approval_rule','check_access_rights',['write'],{raise_exception:false});
 console.log(u.padEnd(10),'menu Aturan Approval tampil:',has,' | boleh ubah aturan:',w);}})().catch(e=>console.error(e.message));
