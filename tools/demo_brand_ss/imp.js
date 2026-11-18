const {login,kw}=require('./rpc');const fs=require('fs');
(async()=>{await login();
 const w=await kw('base.import.module','create',[{module_file:fs.readFileSync('ss_executive_dashboard.zip').toString('base64'),force:true}]);
 const r=await kw('base.import.module','import_module',[[w]]);
 console.log(JSON.stringify(r).slice(0,300));
 console.log(await kw('base.import.module','read',[[w]],{fields:['import_message','state']}));
 console.log(await kw('ir.module.module','search_read',[[['name','=','ss_executive_dashboard']]],{fields:['state','imported']}));
 console.log(await kw('ir.asset','search_read',[[['path','like','ss_executive_dashboard']]],{fields:['bundle','path']}));
})().catch(e=>{console.error(e.message);console.error((e.debug||'').slice(-1500))});
