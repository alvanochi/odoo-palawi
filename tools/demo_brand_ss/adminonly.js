const {login,kw}=require('./rpc');(async()=>{await login();
const sys=(await kw('ir.model.data','check_object_reference',['base','group_system']))[1];
const sysUsers=await kw('res.users','search_read',[[['groups_id','in',[sys]]]],{fields:['login','company_id']});
console.log('Administrator (Settings) users:',sysUsers.map(u=>u.login).join(', '));
const gMgr=(await kw('res.groups','search',[[['name','=','SS Approval / Manager']]]))[0];
// 1) menu Konfigurasi -> admin only
const root=(await kw('ir.ui.menu','search',[[['name','=','Pengajuan & Approval'],['parent_id','=',false]]]))[0];
const conf=(await kw('ir.ui.menu','search',[[['name','=','Konfigurasi'],['parent_id','=',root]]]))[0];
await kw('ir.ui.menu','write',[[conf],{groups_id:[[6,0,[sys]]]}]);
// 2) rule model: managers read-only, admin full
const M=(await kw('ir.model','search',[[['model','=','x_ss_approval_rule']]]))[0];
const acc=await kw('ir.model.access','search_read',[[['model_id','=',M],['group_id','=',gMgr]]],{fields:['id']});
if(acc.length) await kw('ir.model.access','write',[acc.map(a=>a.id),{perm_write:false,perm_create:false,perm_unlink:false}]);
const exSys=await kw('ir.model.access','search',[[['model_id','=',M],['group_id','=',sys]]]);
if(!exSys.length) await kw('ir.model.access','create',[{name:'x_ss_approval_rule admin',model_id:M,group_id:sys,perm_read:true,perm_write:true,perm_create:true,perm_unlink:true}]);
console.log('menu groups:',(await kw('ir.ui.menu','read',[[conf]],{fields:['groups_id']}))[0].groups_id);
console.log((await kw('ir.model.access','search_read',[[['model_id','=',M]]],{fields:['group_id','perm_write','perm_create']})).map(a=>a.group_id[1]+' W'+(+a.perm_write)+' C'+(+a.perm_create)));
})().catch(e=>console.error(e.message));
