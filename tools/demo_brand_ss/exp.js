const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');const L=require('./lib');
(async()=>{await login();
 const wh=await kw('stock.warehouse','read',[[ids.W.main]],{fields:['lot_stock_id']});
 const qids=[];
 for(const [k,name,exp,q] of [['lotion','LTN-2601Z','2027-01-10',45],['wash','FWS-2512Z','2026-12-28',30]]){
  const p=(await kw('product.product','search',[[['product_tmpl_id','=',ids.P[k]]]]))[0];
  const lot=await L.lot(p,name,exp);
  qids.push(await kw('stock.quant','create',[{product_id:p,location_id:wh[0].lot_stock_id[0],lot_id:lot,inventory_quantity:q}],{context:{inventory_mode:true}}));
 }
 await kw('stock.quant','action_apply_inventory',[qids],{context:{inventory_mode:true,inventory_name:'Retur gudang reseller - batch lama (demo)'}});
 console.log(await kw('stock.lot','search_read',[[['name','in',['LTN-2601Z','FWS-2512Z']]]],{fields:['name','alert_date','product_qty']}));
})().catch(e=>console.error(e.message));
