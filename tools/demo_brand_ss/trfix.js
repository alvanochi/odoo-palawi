const {login,kw}=require('./rpc');(async()=>{await login();
let c=(await kw('ir.actions.server','read',[[1009]],{fields:['code']}))[0].code;
c=c.replace("    if not env.user.has_group('account.group_account_manager'):\n","    if not (env.user.has_group('ss_demo.group_approval_finance') or env.user.has_group('base.group_system')):\n");
await kw('ir.actions.server','write',[[1009],{code:c}]);
const v=(await kw('ir.ui.view','search_read',[[['name','=','x_ss_approval.form']]],{fields:['arch_db']}))[0];
let a=v.arch_db.replace(/(<button name="1009"[^>]*?)groups="account.group_account_manager"/,'$1groups="ss_demo.group_approval_finance,base.group_system"')
 .replace('groups="ss_demo.group_approval_finance,base.group_system,account.group_account_manager"','groups="ss_demo.group_approval_finance,base.group_system"');
await kw('ir.ui.view','write',[[v.id],{arch_db:a}]);
console.log('code ok:',c.includes("group_approval_finance"),'| button:',(a.match(/<button name="1009"[^>]*groups="([^"]+)"/)||[])[1],'| bayar dari field groups fixed:',!a.includes('account.group_account_manager'));
})().catch(e=>console.error(e.message));
