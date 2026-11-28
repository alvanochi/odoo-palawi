const URL='https://palawi.rutekebangsaan.com',CID=13;
async function sess(l,p){let c='';const post=async(path,params)=>{const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const s=r.headers.get('set-cookie');if(s)c=s.split(';')[0];const j=await r.json();if(j.error)throw new Error(j.error.data.message);return j.result};await post('/web/session/authenticate',{db:'odoo18_palawi',login:l,password:p});return (m,me,a,k={})=>post('/web/dataset/call_kw',{model:m,method:me,args:a,kwargs:Object.assign(k,{context:{allowed_company_ids:[CID]}})});}
(async()=>{const PW=process.env.DEMO_PW;const admin=await sess('admin',process.env.ODOO_PASSWORD);
 for(const [m,v] of [['hr.employee','form'],['hr.employee','list'],['hr.employee','search'],['x_ss_approval','form'],['x_ss_approval','list'],['x_ss_approval','search'],['x_ss_role','list']]){try{await admin(m,'get_views',[[[false,v]]]);}catch(e){console.log('VIEW FAIL',m,v,e.message.slice(0,90));}}
 console.log('views OK');
 console.log('Yuni:',JSON.stringify((await admin('hr.employee','search_read',[[['name','=','Yuni Astuti']]],{fields:['x_ss_role_id']}))[0].x_ss_role_id));
 console.log('APV/0017:',JSON.stringify((await admin('x_ss_approval','search_read',[[['x_number','=','APV/2026/0017']]],{fields:['x_requester_role_id']}))[0].x_requester_role_id));
 console.log('roles:',(await admin('x_ss_role','search_read',[[]],{fields:['x_name']})).map(r=>r.x_name).join(', '));
 for(const u of ['ss.rina','ss.shella','ss.dewi','ss.yuni']){const kw=await sess(u,PW);
  const c=await kw('x_ss_role','check_access_rights',['create'],{raise_exception:false});
  const menus=await kw('ir.ui.menu','load_web_menus',[[],false]);const has=Object.values(menus).some(m=>m&&m.name==='Peran (Role)');
  console.log(u.padEnd(10),'boleh tambah peran:',c,'| menu Peran (Role):',has);}
 const rina=await sess('ss.rina',PW);const id=await rina('x_ss_role','name_create',['TEST Quality Assurance']);
 console.log('Rina inline create ->',JSON.stringify(id));await admin('x_ss_role','unlink',[[id[0]]]);console.log('test role deleted');
})().catch(e=>console.error('FAIL',e.message));
