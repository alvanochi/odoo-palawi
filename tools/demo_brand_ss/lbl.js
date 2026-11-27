const {login,kw}=require('./rpc');(async()=>{await login();
const f=(await kw('ir.model.fields','search',[[['model','=','x_ss_approval'],['name','=','x_budget_remaining']]]))[0];
await kw('ir.model.fields','write',[[f],{field_description:'Sisa Budget (Rp)'}]);console.log('ok');})().catch(e=>console.error(e.message));
