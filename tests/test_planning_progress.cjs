const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function run(){
 const nodes=new Map(),timers=new Set();
 const $=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,handlers:{},setAttribute(k,v){this[k]=v;},addEventListener(k,f){this.handlers[k]=f;}});return nodes.get(id);};
 const box={window:{},document:{getElementById:$},setInterval(f){timers.add(f);return f;},clearInterval(f){timers.delete(f);}};
 vm.runInNewContext(fs.readFileSync('scripts/planning-progress.js','utf8'),box);
 let state={percent:50,stage:'Codex 分析',detail:'等待输出',status:'running'},release;
 const progress=box.window.createPlanningProgress({poll:async()=>state});
 const task=progress.run('生成建议',()=>new Promise(r=>release=r));
 assert.equal($('operation-bar').value,0);await [...timers][0]();assert.equal($('operation-bar').value,50);assert.match($('operation-stage').textContent,/Codex/);
 state.percent=20;await [...timers][0]();assert.equal($('operation-bar').value,50,'server stages never go backwards');
 release('ok');assert.equal(await task,'ok');assert.equal($('operation-bar').value,100);assert.equal(timers.size,0);
 let fail;
 const rejected=progress.run('保存',()=>new Promise((r,j)=>fail=j));const check=assert.rejects(rejected,/失败/);
 state.percent=75;await [...timers][0]();fail(Error('写入失败'));await check;
 assert.equal($('operation-bar').value,75);assert.equal($('operation-progress-panel')['data-state'],'failed');assert.equal(timers.size,0);
 let oldRelease,newRelease;
 const old=progress.run('旧任务',()=>new Promise(r=>oldRelease=r));const latest=progress.run('新任务',()=>new Promise(r=>newRelease=r));
 oldRelease();await old;assert.equal($('operation-title').textContent,'新任务');assert.equal($('operation-bar').value,0);
 newRelease();await latest;
 let longRelease;
 const long=progress.run('长期 Codex',()=>new Promise(r=>longRelease=r));
 await progress.run('复制',async()=>{},false);
 assert.equal($('operation-title').textContent,'长期 Codex','short local action must restore the running operation');
 assert.equal($('operation-dismiss').hidden,true);longRelease();await long;
 $('operation-dismiss').handlers.click();assert.equal($('operation-progress-panel').hidden,true);
 console.log('Progress: percentages, current step, monotonic milestones, errors, cleanup and overlapping tasks passed.');
}
module.exports=run;if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
