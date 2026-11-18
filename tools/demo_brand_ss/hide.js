const {login,kw}=require('./rpc');(async()=>{await login();
const g=(await kw('res.groups','search',[[['name','=','SS Approval / Pengguna']]]))[0];
for(const [mid,name] of [[533,'Rest API'],[693,'Marketing Order'],[15,'Apps'],[200,'Dashboards']]){
  const ex=await kw('menu.visibility.rule','search',[[['menu_id','=',mid],['note','like','Brand SS demo']]]);
  if(ex.length){console.log('exists',name);continue;}
  await kw('menu.visibility.rule','create',[{menu_id:mid,apply_to:'groups',group_ids:[[6,0,[g]]],note:'Brand SS demo: sembunyikan menu PALAWI/admin dari user ss.*'}]);
  console.log('hidden for SS users:',name);
}})().catch(e=>console.error(e.message));
