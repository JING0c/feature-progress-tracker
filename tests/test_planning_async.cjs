const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const reply=(data,ok=true)=>({ok,status:ok?200:409,json:async()=>data});
const documentReply=(content='# original saved',revision='r')=>reply({content,revision,path:'/P/项目规划书.md',planning:{ready:true}});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};};

// The actual page script is exercised; only DOM/storage and HTTP are controlled.
async function harness(){
 const nodes=new Map(),storage=new Map(),calls=[],prompts=[],readQueue=[];
 let ready=true,generateFails=false,confirmResult=true;
 const candidate='# 功能执行情况\n## 大功能 F01：导出\n- [ ] F01-01 导出CSV｜状态：未开始';
 const node=id=>{
  if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',handlers:{},children:[],attributes:{},hidden:false,
   addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(k,v){this.attributes[k]=v;},
   replaceChildren(){this.children=[];},append(...items){this.children.push(...items);},
   focus(){},scrollIntoView(){},querySelector(){return node('send');},showModal(){this.open=true;},close(){this.open=false;}
  });return nodes.get(id);
 };
 storage.set('project-planning:__PLANNING_KEY__',JSON.stringify([{role:'assistant',content:candidate,ledgerRevision:'ledger-r',planRevision:'r',sourceRevision:'source-r',intent:'ledger'}]));
 const context=vm.createContext({
  document:{getElementById:node,querySelector:node,createElement:()=>node(Symbol()),body:node('body')},
  location:{search:'?project=isolated'},URLSearchParams,
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  setInterval(){},setTimeout(){},renderPlanningMarkdown(){},
  createPlanningWorkflow(){return{setBusy(){},editing:false};},
  createPlanningSuggestions(){return{setBusy(){},discardPreview(){},onSaved(){}};},
  createPlanningSheetView(){return{show(){},loading(){},clear(){},error(){},finishPreview(){}};},
  confirm(text){prompts.push(text);return confirmResult;},
  fetch:async(url,options={})=>{
   const route=url.split('?')[0],payload=options.body?JSON.parse(options.body):undefined;calls.push({route,payload});
   if(route==='/api/plan')return readQueue.length?readQueue.shift()():documentReply();
   if(route==='/api/plan/table')return reply({title:'规划',sheets:[]});
   if(route==='/api/plan/save')return reply({revision:'saved',planning:{ready:true}});
   if(route==='/api/project')return reply({name:'隔离项目',planning:{ready,reason:'请先保存规划'}});
   if(route==='/api/ledger/info')return reply({revision:'ledger-r',path:'/P/功能执行情况.md'});
   if(route==='/api/ledger/generate')return generateFails?reply({error:'转换失败'},false):reply({content:candidate,ledger_revision:'ledger-r',plan_revision:'r',source_revision:'source-generated',summary:{done:0,total:1},note:'代码转换'});
   if(route==='/api/ledger/preview')return reply({content:candidate,count:1,summary:{done:0,total:1},adjustments:[]});
   if(route==='/api/ledger/save')return reply({count:1,summary:{done:0,total:1},adjustments:[]});
   throw Error('Unexpected request '+route);
  }
 });
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/planning.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await tick();
 return{node,storage,calls,prompts,readQueue,context,run:code=>vm.runInContext(code,context),setReady:value=>ready=value,setGenerateFails:value=>generateFails=value,setConfirm:value=>confirmResult=value};
}

