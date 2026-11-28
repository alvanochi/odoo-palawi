const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');(async()=>{await login();
const sup=(await kw('res.partner','search',[[['name','=','Toko Bahan Makanan Sumber Rejeki']]]))[0];
const m=await kw('account.move','create',[{move_type:'in_invoice',partner_id:sup,company_id:CID,invoice_date:'2026-11-28',invoice_line_ids:[[0,0,{product_id:283,quantity:1,price_unit:45000,analytic_distribution:{[String(ids.AN.prod)]:100}}],[0,0,{product_id:286,quantity:1,price_unit:75000,analytic_distribution:{[String(ids.AN.prod)]:100}}]]}]);
const l=await kw('account.move.line','search_read',[[['move_id','=',m],['display_type','=','product']]],{fields:['name','account_id','analytic_distribution','tax_ids']});
console.log(l.map(x=>[x.name,x.account_id[1],JSON.stringify(x.analytic_distribution),x.tax_ids]));
await kw('account.move','unlink',[[m]]);console.log('test bill deleted');
})().catch(e=>console.error(e.message));
