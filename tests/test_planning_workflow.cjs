const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Node{
 constructor(){this.children=[];this.handlers={};this.attributes={};this.value='';this.disabled=false;this.hidden=false;}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,fn){this.handlers[k]=fn;}scrollIntoView(){}
}
async function run(){
 const nodes=new Map(),storage=new Map(),calls=[],notices=[];const $=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const source=fs.readFileSync(path.join(__dirname,'../scripts/planning-workflow.js'),'utf8');
 const sandbox={window:{},document:{getElementById:$,createElement:()=>new Node()},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},confirm:()=>true};
 vm.runInNewContext(source,sandbox);
 let researchFails=true,saves=0,guided='',guidedFromReferences=false,plan={content:'BASE',revision:'r1',ready:true};
 const table={reserved_ids:['F01-02','F05'],columns:['采用','编号','上级编号','功能名称','所需技术','前期准备'],rows:[{'采用':'是','编号':'F01','上级编号':'无','功能名称':'模块'},{'采用':'是','编号':'F01-01','上级编号':'F01','功能名称':'细项','所需技术':'建议A'}]};
 const options={storageKey:'draft',notice:(...n)=>notices.push(n),getPlan:()=>plan,setBusy:v=>workflow.setBusy(v),guide:(t,fromReferences)=>{guided=t;guidedFromReferences=fromReferences;},onSave:async c=>{saves++;plan.content=c;},request:async(route,payload)=>{
  calls.push({route,payload});if(route==='/api/research'&&!payload)return{completed:false,repositories:[]};
  if(route==='/api/research/selection')return{completed:true,selection_confirmed:true,feature_idea:'增加库存',query:'inventory',repositories:[]};
  if(route==='/api/research'&&payload.feature_idea)return{completed:true,selection_confirmed:false,feature_idea:payload.feature_idea,query:'inventory',repositories:[]};
  if(route==='/api/research'){if(researchFails)throw Error('GitHub rate limit');return{completed:true,selection_confirmed:true,query:'ticket',repositories:[{name:'org/repo',url:'https://github.com/org/repo',description:'资料',license:'MIT',stars:1}]};}
  if(payload.rows)return{content:'UPDATED'};
  return JSON.parse(JSON.stringify(table));
 }};
 let workflow=sandbox.window.createPlanningWorkflow(options);
 await assert.rejects(()=>workflow.ensureResearch('需求'),/rate limit/);
 researchFails=false;await workflow.ensureResearch('需求');
 const count=calls.length;await workflow.ensureResearch('第二条消息');assert.equal(calls.length,count,'successful research is reused');
 await $('edit-features').handlers.click();assert.equal(workflow.editing,true);
 const fields=()=>{const visit=n=>[n,...n.children.flatMap(visit)];return visit($('feature-editor-table'));};
 const field=name=>fields().find(n=>n.attributes['aria-label']===name);
 field('F01-01 所需技术').value='用户指定SQLite';field('F01-01 所需技术').handlers.input();assert.ok(storage.has('draft'));
 field('采用 F01').checked=false;field('采用 F01').handlers.change();
 assert.equal(field('采用 F01-01').checked,false,'editor parent checkbox cascades');
 field('采用 F01-01').checked=true;field('采用 F01-01').handlers.change();assert.equal(field('采用 F01').checked,true,'child restores ancestor');
 field('新增子功能 F01-01').handlers.click();assert.ok(field('F01-01-01 功能名称'),'nested child added without a model');
 field('F01-01-01 功能名称').value='更细功能';field('F01-01-01 功能名称').handlers.input();
 field('删除功能 F01-01-01').handlers.click();assert.ok(!field('F01-01-01 功能名称'),'delete is staged in editor');
 field('新增子功能 F01-01').handlers.click();assert.ok(field('F01-01-02 功能名称'),'deleted ID is never reused');field('删除功能 F01-01-02').handlers.click();
 field('新增子功能 F01').handlers.click();assert.ok(field('F01-03 功能名称'),'ledger IDs remain reserved');field('删除功能 F01-03').handlers.click();
 await $('save-feature-edit').handlers.click();
 const written=calls.find(c=>c.payload?.rows);assert.equal(written.payload.rows[1]['所需技术'],'用户指定SQLite');assert.equal(saves,1);assert.equal(storage.has('draft'),false);
 $('new-feature-idea').value='增加库存';$('guide-feature').handlers.click();assert.match(guided,/增加库存/);assert.equal(saves,1,'decomposition does not save a proposal');
 guided='';await $('research-feature').handlers.click();
 assert.equal(calls.at(-1).payload.feature_idea,'增加库存');
 assert.equal(calls.at(-1).payload.query,undefined,'feature search must ignore the old project keyword');
 assert.equal(guided,'','decomposition waits for selection');
 $('research-query').value='stock audit';
 await $('search-references').handlers.click();
 assert.equal(calls.at(-1).payload.feature_idea,'增加库存','keyword refinement retains the feature scope');
 assert.equal(calls.at(-1).payload.query,'stock audit');
 $('new-feature-idea').value='另一个未搜索的需求';
 await $('save-reference-selection').handlers.click();
 assert.match(guided,/增加库存/);assert.equal(guidedFromReferences,true);
 assert.equal(saves,1,'reference-assisted proposal is also read-only');

 await $('edit-features').handlers.click();plan.revision='r2';await $('save-feature-edit').handlers.click();assert.match(notices.at(-1)[0],/已经变化/);assert.equal(saves,1,'stale editor cannot overwrite');
 console.log('Planning workflow: research failure/retry/cache, edited fields, adoption cascade, guided proposals and conflict retention passed.');
}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