async function stalePollCannotReplaceSavedPlan(){
 const h=await harness(),old=deferred();h.readQueue.push(()=>old.promise);
 const poll=h.run('loadPlan()');await tick();
 h.run("planText='# newer saved';dirty=true;");await h.node('save-plan').handlers.click();
 assert.equal(h.run('planRevision'),'saved');
 old.resolve(documentReply());await poll;
 assert.equal(h.run('planText'),'# newer saved','late old read must not replace just-saved content');
 assert.equal(h.run('planRevision'),'saved');assert.equal(h.run('dirty'),false);
}
async function stalePollFailureCannotRelockSavedPlan(){
 const h=await harness(),old=deferred();h.readQueue.push(()=>old.promise);
 const poll=h.run('loadPlan()');await tick();
 h.run("planText='# newer saved';dirty=true;");await h.node('save-plan').handlers.click();
 old.resolve(reply({error:'旧读取失败',planning:{ready:false,reason:'旧读取缺文件'}},false));await poll;
 assert.equal(h.run('planningState.ready'),true,'a stale failure cannot relock a successfully saved plan');
 assert.equal(h.run('planText'),'# newer saved');assert.doesNotMatch(h.node('status').textContent,/旧读取/);
}
async function forcedReloadSupersedesPendingPoll(){
 const h=await harness(),old=deferred();h.readQueue.push(()=>old.promise,()=>documentReply('# latest disk','latest'));
 const poll=h.run('loadPlan()');await tick();
 h.run("planText='# unsaved important';dirty=true;retainDraft();");
 const before=h.calls.filter(c=>c.route==='/api/plan').length;
 await h.node('reload-plan').handlers.click();
 const after=h.calls.filter(c=>c.route==='/api/plan').length;
 old.resolve(documentReply());await poll;
 assert.equal(after-before,1,'explicit reload must actually read despite an in-flight background poll');
 assert.equal(h.run('planText'),'# latest disk');assert.equal(h.run('planRevision'),'latest');assert.equal(h.run('dirty'),false);
 assert.equal(h.storage.has('project-planning:__PLANNING_KEY__:document-draft-v2'),false);
 assert.match(h.node('status').textContent,/已读取/);
}
async function failedForcedReloadKeepsDraftAndReportsFailure(){
 const h=await harness(),old=deferred();h.readQueue.push(()=>old.promise,()=>reply({error:'读取失败'},false));
 const poll=h.run('loadPlan()');await tick();
 h.run("planText='# unsaved important';dirty=true;retainDraft();");
 await h.node('reload-plan').handlers.click();old.resolve(documentReply());await poll;
 assert.equal(h.run('planText'),'# unsaved important');assert.equal(h.run('dirty'),true);
 assert.ok(h.storage.has('project-planning:__PLANNING_KEY__:document-draft-v2'),'failed explicit read must retain recovery data');
 assert.doesNotMatch(h.node('status').textContent,/已读取/);assert.match(h.node('status').textContent,/读取失败/);
}
async function duplicateLedgerClicksSubmitOnce(){
 for(const action of ['generate-ledger','save-ledger']){
  const h=await harness();await Promise.all([h.node(action).handlers.click(),h.node(action).handlers.click()]);
  const route=action==='generate-ledger'?'/api/ledger/generate':'/api/ledger/save';
  assert.equal(h.calls.filter(c=>c.route===route).length,1,action+' should submit only once');
  assert.equal(h.prompts.length,action==='save-ledger'?1:0);
  assert.equal(h.run('busy'),false,'operation lock must be released');
 }
}
async function failedPrerequisiteAndCancellationReleaseLock(){
 for(const action of ['generate-ledger','save-ledger']){
  const h=await harness();h.setReady(false);await h.node(action).handlers.click();assert.equal(h.run('busy'),false);
  h.setReady(true);h.setConfirm(false);await h.node(action).handlers.click();assert.equal(h.run('busy'),false);
  if(action==='save-ledger')assert.equal(h.calls.filter(c=>c.route==='/api/ledger/save').length,0);
 }
 const h=await harness();h.setGenerateFails(true);await h.node('generate-ledger').handlers.click();assert.equal(h.run('busy'),false);
 h.setGenerateFails(false);await h.node('generate-ledger').handlers.click();assert.match(h.node('status').textContent,/已按规则转换/);
}
async function ledgerSourceBindingSurvivesGenerateAndSave(){
 const h=await harness();await h.node('generate-ledger').handlers.click();
 assert.equal(h.run('messages.at(-1).sourceRevision'),'source-generated','generated source binding must survive chat persistence');
 const stored=JSON.parse(h.storage.get('project-planning:__PLANNING_KEY__'));
 assert.equal(stored.at(-1).sourceRevision,'source-generated');
 await h.node('save-ledger').handlers.click();
 for(const route of ['/api/ledger/preview','/api/ledger/save'])assert.equal(h.calls.find(c=>c.route===route).payload.source_revision,'source-generated');
}
async function run(){
 const cases=[stalePollCannotReplaceSavedPlan,stalePollFailureCannotRelockSavedPlan,forcedReloadSupersedesPendingPoll,failedForcedReloadKeepsDraftAndReportsFailure,duplicateLedgerClicksSubmitOnce,failedPrerequisiteAndCancellationReleaseLock,ledgerSourceBindingSurvivesGenerateAndSave];
 const failures=[];
 for(const test of cases){try{await test();console.log('PASS',test.name);}catch(e){failures.push(e);console.error('FAIL',test.name,e.message);}}
 if(failures.length)throw new Error(failures.length+' async planning regressions failed');
}
module.exports=run;
if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
