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
 let researchFails=true,saves=0,guided='',plan={content:'BASE',revision:'r1',ready:true};
 const table={columns:['采用','编号','上级编号','功能名称','所需技术','前期准备'],rows:[{'采用':'是','编号':'F01','上级编号':'无','功能名称':'模块'},{'采用':'是','编号':'F01-01','上级编号':'F01','功能名称':'细项','所需技术':'建议A'}]};
 const options={storageKey:'draft',notice:(...n)=>notices.push(n),getPlan:()=>plan,setBusy:v=>workflow.setBusy(v),guide:t=>guided=t,onSave:async c=>{saves++;plan.content=c;},request:async(route,payload)=>{
  calls.push({route,payload});if(route==='/api/research'&&!payload)return{completed:false,repositories:[]};
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
 await $('save-feature-edit').handlers.click();
 const written=calls.find(c=>c.payload?.rows);assert.equal(written.payload.rows[1]['所需技术'],'用户指定SQLite');assert.equal(saves,1);assert.equal(storage.has('draft'),false);
 $('new-feature-idea').value='增加库存';$('guide-feature').handlers.click();assert.match(guided,/增加库存/);assert.equal(saves,1,'decomposition does not save a proposal');
 await $('edit-features').handlers.click();plan.revision='r2';await $('save-feature-edit').handlers.click();assert.match(notices.at(-1)[0],/已经变化/);assert.equal(saves,1,'stale editor cannot overwrite');
 console.log('Planning workflow: research failure/retry/cache, edited fields, adoption cascade, guided proposals and conflict retention passed.');
}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
