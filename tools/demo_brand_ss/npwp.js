const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');
// NPWP 15 digit: 9th digit = Luhn check of first 8; 16-digit form = '0' + 15 digits
function luhnDigit(s){let sum=0;for(let i=0;i<s.length;i++){let d=+s[s.length-1-i];if(i%2===0){d*=2;if(d>9)d-=9;}sum+=d;}return (10-sum%10)%10;}
function npwp(base8,tail6){return '0'+base8+luhnDigit(base8)+tail6;}
(async()=>{await login();
 const comp=npwp('01234567','015000');
 await kw('res.company','write',[[CID],{vat:comp}]);console.log('company NPWP',comp);
 const parts=[['res_aisyah','71234560','421000'],['res_medan','81234561','121000'],['dist_sby','91234562','615000']];
 for(const [k,b,t] of parts){const v=npwp(b,t);await kw('res.partner','write',[[ids.R[k]],{vat:v,l10n_id_pkp:true,l10n_id_kode_transaksi:'04'}]).then(()=>console.log(k,v)).catch(e=>console.log(k,'ERR',e.message));}
 const tab=(await kw('res.partner','search',[[['name','ilike','Tanah Abang'],['company_id','=',CID]]]))[0];
 const v=npwp('61234563','073000');await kw('res.partner','write',[[tab],{vat:v,l10n_id_pkp:true,l10n_id_kode_transaksi:'04'}]).then(()=>console.log('tanah abang',v)).catch(e=>console.log('tab ERR',e.message));
 // test download on one posted distributor invoice
 const inv=(await kw('account.move','search_read',[[['partner_id','=',ids.R.dist_sby],['move_type','=','out_invoice'],['state','=','posted']]],{fields:['name','l10n_id_kode_transaksi','l10n_id_coretax_efaktur_available'],limit:1,order:'id desc'}))[0];
 console.log('invoice',inv);
 const sa=(await kw('ir.actions.server','search',[[['name','=','Download e-Faktur']]]))[0];
 const r=await kw('ir.actions.server','run',[[sa]],{context:{active_model:'account.move',active_ids:[inv.id],active_id:inv.id,allowed_company_ids:[CID]}}).catch(e=>({err:e.message,dbg:(e.debug||'').split(String.fromCharCode(10)).filter(l=>l.includes('File')).slice(-3).join(' | ')}));
 console.log('download result',JSON.stringify(r).slice(0,400));
 console.log((await kw('account.move','read',[[inv.id]],{fields:['l10n_id_coretax_document']}))[0]);
})().catch(e=>console.error(e.message));
