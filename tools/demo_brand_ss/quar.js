const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');const L=require('./lib');
(async()=>{await login();
 const wh=(await kw('stock.warehouse','read',[[ids.W.main]],{fields:['view_location_id']}))[0];
 let q=(await kw('stock.location','search',[[['name','=','Karantina Expiry'],['company_id','=',CID]]]))[0];
 if(!q) q=await kw('stock.location','create',[{name:'Karantina Expiry',location_id:wh.view_location_id[0],usage:'internal',company_id:CID}]);
 const qids=[];
 for(const [k,name,exp,n] of [['lotion','LTN-2601Z','2027-01-10',45],['wash','FWS-2512Z','2026-12-28',30],['serum','SRM-2602Q','2027-02-05',24]]){
   const p=(await kw('product.product','search',[[['product_tmpl_id','=',ids.P[k]]]]))[0];
   const lot=await L.lot(p,name,exp);
   qids.push(await kw('stock.quant','create',[{product_id:p,location_id:q,lot_id:lot,inventory_quantity:n}],{context:{inventory_mode:true}}));
 }
 await kw('stock.quant','action_apply_inventory',[qids],{context:{inventory_mode:true,inventory_name:'Batch mendekati expired dipindah ke karantina (demo)'}});
 await kw('crm.team','write',[[ids.TM.off],{invoiced_target:20000000}]);
 console.log(await kw('stock.lot','search_read',[[['name','in',['LTN-2601Z','FWS-2512Z','SRM-2602Q']]]],{fields:['name','product_qty','alert_date']}));
})().catch(e=>console.error(e.message));
