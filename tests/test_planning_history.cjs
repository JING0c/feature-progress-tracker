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
 let closed=0;
 const controller=sandbox.window.createPlanningHistoryView({onClose:()=>closed++,downloadExcel:async(...args)=>downloads.push(args),request:async route=>{
  calls.push(route);if(route.endsWith('v-stale'))return new Promise(resolve=>staleResolve=resolve);if(route.endsWith('v-missing'))throw Error('历史版本不存在');return version;
 }});
 await controller.show('v-old');assert.equal(d.$('history-document').textContent,'# OLD');assert.equal(d.$('history-diff').textContent,version.diff);assert.equal(model,version.model);assert.equal(d.$('history-detail').hidden,false);
 assert.doesNotMatch(d.$('history-title').textContent,/v-old/,'internal IDs are not the user title');assert.match(d.$('history-title').textContent,/功能表/);
 await d.$('history-download-excel').handlers.click();assert.equal(downloads[0][0],'# OLD');assert.match(downloads[0][1],/^功能表-.*\.xlsx$/);d.$('history-download-md').handlers.click();assert.equal(await blobs[0].text(),'# OLD');
 const stale=controller.show('v-stale');await d.$('history-back').handlers.click();staleResolve({...version,content:'STALE'});await stale;assert.equal(d.$('plan-history').hidden,true,'late detail cannot reopen after back');assert.equal(closed,1);
 await controller.show('v-missing');assert.equal(d.$('history-detail').hidden,true,'failed read cannot leave previous export actions visible');assert.match(d.$('history-status').textContent,/不存在/);
 version.warnings=['上次保存的功能表无法读取，暂时不能比较改动。'];await controller.show('v-old');assert.match(d.$('history-status').textContent,/无法读取/);assert.equal(d.$('history-detail').hidden,false);
 assert.ok(calls.every(route=>route.startsWith('/api/plan/history')),'history never writes current plan');
}
async function run(){await references();await history();console.log('References/history UI: multiselect, none, conflict retention, intent resume callback, readonly snapshots, exports and stale response checks passed.');}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
