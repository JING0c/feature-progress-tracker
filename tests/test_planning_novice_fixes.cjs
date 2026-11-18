const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const reply=(data,ok=true)=>({ok,status:ok?200:409,json:async()=>data});
const QUESTION='请先确认：1. 谁会使用库存？2. 是否需要预警？';
const PROPOSAL='拆分如下。\n```json\n{"features":[{"key":"N1","parent":"无","功能名称":"库存","说明":"记录材料","验收标准":"可增减"}]}\n```\n<!-- feature-proposal -->';

// Drives the actual page script; only DOM, storage and HTTP are stubbed.
async function harness(){
 const nodes=new Map(),storage=new Map(),calls=[],planningReplies=[];
 let workflowOptions;
 const node=id=>{
  if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',handlers:{},attributes:{},hidden:false,
   addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(k,v){this.attributes[k]=v;},
   replaceChildren(){},append(){},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},querySelector(){return node('send');}
  });return nodes.get(id);
 };
 const context=vm.createContext({
  document:{getElementById:node,querySelector:node,createElement:()=>node(Symbol()),body:node('body')},
  location:{search:'?project=isolated'},URLSearchParams,
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  setInterval(){},setTimeout(){},renderPlanningMarkdown(target,text){target.rendered=text;},confirm:()=>true,
  createPlanningWorkflow(options){workflowOptions=options;return{setBusy(){},editing:false,ensureResearch:async()=>{}};},
  createPlanningAssistant(){return{sync(){},validate(){return true;},shouldGenerate(){return false;},persistInput(){},showDiscussion(){context.switchedToDiscussion=true;}};},
  createPlanningSuggestions(){return{setBusy(){},discardPreview(){},onSaved(){}};},
  createPlanningSheetView(){return{show(){},loading(){},clear(){},error(){},finishPreview(){}};},
  fetch:async(url,options={})=>{
   const route=url.split('?')[0],payload=options.body?JSON.parse(options.body):undefined;calls.push({route,payload});
   if(route==='/api/plan')return reply({content:'# 项目规划书',revision:'r1',path:'/P/项目规划书.md',planning:{ready:true}});
   if(route==='/api/plan/table')return reply({title:'规划',sheets:[]});
   if(route==='/api/project')return reply({name:'隔离项目',planning:{ready:true}});
   if(route==='/api/ledger/info')return reply({revision:'ledger-r',path:'/P/功能执行情况.md'});
   if(route==='/api/planning'){const next=planningReplies.shift();return next==='fail'?reply({error:'智能体回复超时，请重试。'},false):reply({reply:next,plan_revision:'r1'});}
   if(route==='/api/plan/merge')return reply({content:'# 项目规划书\n合并后',plan_revision:'r1',added:['F02']});
   if(route==='/api/plan/save')return reply({revision:'r2',path:'/P/项目规划书.md',planning:{ready:true}});
   if(route==='/api/ledger/generate')return reply({content:'## 大功能 F01：库存\n- [ ] F01-01 记录｜状态：未开始',ledger_revision:'ledger-r',plan_revision:'r2',source_revision:'s',summary:{done:0,total:1},note:'代码转换'});
   if(route==='/api/ledger/preview')return reply({count:1,summary:{done:0,total:1},adjustments:[]});
   if(route==='/api/ledger/save')return reply({count:1,summary:{done:0,total:1},adjustments:[]});
   throw Error('Unexpected request '+route);
  }
 });
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/planning.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await tick();await tick();
 return{node,storage,calls,planningReplies,context,guide:t=>workflowOptions.guide(t),run:code=>vm.runInContext(code,context)};
}

async function clarifyingQuestionsStayInFeaturePanel(){
 const h=await harness();
 h.node('input').value='主讨论区里我自己的草稿';
 h.planningReplies.push(QUESTION);
 await h.guide('我希望新增功能：库存');
 const split=h.calls.find(c=>c.route==='/api/planning');
 assert.equal(split.payload.intent,'decompose');
 assert.equal(h.node('input').value,'主讨论区里我自己的草稿','feature flow must not borrow or clear the main input');
 assert.equal(h.node('feature-thread').hidden,false,'questions appear inside the new-feature panel');
 assert.equal(h.node('feature-thread-reply').rendered,QUESTION);
 assert.equal(h.node('feature-answer-box').hidden,false);
 assert.equal(h.node('apply-feature-proposal').hidden,true);
 assert.ok(h.node('feature-thread').scrolled&&h.node('feature-answer').focused,'reply is brought into view where the user started');
 assert.ok(!h.context.switchedToDiscussion,'must not send the user to the suggestions discussion');
 assert.match(h.node('status').textContent,/下方直接回答/);

 h.node('feature-answer').value='维修员使用，需要低库存预警';
 h.planningReplies.push(PROPOSAL);
 await h.node('answer-feature').handlers.click();
 const second=h.calls.filter(c=>c.route==='/api/planning')[1];
 assert.equal(second.payload.intent,'decompose');
 assert.equal(second.payload.messages.at(-1).content,'维修员使用，需要低库存预警');
 assert.equal(h.node('feature-answer').value,'','answer box clears after a successful reply');
 assert.equal(h.node('apply-feature-proposal').hidden,false);
 assert.equal(h.node('answer-feature').hidden,true);
 assert.equal(h.node('feature-answer-box').hidden,true);
 assert.match(h.node('feature-proposal').textContent,/库存/);

 await h.node('apply-feature-proposal').handlers.click();
 assert.ok(h.calls.some(c=>c.route==='/api/plan/merge')&&h.calls.some(c=>c.route==='/api/plan/save'));
 assert.equal(h.node('feature-thread').hidden,true,'saved proposal closes the thread');
 assert.equal(h.node('apply-feature-proposal').hidden,true,'adopted proposal cannot be applied twice');
}

