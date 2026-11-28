const {login,kw}=require('./rpc');(async()=>{await login();
const M=(await kw('ir.model','search',[[['model','=','x_ss_approval']]]))[0];
if(!(await kw('ir.model.fields','search_count',[[['model_id','=',M],['name','=','x_is_my_turn']]])))
 await kw('ir.model.fields','create',[{model_id:M,state:'manual',name:'x_is_my_turn',field_description:'Giliran Saya Menyetujui',ttype:'boolean',store:false,readonly:true,depends:'',
  compute:"for rec in self:\n    u = rec.env.user\n    rec['x_is_my_turn'] = rec.x_state == 'submitted' and (u == rec.x_approver_id or u.has_group('base.group_system'))"}]);
const v=(await kw('ir.ui.view','search_read',[[['name','=','x_ss_approval.form']]],{fields:['arch_db']}))[0];
let a=v.arch_db;
for(const s of ['string="Setujui"','string="Kembalikan untuk Revisi"','string="Tolak"']){
  const re=new RegExp('(<button[^>]*'+s+'[^>]*?)invisible="x_state != \'submitted\'"');
  a=a.replace(re,'$1invisible="not x_is_my_turn"');
}
if(!a.includes('name="x_is_my_turn"')) a=a.replace('<field name="x_state" widget="statusbar"','<field name="x_is_my_turn" invisible="1"/>\n    <field name="x_state" widget="statusbar"');
await kw('ir.ui.view','write',[[v.id],{arch_db:a}]);
console.log((a.match(/invisible="not x_is_my_turn"/g)||[]).length,'buttons now restricted');
})().catch(e=>console.error(e.message));
