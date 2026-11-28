const {login,kw,CID}=require('./rpc');
async function gid(x){const [m,n]=x.split('.');return (await kw('ir.model.data','check_object_reference',[m,n]))[1];}
(async()=>{await login();
 const groups=[];
 for(const x of ['base.group_user','hr.group_hr_manager','hr_contract.group_hr_contract_manager','hr_attendance.group_hr_attendance_manager','hr_holidays.group_hr_holidays_manager','om_hr_payroll.group_hr_payroll_manager','hr_expense.group_hr_expense_manager','project.group_project_user']) groups.push(await gid(x));
 for(const n of ['SS Approval / Pengguna','SS Demo / Kontak hanya PT ShellaSaukia']) groups.push((await kw('res.groups','search',[[['name','=',n]]]))[0]);
 let u=(await kw('res.users','search',[[['login','=','ss.rina']]],{context:{active_test:false}}))[0];
 if(!u) u=await kw('res.users','create',[{name:'Rina Kartika',login:'ss.rina',email:'ss.rina@demo.invalid',notification_type:'inbox',company_id:CID,company_ids:[[6,0,[CID]]],groups_id:[[6,0,groups]],tz:'Asia/Jakarta'}],{context:{no_reset_password:true}});
 else await kw('res.users','write',[[u],{groups_id:groups.map(g=>[4,g])}]);
 await kw('res.users','write',[[u],{password:process.env.DEMO_PW}]);
 const up=(await kw('res.users','read',[[u]],{fields:['partner_id']}))[0].partner_id[0];
 await kw('res.partner','write',[[up],{company_id:CID}]);
 const emp=(await kw('hr.employee','search_read',[[['name','=','Rina Kartika'],['company_id','=',CID]]],{fields:['work_contact_id']}))[0];
 const dup=await kw('hr.employee','search',[[['user_id','=',u],['id','!=',emp.id]]]);
 if(dup.length) await kw('hr.employee','write',[dup,{user_id:false,active:false}]);
 const oldWc=emp.work_contact_id&&emp.work_contact_id[0];
 await kw('hr.employee','write',[[emp.id],{user_id:u,work_contact_id:up}]);
 if(oldWc&&oldWc!==up) await kw('res.partner','write',[[oldWc],{active:false}]).catch(()=>{});
 // HR manager handles leave approvals for the HR dept staff + is HR responsible on leave types
 const t=await kw('hr.leave.type','search',[[['company_id','=',CID]]]);
 await kw('hr.leave.type','write',[t,{responsible_ids:[[4,u]]}]).catch(e=>console.log('leave resp',e.message));
 console.log('ss.rina',u,'employee',emp.id);
})().catch(e=>console.error(e.message));
