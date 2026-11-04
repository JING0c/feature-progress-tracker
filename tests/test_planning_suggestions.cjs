const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {constructor(){this.children=[];this.handlers={};this.value='';this.hidden=false;}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}addEventListener(k,f){this.handlers[k]=f;}setAttribute(){}}
async function run(){
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const calls=[],notices=[];let preview=null,state={revision:'r1',ready:true,dirty:false},view;
 const data={id:'batch',plan_revision:'r1',suggestions:[{id:'S01',title:'异常处理',reason:'边界缺失',changes:[{action:'update',id:'F01',fields:{说明:'重试'}}]}]};
 const sandbox={window:{},document:{getElementById:$,createElement:()=>new Node()},setInterval(){return 1;},clearInterval(){}};
 vm.runInNewContext(fs.readFileSync('scripts/planning-suggestions.js','utf8'),sandbox);
 view=sandbox.window.createPlanningSuggestions({getPlan:()=>state,setBusy:v=>view.setBusy(v),onPreview:d=>{preview=d;state.dirty=true;},request:async(route,payload)=>{calls.push({route,payload});return route.endsWith('/preview')?{content:'PREVIEW',revision:'r1',diff:'+ retry'}:data;}});
 await new Promise(r=>setImmediate(r));
 const check=$('suggestions-list').children[0].children[0].children[0];assert.equal(check.checked,false);assert.equal($('preview-suggestions').disabled,true);
 check.checked=true;check.handlers.change();assert.equal($('preview-suggestions').disabled,false);
 await $('preview-suggestions').handlers.click();assert.equal(preview.content,'PREVIEW');assert.equal(preview.changedIds.join(','),'F01');assert.equal($('suggestion-diff').hidden,false);assert.ok(!calls.some(c=>c.route.endsWith('/save')),'preview must never save');
 assert.equal($('preview-suggestions').disabled,true);await $('generate-suggestions').handlers.click();assert.match($('suggestions-status').textContent,/先保存/);
 state={revision:'r2',ready:true,dirty:false};view.setBusy(false);assert.equal(check.disabled,true);assert.match($('suggestions-status').textContent,/过期/);
 state.revision='r1';view.setBusy(false);assert.equal(check.disabled,false);assert.doesNotMatch($('suggestions-status').textContent,/过期/);state.revision='r2';
 $('suggestions-focus').value=' 边界 ';await $('generate-suggestions').handlers.click();assert.equal(calls.at(-1).payload.focus,'边界');assert.equal(calls.at(-1).payload.revision,'r2');assert.equal($('suggestions-progress').hidden,true);
 console.log('Suggestions: explicit selection, preview without save, dirty guard, stale revision, generation progress passed.');
}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
