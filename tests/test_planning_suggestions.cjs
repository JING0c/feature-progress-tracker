const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {constructor(){this.children=[];this.handlers={};this.value='';this.hidden=false;}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}addEventListener(k,f){this.handlers[k]=f;}setAttribute(){}}
async function run(){
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const calls=[],notices=[];let failGenerate=false,preview=null,state={revision:'r1',ready:true,dirty:false},view;
 const data={id:'batch',plan_revision:'r1',suggestions:[{id:'S01',title:'异常处理',reason:'边界缺失',changes:[{action:'update',id:'F01',fields:{说明:'重试'}}]}]};
 const sandbox={window:{},document:{getElementById:$,createElement:()=>new Node()},setInterval(){return 1;},clearInterval(){}};
 vm.runInNewContext(fs.readFileSync('scripts/planning-suggestions.js','utf8'),sandbox);
 view=sandbox.window.createPlanningSuggestions({getPlan:()=>state,getDiscussion:()=>'用户：希望支持离线记账。',setBusy:v=>view.setBusy(v),onPreview:d=>{preview=d;state.dirty=true;},request:async(route,payload)=>{calls.push({route,payload});if(failGenerate&&route==='/api/plan/suggestions')throw Error('network failure');return route.endsWith('/preview')?{content:'PREVIEW',revision:'r1',diff:'+ retry'}:data;}});
 await new Promise(r=>setImmediate(r));
 const check=$('suggestions-list').children[0].children[0].children[0];assert.equal(check.checked,false);assert.equal($('preview-suggestions').disabled,true);
 check.checked=true;check.handlers.change();assert.equal($('preview-suggestions').disabled,false);
 await $('preview-suggestions').handlers.click();assert.equal(preview.content,'PREVIEW');assert.equal(preview.changedIds.join(','),'F01');assert.equal($('suggestion-diff').hidden,false);assert.ok(!calls.some(c=>c.route.endsWith('/save')),'preview must never save');
 assert.equal($('preview-suggestions').disabled,true);await $('generate-suggestions').handlers.click();assert.match($('suggestions-status').textContent,/先保存/);
 state={revision:'saved-preview',ready:true,dirty:false};view.onSaved('saved-preview');view.setBusy(false);assert.match($('suggestions-status').textContent,/已保存/);assert.doesNotMatch($('suggestions-status').textContent,/过期/);
 state={revision:'r2',ready:true,dirty:false};view.setBusy(false);assert.equal(check.disabled,true);assert.match($('suggestions-status').textContent,/过期/);
 state.revision='r1';view.setBusy(false);assert.equal(check.disabled,false);assert.doesNotMatch($('suggestions-status').textContent,/过期/);state.revision='r2';
 state={revision:'r1',ready:true,dirty:false};view.setBusy(false);await $('preview-suggestions').handlers.click();
 view.discardPreview();state={revision:'r1',ready:true,dirty:false};view.setBusy(false);assert.match($('suggestions-status').textContent,/已放弃上次预览/);assert.equal($('suggestion-diff').hidden,true);state={revision:'unrelated',ready:true,dirty:false};view.onSaved('unrelated');view.setBusy(false);assert.doesNotMatch($('suggestions-status').textContent,/编辑结果已保存/,'discarded preview cannot claim unrelated save');
 state={revision:'r1',ready:true,dirty:false};view.setBusy(false);await $('preview-suggestions').handlers.click();state={revision:'r2',ready:true,dirty:false};view.onSaved('r2');
 failGenerate=true;await $('generate-suggestions').handlers.click();assert.match($('suggestions-status').textContent,/network failure/,'old success cannot mask new generation failure');failGenerate=false;
 $('suggestions-focus').value=' 边界 ';await $('generate-suggestions').handlers.click();assert.equal(calls.at(-1).payload.focus,'边界');assert.equal(calls.at(-1).payload.discussion,'用户：希望支持离线记账。');assert.equal(calls.at(-1).payload.revision,'r2');assert.equal($('suggestions-progress').hidden,true);
 console.log('Suggestions: explicit selection, preview without save, dirty guard, stale revision, generation progress passed.');
}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
