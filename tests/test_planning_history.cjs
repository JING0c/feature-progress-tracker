const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Node{
 constructor(){this.children=[];this.handlers={};this.attributes={};this.value='';this.disabled=false;this.hidden=true;}
 append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,f){this.handlers[k]=f;}scrollIntoView(){}click(){this.clicked=true;}remove(){}
}
function dom(){const nodes=new Map();return{nodes,$:id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},document:{createElement:()=>new Node(),body:new Node()}};}
const descendants=n=>[n,...n.children.flatMap(descendants)];
async function references(){
 const d=dom();d.document.getElementById=d.$;const calls=[],notices=[];let fail=false,resumed=0,workflow;
 const result={completed:true,selection_confirmed:false,revision:'r1',repositories:['a/one','b/two','c/three'].map(name=>({name,url:'https://github.com/'+name,selected:false}))};
 const sandbox={window:{},document:d.document,localStorage:{getItem(){return null;}},confirm:()=>true};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../scripts/planning-workflow.js'),'utf8'),sandbox);
 workflow=sandbox.window.createPlanningWorkflow({storageKey:'x',getPlan:()=>({}),notice:(m)=>notices.push(m),setBusy:b=>workflow.setBusy(b),resumePlanning:()=>resumed++,request:async(route,payload)=>{
  calls.push({route,payload});if(!payload)return JSON.parse(JSON.stringify(result));if(fail)throw Error('调研结果已变化');
  return{...result,revision:'r2',selection_confirmed:true,repositories:result.repositories.map(r=>({...r,selected:payload.selected.includes(r.name)}))};
 }});
 await assert.rejects(()=>workflow.ensureResearch('need'),/请选择要参考的项目/);
 const field=name=>descendants(d.$('research-results')).find(n=>n.attributes['aria-label']==='参考 '+name);
 for(const name of ['a/one','c/three']){field(name).checked=true;field(name).handlers.change();}
 await d.$('save-reference-selection').handlers.click();
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1).payload)),{revision:'r1',selected:['a/one','c/three']});assert.equal(resumed,1);await workflow.ensureResearch('next');
 field('a/one').checked=false;field('a/one').handlers.change();fail=true;await d.$('save-reference-selection').handlers.click();
 assert.equal(field('a/one').checked,false);assert.equal(field('c/three').checked,true);assert.equal(resumed,1);await assert.rejects(()=>workflow.ensureResearch('next'),/请选择要参考的项目/);
 fail=false;field('c/three').checked=false;field('c/three').handlers.change();await d.$('save-reference-selection').handlers.click();assert.equal(calls.at(-1).payload.selected.length,0);await workflow.ensureResearch('none');
}
async function history(){
 const d=dom();d.document.getElementById=d.$;const calls=[],downloads=[],blobs=[];let model,staleResolve;
 const sandbox={window:{},document:d.document,createPlanningSheetView:()=>({show:m=>model=m}),renderPlanningMarkdown:(n,c)=>n.textContent=c,Blob,URL:{createObjectURL:b=>{blobs.push(b);return'blob:old';},revokeObjectURL(){}},setTimeout(){}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../scripts/planning-history-view.js'),'utf8'),sandbox);
 const version={id:'v-old',saved_at:'2026-11-02T12:00:00Z',source:'功能表编辑',note:'保留库存',references:[{name:'org/repo'}],content:'# OLD',model:{sheets:[]},diff:'- before\n+ after'};
 sandbox.window.createPlanningHistoryView({downloadExcel:async(...args)=>downloads.push(args),request:async route=>{
  calls.push(route);if(route==='/api/plan/history')return{versions:[version,{...version,id:'v-stale'}]};if(route.endsWith('v-stale'))return new Promise(resolve=>staleResolve=resolve);return version;
 }});
 await d.$('open-plan-history').handlers.click();const buttons=()=>descendants(d.$('history-list')).filter(n=>n.handlers.click);
 await buttons()[0].handlers.click();assert.equal(d.$('history-document').textContent,'# OLD');assert.equal(d.$('history-diff').textContent,version.diff);assert.equal(model,version.model);assert.equal(d.$('history-detail').hidden,false);
 await d.$('history-download-excel').handlers.click();assert.deepEqual(downloads,[['# OLD','v-old.xlsx']]);d.$('history-download-md').handlers.click();assert.equal(await blobs[0].text(),'# OLD');
 const stale=buttons()[1].handlers.click();await d.$('open-plan-history').handlers.click();staleResolve({...version,content:'STALE'});await stale;assert.equal(d.$('history-document').textContent,'# OLD','late detail cannot overwrite a reopened history list');
 assert.ok(calls.every(route=>route.startsWith('/api/plan/history')),'history never writes current plan');
}
async function run(){await references();await history();console.log('References/history UI: multiselect, none, conflict retention, intent resume callback, readonly snapshots, exports and stale response checks passed.');}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
