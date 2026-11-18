const {login,kw,CID}=require('./rpc');
const ids=require('./ids.json');
(async()=>{await login();
 const loc=await kw('stock.location','search_read',[[['usage','=','inventory'],['company_id','=',CID]]],{fields:['name','valuation_in_account_id','valuation_out_account_id']});
 console.log(loc);
 const hist=(await kw('account.account','search',[[['code','=','39000000'],['company_ids','in',[CID]]]]))[0];
 for(const l of loc) await kw('stock.location','write',[[l.id],{valuation_in_account_id:hist,valuation_out_account_id:hist}]);
 const {W,P}=ids;
 const wh=await kw('stock.warehouse','read',[[W.main,W.store]],{fields:['lot_stock_id']});
 const MAIN=wh[0].lot_stock_id[0], STORE=wh[1].lot_stock_id[0];
 // removal strategy FEFO for beauty category
 const fefo=(await kw('product.removal','search',[[['method','=','fefo']]]))[0];
 await kw('product.category','write',[[ids.C.beauty],{removal_strategy_id:fefo}]);
 const quants=[];
 const R=(a,b)=>a+Math.floor(Math.random()*(b-a+1));
 // raw materials
 const rmq={kain_wolfis:900,kain_silk:400,label:3000,botol30:1500,tube_lip:1200,bottle250:500,tube100:800,base_serum:30,base_lip:6,base_lotion:80,base_wash:60};
 for(const [k,q] of Object.entries(rmq)){const p=(await kw('product.product','search',[[['product_tmpl_id','=',P[k]]]]))[0];quants.push({product_id:p,location_id:MAIN,inventory_quantity:q});}
 // fashion variants
 for(const k of ['gamis','tunik','pashmina']){
  const vs=await kw('product.product','search_read',[[['product_tmpl_id','=',P[k]]]],{fields:['default_code']});
  for(const v of vs){quants.push({product_id:v.id,location_id:MAIN,inventory_quantity:R(25,70)});
    quants.push({product_id:v.id,location_id:STORE,inventory_quantity:R(3,10)});}
 }
 // beauty lots
 const lots={serum:[['SRM-2603A','2027-01-20',60],['SRM-2607B','2028-07-15',380]],lip:[['LIP-2606A','2028-06-10',320]],lotion:[['LTN-2605A','2028-05-01',140]],wash:[['FWS-2606A','2028-06-20',220]]};
 for(const [k,ls] of Object.entries(lots)){
  const p=(await kw('product.product','search',[[['product_tmpl_id','=',P[k]]]]))[0];
  for(const [name,exp,q] of ls){
    let lot=(await kw('stock.lot','search',[[['name','=',name],['product_id','=',p],['company_id','=',CID]]]))[0];
    if(!lot) lot=await kw('stock.lot','create',[{name,product_id:p,company_id:CID,expiration_date:exp+' 00:00:00'}]);
    quants.push({product_id:p,location_id:MAIN,lot_id:lot,inventory_quantity:q});
    quants.push({product_id:p,location_id:STORE,lot_id:lot,inventory_quantity:Math.round(q*0.05)+2});
  }
 }
 const qids=[];
 for(const q of quants){const id=await kw('stock.quant','create',[q],{context:{inventory_mode:true}}); qids.push(id);}
 await kw('stock.quant','action_apply_inventory',[qids],{context:{inventory_mode:true,inventory_name:'Saldo Awal Stok Brand SS (Demo)'}});
 const val=await kw('stock.quant','read_group',[[['company_id','=',CID],['location_id.usage','=','internal']],['value:sum','quantity:sum'],[]]).catch(e=>e.message);
 console.log('quants',qids.length,val);
})().catch(e=>{console.error(e.message);console.error((e.debug||'').slice(-1500))});
