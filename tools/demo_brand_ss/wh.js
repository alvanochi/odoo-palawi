const {login,kw}=require('./rpc');const ids=require('./ids.json');
(async()=>{await login();await kw('stock.warehouse','write',[[ids.W.main],{delivery_steps:process.argv[2]}]);
console.log(await kw('stock.warehouse','read',[[ids.W.main]],{fields:['delivery_steps']}));})().catch(e=>console.error(e.message));
