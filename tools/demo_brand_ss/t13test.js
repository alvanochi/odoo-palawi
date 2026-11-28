const {SA}=require('./approval_ids.json');const ids=require('./ids.json');
const URL='https://palawi.rutekebangsaan.com',CID=13;
class S{constructor(l,p){this.l=l;this.p=p;this.c=''}async post(path,params){const r=await fetch(URL+path,{method:'POST',headers:{'Content-Type':'application/json',Cookie:this.c},body:JSON.stringify({jsonrpc:'2.0',method:'call',params})});const sc=r.headers.get('set-cookie');if(sc)this.c=sc.split(';')[0];const j=await r.json();if(j.error)throw new Error(`[${this.l}] `+(j.error.data&&j.error.data.message||j.error.message));return j.result}
async auth(){const r=await this.post('/web/session/authenticate',{db:'odoo18_palawi',login:this.l,password:this.p});this.uid=r.uid;return this}
kw(m,me,a=[],k={}){k=Object.assign({},k);k.context=Object.assign({allowed_company_ids:[CID]},k.context||{});return this.post('/web/dataset/call_kw',{model:m,method:me,args:a,kwargs:k})}
run(sa,id){return this.post('/web/action/run',{action_id:sa,context:{active_model:'x_ss_approval',active_id:id,active_ids:[id],allowed_company_ids:[CID]}})}}
(async()=>{const PW=process.env.DEMO_PW;
 const reza=await new S('ss.reza',PW).auth(), dewi=await new S('ss.dewi',PW).auth(), shella=await new S('ss.shella',PW).auth(), admin=await new S('admin',process.env.ODOO_PASSWORD).auth();
 const rd=async id=>(await admin.kw('x_ss_approval','read',[[id]],{fields:['x_state','x_approval_path','x_approver_id','x_chain','x_over_budget']}))[0];
 const made=[];
 try{
  // 1) payment Rp 15jt by Reza (no budget acct): rules -> Atasan(Shella), Pembayaran Finance(Dewi), Finance>=10jt(Dewi) => Shella -> Dewi
  let id=await reza.kw('x_ss_approval','create',[{x_name:'TEST rules 1',x_type:'pembayaran',x_amount:15000000,x_company_id:CID,x_requester_id:reza.uid,x_state:'draft'}]);made.push(id);
  await reza.run(SA.submit,id);console.log('T1 submitted',await rd(id));
  await shella.run(SA.approve,id);console.log('T1 after Shella',await rd(id));
  await dewi.run(SA.approve,id);console.log('T1 after Dewi',await rd(id));
  // 2) campaign Rp 2jt on marketing budget (over) -> Atasan(Shella) + Direksi(Shella) dedupe => Shella only
  id=await reza.kw('x_ss_approval','create',[{x_name:'TEST rules 2',x_type:'campaign',x_amount:2000000,x_analytic_id:ids.AN.mkt,x_company_id:CID,x_requester_id:reza.uid,x_state:'draft'}]);made.push(id);
  await reza.run(SA.submit,id);console.log('T2 submitted',await rd(id));
  // 3) legacy chain format still approvable
  id=await admin.kw('x_ss_approval','create',[{x_name:'TEST legacy',x_type:'kantor',x_amount:1000000,x_company_id:CID,x_requester_id:reza.uid,x_state:'submitted',x_chain:'finance:'+dewi.uid,x_step:0,x_approver_id:dewi.uid}]);made.push(id);
  await dewi.run(SA.approve,id);console.log('T3 legacy after Dewi',await rd(id));
 } finally { if(made.length) await admin.kw('x_ss_approval','unlink',[made]); console.log('cleaned',made.length); }
})().catch(e=>console.error('FAIL',e.message));
