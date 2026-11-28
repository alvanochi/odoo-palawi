const {login,kw,CID}=require('./rpc');const ids=require('./ids.json');
async function foc(model, domain, vals) { const r = await kw(model, 'search', [domain], { limit: 1, context:{active_test:false} }); return r.length ? r[0] : kw(model, 'create', [vals]); }
(async()=>{await login();
 const tagIds={};
 for(const t of ['SS Komplain Produk','SS Pengiriman','SS Retur/Refund','SS Pertanyaan','SS KOL','SS Affiliate','SS TikTok','SS Instagram','SS Urgent'])
   tagIds[t]=await foc('project.tags',[['name','=',t]],{name:t});
 async function project(name, stages, tasks, color, desc){
   const p=await foc('project.project',[['name','=',name],['company_id','=',CID]],{name,company_id:CID,user_id:265,color,description:desc||false});
   const st={};let seq=1;
   for(const s of stages){let id=(await kw('project.task.type','search',[[['name','=',s],['project_ids','in',[p]]]]))[0];
     if(!id) id=await kw('project.task.type','create',[{name:s,sequence:seq,project_ids:[[6,0,[p]]],fold:/Selesai|Closed|Tayang & Dievaluasi/.test(s)}]); st[s]=id; seq++;}
   for(const [tn,stage,deadline,prio,d,tags] of tasks){
     if(await kw('project.task','search_count',[[['name','=',tn],['project_id','=',p]]])) continue;
     await kw('project.task','create',[{name:tn,project_id:p,stage_id:st[stage],date_deadline:deadline,priority:prio?'1':'0',description:d||false,tag_ids:[[6,0,(tags||[]).map(t=>tagIds[t])]],user_ids:[[6,0,[265]]],company_id:CID}]);
   }
 }
 await project('SS - Customer Service (Tiket)',['Tiket Baru','Diproses','Menunggu Pelanggan','Eskalasi','Selesai'],[
  ['#CS-1041 Serum bocor saat diterima (TTS-5780318...)','Diproses','2026-11-19 10:00:00',true,'Channel: TikTok Shop. Solusi: kirim ulang + klaim ke ekspedisi.',['SS Komplain Produk','SS Retur/Refund','SS TikTok']],
  ['#CS-1042 Paket belum sampai 5 hari (Shopee)','Menunggu Pelanggan','2026-11-19 12:00:00',false,'Menunggu konfirmasi alamat dari pembeli.',['SS Pengiriman']],
  ['#CS-1043 Ukuran gamis kekecilan, minta tukar size','Tiket Baru','2026-11-20 10:00:00',false,'',['SS Retur/Refund']],
  ['#CS-1038 Iritasi setelah pakai lip cream','Eskalasi','2026-11-17 10:00:00',true,'Eskalasi ke R&D + QC. Cek batch LIP-2610B. TERLAMBAT SLA.',['SS Komplain Produk','SS Urgent']],
  ['#CS-1035 Tanya cara pakai serum + niacinamide','Selesai','2026-11-15 10:00:00',false,'Selesai dalam 15 menit.',['SS Pertanyaan']],
  ['#CS-1031 Refund pesanan dobel','Selesai','2026-11-12 10:00:00',false,'Refund diproses via Shopee.',['SS Retur/Refund']],
 ],2,'Sistem tiket CS sederhana memakai Project (Helpdesk hanya di Enterprise).');
 await project('SS - Campaign, KOL & Affiliate',['Perencanaan Campaign','Approval Budget','Brief ke KOL','Produksi Konten','Jadwal Posting','Tayang & Dievaluasi'],[
  ['Campaign 12.12 - Glow Serum (budget Rp 35 jt)','Approval Budget','2026-11-25 10:00:00',true,'Target penjualan Rp 250 jt, ROAS target 6x. Menunggu approval direksi.',['SS TikTok']],
  ['KOL @glowwithkirana - video review serum (Rp 5 jt)','Jadwal Posting','2026-11-21 19:00:00',true,'Kontrak: 1 video TikTok + 3 story. Link affiliate: SSKIRANA.',['SS KOL','SS TikTok']],
  ['KOL @nadyahijabstyle - OOTD gamis Ramadhan (Rp 3,5 jt)','Produksi Konten','2026-11-24 19:00:00',false,'',['SS KOL','SS Instagram']],
  ['Affiliate program - 120 affiliator aktif, komisi 10%','Tayang & Dievaluasi','2026-11-30 10:00:00',false,'Komisi Okt: Rp 2,38 jt. Penjualan affiliate tercatat dengan tag "SS Affiliate" di sales order.',['SS Affiliate']],
  ['KOL @dailyoutfit.ayu - Tunik daily (Rp 2,5 jt)','Tayang & Dievaluasi','2026-10-24 19:00:00',false,'Hasil: 85rb views, 63 order (ROAS 5,1x).',['SS KOL','SS TikTok']],
 ],9,'Database & jadwal KOL/affiliate. Biaya fee tercatat di akun 61200030/61200040 (analytic DIV - Digital Marketing).');
 // tag KOL partners
 const cat=await foc('res.partner.category',[['name','=','SS KOL / Influencer']],{name:'SS KOL / Influencer'});
 const kols=await kw('res.partner','search',[[['name','like','KOL - '],['company_id','=',CID]]]);
 await kw('res.partner','write',[kols,{category_id:[[4,cat]]}]);
 console.log('ok');
})().catch(e=>{console.error(e.message);console.error((e.debug||'').slice(-800))});