async function failedAnswerIsKeptAndDiscardCloses(){
 const h=await harness();
 h.planningReplies.push(QUESTION,'fail');
 await h.guide('我希望新增功能：库存');
 h.node('feature-answer').value='我的回答';
 await h.node('answer-feature').handlers.click();
 assert.equal(h.node('feature-answer').value,'我的回答','failed reply keeps the answer for retry');
 assert.equal(h.node('feature-thread').hidden,false,'question stays visible after failure');
 h.node('feature-answer').value='';
 await h.node('answer-feature').handlers.click();
 assert.equal(h.calls.filter(c=>c.route==='/api/planning').length,2,'empty answer is not sent');
 h.node('discard-feature-thread').handlers.click();
 assert.equal(h.node('feature-thread').hidden,true);
 assert.equal(JSON.parse(h.storage.get('project-planning:__PLANNING_KEY__')).at(-1).featureClosed,true,'dismissal is stored on the reply and survives reload');
}

async function clearedChatDoesNotHideNextSplit(){
 const h=await harness();
 h.planningReplies.push(PROPOSAL);
 await h.guide('我希望新增功能：库存');
 await h.node('apply-feature-proposal').handlers.click();
 assert.equal(h.node('feature-thread').hidden,true);
 h.node('clear').handlers.click();
 h.planningReplies.push(QUESTION);
 await h.guide('我希望新增功能：预警');
 assert.equal(h.node('feature-thread').hidden,false,'a new split after clearing the chat must be visible');
 h.node('feature-answer').value='需要预警';h.planningReplies.push(PROPOSAL);
 await h.node('answer-feature').handlers.click();
 assert.equal(h.calls.filter(c=>c.route==='/api/planning').length,3,'answer is sent after clearing the chat');
 assert.equal(h.node('apply-feature-proposal').hidden,false);
}

async function staleUnsavedWordingIsDropped(){
 const h=await harness();
 h.run("dirty=true;setSyncText('磁盘已有更新版本；当前为未保存编辑，请保留修改后读取文件版本。',{unsaved:true});dirty=false;setBusy(false);dirty=true;setBusy(false)");
 assert.doesNotMatch(h.node('plan-sync').textContent,/磁盘已有更新版本/,'an old unsaved warning must not reappear for a new edit');
}

async function saveStateWordingNeverContradicts(){
 const h=await harness();
 h.run("setSyncText('已保存 · 历史版本已保留');dirty=true;setBusy(false)");
 assert.match(h.node('plan-sync').textContent,/未保存/,'sidebar follows unsaved state');
 assert.match(h.node('document-save-state').textContent,/未保存/);
 assert.match(h.node('planning-step').textContent,/未保存/);
 h.run('dirty=false;setBusy(false)');
 assert.equal(h.node('plan-sync').textContent,'已保存 · 历史版本已保留');
 assert.equal(h.node('ledger-done').hidden,true,'board sync is never claimed without a ledger save');

 await h.node('generate-ledger').handlers.click();
 await h.node('save-ledger').handlers.click();
 assert.ok(h.calls.some(c=>c.route==='/api/ledger/save'));
 assert.equal(h.node('ledger-done').hidden,false,'board link appears in place after saving the ledger');
 assert.match(h.node('planning-step').textContent,/看板已同步/);
 assert.doesNotMatch(h.node('planning-reason').textContent,/再进入看板|生成功能台账。$/,'completed step is not presented as still pending');
 assert.equal(h.node('open-board').href,'/?project=isolated');

 h.run("planRevision='r-new';setBusy(false)");
 assert.equal(h.node('ledger-done').hidden,true,'a newer plan revision withdraws the synced claim');
 assert.doesNotMatch(h.node('planning-step').textContent,/看板已同步/);
}

(async()=>{
 const tests=[clarifyingQuestionsStayInFeaturePanel,failedAnswerIsKeptAndDiscardCloses,clearedChatDoesNotHideNextSplit,staleUnsavedWordingIsDropped,saveStateWordingNeverContradicts];
 let failed=0;
 for(const test of tests){try{await test();console.log('PASS',test.name);}catch(error){failed++;console.error('FAIL',test.name,error.message);}}
 if(failed)throw Error(failed+' novice-fix regressions failed');
 console.log('Novice fixes: in-place feature clarification, kept answers, consistent save/board state passed.');
})().catch(error=>{console.error(error);process.exit(1);});
