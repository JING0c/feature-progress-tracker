const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

async function run(){
  const nodes=new Map(),pending=[],calls=[],shown=[],downloads=[];
  let exportFails=false,suggestionOptions,finishedPreviews=0,editing=false,editSaves=0,hasPreview=false,readFails=false;
  const storage=new Map([['project-planning:__PLANNING_KEY__:document-draft-v2',JSON.stringify({content:'# stale browser draft',revision:'old'})]]);
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',attributes:{},handlers:{},hidden:false,children:[],
      addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(k,v){this.attributes[k]=v;},
      replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},focus(){},scrollIntoView(){this.scrolls=(this.scrolls||0)+1;},remove(){},
      click(){downloads.push({href:this.href,filename:this.download});},querySelector(){return node('send');}
    });
    return nodes.get(id);
  };
  const context=vm.createContext({
    document:{getElementById:node,querySelector:node,createElement:()=>node(Symbol()),body:node('body')},
    location:{search:'?project=project-table'},URLSearchParams,
    localStorage:{getItem(k){return storage.get(k)||null;},setItem(k,v){storage.set(k,v);},removeItem(k){storage.delete(k);}},
    setInterval(){},setTimeout(){},renderPlanningMarkdown(){},
    createPlanningSuggestions(options){suggestionOptions=options;return{setBusy(){},get hasPreview(){return hasPreview;},discardPreview(){hasPreview=false;}};},
    createPlanningWorkflow(){return{ensureResearch:async()=>{},setBusy(){},get editing(){return editing;},async saveEdits(){editSaves++;editing=false;}};},
    createPlanningSheetView(){return{finishPreview(){finishedPreviews++;},show(data){shown.push(data);},loading(){},error(){shown.push('error');},clear(){}};},
    URL:{createObjectURL(){return 'blob:export';},revokeObjectURL(){}},
    fetch:async(url,options={})=>{
      const route=url.split('?')[0],payload=options.body?JSON.parse(options.body):null;
      calls.push({url,route,payload});
      if(route==='/api/plan'&&readFails)return{ok:false,json:async()=>({error:'读取失败'})};
      if(route==='/api/plan/table')return new Promise(resolve=>pending.push({payload,resolve}));
      if(route==='/api/plan/save')return{ok:true,json:async()=>({revision:'saved',planning:{ready:true}})};
      if(route==='/api/plan/export')return{ok:!exportFails,json:async()=>({error:'导出失败'}),blob:async()=>({})};
      return{ok:true,json:async()=>route==='/api/plan'?{content:'',revision:'r',path:'/P/项目规划书.md',planning:{ready:false}}:{name:'P',source:'new',planning:{ready:false}}};
    }
  });
  const source=fs.readFileSync(path.join(__dirname,'../scripts/planning.html'),'utf8');
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  await new Promise(r=>setImmediate(r));
  assert.equal(vm.runInContext('planText',context),'','old cached draft must not replace disk version');
  assert.equal(node('restore-plan-draft').hidden,false);
  assert.equal(node('plan-sidebar').hidden,false,'recovery must stay accessible when the saved document is empty');
  assert.match(storage.get('project-planning:__PLANNING_KEY__:recoverable-draft'),/stale browser draft/);
  storage.delete('project-planning:__PLANNING_KEY__:document-draft-v2');
  assert.match(storage.get('project-planning:__PLANNING_KEY__:recoverable-draft'),/stale browser draft/,'saving latest plan must not delete recovery copy');
  storage.set('project-planning:__PLANNING_KEY__:document-draft-v2',JSON.stringify({content:'# new unsaved draft',revision:'new'}));
  vm.runInContext("loadRecoverableDrafts({content:'',revision:'r'})",context);
  const recovered=JSON.parse(storage.get('project-planning:__PLANNING_KEY__:recoverable-draft'));
  assert.equal(recovered.length,2);assert.equal(recovered[0].content,'# new unsaved draft');assert.equal(recovered[1].content,'# stale browser draft');
  assert.equal(node('recovery-tools').hidden,false);assert.equal(node('recovery-summary').textContent,'未保存草稿（2）');
  const cards=node('recovery-list').children.slice(1);assert.equal(cards.length,2);assert.equal(cards[0].children[0].checked,true);
  assert.match(cards[1].children[1].children[1].textContent,/暂存时间未记录/);assert.equal(cards[1].children[1].children[2].textContent,'stale browser draft');
  cards[1].children[0].handlers.change();assert.equal(node('plan-draft-choice').value,'1');
  const saveCalls=calls.filter(c=>c.route.endsWith('/save')).length;
  node('restore-plan-draft').handlers.click();assert.equal(vm.runInContext('planText',context),'# stale browser draft');assert.equal(vm.runInContext('planRevision',context),'old');assert.equal(vm.runInContext('dirty',context),true);assert.equal(calls.filter(c=>c.route.endsWith('/save')).length,saveCalls);
  node('plan-draft-choice').value='0';node('restore-plan-draft').handlers.click();assert.equal(vm.runInContext('planText',context),'# stale browser draft','dirty preview cannot be replaced');
  vm.runInContext('retainDraft()',context);assert.ok(JSON.parse(storage.get('project-planning:__PLANNING_KEY__:document-draft-v2')).savedAt);

  pending.shift().resolve({ok:true,json:async()=>({title:'recovered',sheets:[]})});await new Promise(r=>setImmediate(r));shown.length=0;
  vm.runInContext('showPlan("# older");showPlan("# current draft");dirty=true;',context);
  assert.equal(pending.length,2);
  pending[1].resolve({ok:true,json:async()=>({title:'current',sheets:[]})});
  await new Promise(r=>setImmediate(r));
  pending[0].resolve({ok:true,json:async()=>({title:'older',sheets:[]})});
  await new Promise(r=>setImmediate(r));
  assert.equal(shown.length,1);assert.equal(shown[0].title,'current','late responses cannot replace latest plan');
  await node('export-excel').handlers.click();
  const exported=calls.find(c=>c.route==='/api/plan/export');
  assert.equal(exported.payload.content,'# current draft');
  assert.equal(exported.url,'/api/plan/export?project=project-table');
  assert.equal(downloads[0].filename,'项目规划书.xlsx');
  assert.equal(node('save-ledger').disabled,true,'export never unlocks pending project');
  assert.match(node('status').textContent,/仍未保存/);
  exportFails=true;await node('export-excel').handlers.click();
  assert.equal(downloads.length,1);assert.match(node('status').textContent,/导出失败/);
  assert.ok(!calls.some(c=>c.route.endsWith('/save')));
  vm.runInContext('showPlan("# fallback")',context);
  pending[2].resolve({ok:false,json:async()=>({error:'cannot parse'})});
  await new Promise(r=>setImmediate(r));
  assert.equal(shown.at(-1),'error');
  node('view-document').handlers.click();
  assert.equal(node('plan-content').hidden,false);assert.equal(node('plan-sheet').hidden,true);
  node('view-sheet').handlers.click();
  assert.equal(node('plan-content').hidden,true);assert.equal(node('view-sheet').attributes['aria-pressed'],'true');
  vm.runInContext("planRevision='r';dirty=false;setPlanView('document');",context);
  let previewFinished=false;
  const previewTask=suggestionOptions.onPreview({content:'# suggestion preview',revision:'r',changedIds:['F01']}).then(()=>{previewFinished=true;});
  await new Promise(r=>setImmediate(r));
  assert.equal(previewFinished,false,'preview must wait until table is ready');
  assert.notEqual(vm.runInContext('planText',context),'# suggestion preview','failed table requests must not replace current draft');
  pending.at(-1).resolve({ok:true,json:async()=>({title:'suggestion',sheets:[]})});await previewTask;
  assert.equal(shown.at(-1).title,'suggestion');assert.equal(vm.runInContext('planText',context),'# suggestion preview');
  assert.equal(vm.runInContext('dirty',context),true);assert.equal(node('plan-sheet').hidden,false);
  assert.ok(!calls.some(c=>c.route.endsWith('/save')));
  vm.runInContext('dirty=false',context);
  const failed=suggestionOptions.onPreview({content:'# invalid preview',revision:'r',changedIds:['F01']});
  const failure=assert.rejects(failed,/cannot parse/);
  pending.at(-1).resolve({ok:false,json:async()=>({error:'cannot parse'})});await failure;
  assert.equal(vm.runInContext('planText',context),'# suggestion preview');assert.equal(vm.runInContext('dirty',context),false);
  await vm.runInContext('savePlan()',context);assert.equal(node('save-plan').disabled,true,'saved content does not invite duplicate saves');assert.equal(node('document-save-state').textContent,'已保存');assert.equal(finishedPreviews,1,'successful save must end preview filtering and unsaved status');assert.match(node('source-review-status').textContent,/下一步/,'first save must advance source-review guidance');
  vm.runInContext("notice('保存冲突，请重新读取。',true)",context);assert.equal(node('page-feedback').hidden,false);assert.match(node('page-feedback-text').textContent,/保存冲突/);node('dismiss-feedback').handlers.click();assert.equal(node('page-feedback').hidden,true);
  const beforeScroll=node('view-section').scrolls||0;const rendering=vm.runInContext('showPlan("# generated",true)',context);assert.equal(node('view-section').scrolls||0,beforeScroll,'do not focus an unfinished table');pending.at(-1).resolve({ok:true,json:async()=>({title:'generated',sheets:[]})});await rendering;assert.equal(node('view-section').scrolls,beforeScroll+1,'focus only after the table has rendered');
  editing=true;vm.runInContext('setBusy(false)',context);assert.equal(node('save-plan').disabled,false,'sticky save must work while editing');await node('save-plan').handlers.click();assert.equal(editSaves,1,'sticky save submits editor fields, not stale document');
  editing=false;hasPreview=true;vm.runInContext("dirty=true;planText='# protected preview';",context);readFails=true;await node('discard-suggestion-preview').handlers.click();assert.equal(vm.runInContext('planText',context),'# protected preview');assert.equal(hasPreview,true);assert.equal(vm.runInContext('dirty',context),true);
  readFails=false;vm.runInContext('planPolling=true',context);await node('discard-suggestion-preview').handlers.click();assert.equal(vm.runInContext('dirty',context),false,'explicit discard must work even when background polling has started');assert.equal(hasPreview,false);
  console.log('Planning table flow: baseline and suggestion rendering/failure scenarios passed (race, draft export, no unlock, failed export, source fallback).');
}
module.exports=run;
if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
