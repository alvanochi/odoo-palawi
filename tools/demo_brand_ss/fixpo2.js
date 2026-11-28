const {login,kw}=require('./rpc');const {SA}=require('./approval_ids.json');(async()=>{await login();
let c=(await kw('ir.actions.server','read',[[SA.make_po]],{fields:['code']}))[0].code;
const old="'order_line': [(0, 0, {'product_id': l.x_product_id.id, 'product_qty': l.x_qty, 'price_unit': l.x_price}) for l in rec.x_line_ids]";
if(c.includes(old)){
 c=c.replace("    po = env['purchase.order'].create(","    dist = {str(rec.x_analytic_id.id): 100} if rec.x_analytic_id else False\n    po = env['purchase.order'].create(")
    .replace(old,"'order_line': [(0, 0, {'product_id': l.x_product_id.id, 'product_qty': l.x_qty, 'price_unit': l.x_price, 'analytic_distribution': dist}) for l in rec.x_line_ids]");
 await kw('ir.actions.server','write',[[SA.make_po],{code:c}]);console.log('patched');
} else console.log(c.includes('analytic_distribution')?'already patched':'pattern not found');
})().catch(e=>console.error(e.message));
