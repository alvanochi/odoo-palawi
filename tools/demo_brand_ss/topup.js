const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');const L=require('./lib');
(async()=>{await login();
 const wh=await kw('stock.warehouse','read',[[ids.W.main,ids.W.store]],{fields:['lot_stock_id']});
 const MAIN=wh[0].lot_stock_id[0], STORE=wh[1].lot_stock_id[0];
 const prods=await kw('product.product','search_read',[[['is_storable','=',true],['sale_ok','=',true],['company_id','=',CID]]],{fields:['display_name','tracking','qty_available','product_tmpl_id']});
 const qids=[];
 for(const p of prods){
   const add = p.tracking==='lot' ? 400 : 80;
   if(p.tracking==='lot'){
     const code=p.display_name.match(/SS-(\w+)/)[1];
     const lot=await L.lot(p.id,code+'-2610X','2028-10-15');
     qids.push(await kw('stock.quant','create',[{product_id:p.id,location_id:MAIN,lot_id:lot,inventory_quantity:add}],{context:{inventory_mode:true}}));
     qids.push(await kw('stock.quant','create',[{product_id:p.id,location_id:STORE,lot_id:lot,inventory_quantity:30}],{context:{inventory_mode:true}}));
   } else {
     const q=await kw('stock.quant','search_read',[[['product_id','=',p.id],['location_id','=',MAIN]]],{fields:['quantity']});
     const cur=q.reduce((a,x)=>a+x.quantity,0);
     qids.push(await kw('stock.quant','create',[{product_id:p.id,location_id:MAIN,inventory_quantity:cur+add}],{context:{inventory_mode:true}}));
     const qs=await kw('stock.quant','search_read',[[['product_id','=',p.id],['location_id','=',STORE]]],{fields:['quantity']});
     const cs=qs.reduce((a,x)=>a+x.quantity,0);
     qids.push(await kw('stock.quant','create',[{product_id:p.id,location_id:STORE,inventory_quantity:cs+15}],{context:{inventory_mode:true}}));
   }
 }
 await kw('stock.quant','action_apply_inventory',[qids],{context:{inventory_mode:true,inventory_name:'Penerimaan hasil konveksi/maklon (demo top-up)'}});
 console.log('topped up',prods.length,'products');
})().catch(e=>{console.error(e.message);console.error((e.debug||'').slice(-800))});
