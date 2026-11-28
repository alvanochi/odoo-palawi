const {login,kw,CID}=require('./rpc');(async()=>{await login();
const v=(await kw('ir.ui.view','search',[[['name','=','hr.employee.form.x_ss_role']]]))[0];
await kw('ir.ui.view','write',[[v],{arch_db:`<data><xpath expr="//field[@name='job_id']" position="after"><field name="x_ss_role" string="Peran (Role)" invisible="company_id != ${CID}"/></xpath></data>`}]);
const r=await kw('hr.employee','get_views',[[[false,'form']]]);const a=r.views.form.arch;
console.log('in form:',a.includes('x_ss_role'),'| right after job_id:',/name="job_id"[\s\S]{0,400}name="x_ss_role"/.test(a));
})().catch(e=>console.error(e.message));
