const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Node{
 constructor(tag){this.tagName=tag;this.children=[];this.handlers={};this.attributes={};this.value='';this.disabled=false;this.hidden=false;this.className='';this._text='';}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;this._text='';}
 setAttribute(k,v){this.attributes[k]=String(v);}removeAttribute(k){delete this.attributes[k];}addEventListener(k,fn){this.handlers[k]=fn;}scrollIntoView(){}focus(){}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 querySelector(){return new Node();}
}
const read=name=>fs.readFileSync(path.join(__dirname,'../scripts',name),'utf8');

// U6: a candidate leads with the Chinese match summary; framework facts are folded; the confirm step is the one next step.
async function candidatesLeadWithBorrowableFeatures(){
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Node('div'));return nodes.get(id);};
 const sandbox={window:{},document:{getElementById:$,createElement:tag=>new Node(tag)},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},confirm:()=>true};
 vm.runInNewContext(read('planning-workflow.js'),sandbox);
 let rendered=0;
 const research={completed:true,selection_confirmed:false,query:'shopping list',summary_source:'中文摘要由本机 Codex 依据仓库说明与 README 节选生成，未核对源码。',
  repositories:[{name:'org/shop',url:'https://github.com/org/shop',description:'Shopping list PWA built with Vue',language:'HTML',license:'MIT',stars:82,summary_zh:'离线可用的购物清单网页',reusable:['添加商品','勾选已买'],gaps:'没有搜索'},
   {name:'org/plain',url:'https://github.com/org/plain',description:'Plain list',language:'JS',license:'MIT',stars:1}]};
 const workflow=sandbox.window.createPlanningWorkflow({request:async()=>JSON.parse(JSON.stringify(research)),notice(){},getPlan:()=>({content:'',revision:'r',ready:false}),setBusy(){},onResearchRendered:()=>rendered++});
 await new Promise(r=>setImmediate(r));
 const [first,second]=$('research-results').children;
 const texts=first.children.map(n=>n.textContent);
 assert.equal(first.children[2].textContent,'离线可用的购物清单网页','summary comes right after the choice and name');
 assert.ok(texts.includes('可借鉴：')&&texts.some(t=>t.includes('添加商品')&&t.includes('勾选已买')));
 assert.ok(texts.includes('与需求的差距：没有搜索'));
 const folded=first.children.find(n=>n.tagName==='details');
 assert.match(folded.textContent,/技术资料与原说明.*Shopping list PWA.*HTML · 许可证 MIT · ★ 82/);
 assert.ok(!texts.slice(0,-1).some(t=>t.includes('Shopping list PWA')),'English description stays inside the fold');
 assert.match(second.children[2].textContent,/暂无中文摘要/,'missing summary is stated, not invented');
 assert.match($('research-summary-note').textContent,/未核对源码/);
 assert.equal(workflow.referencePending,true,'a pending choice is the next step');
 assert.ok(rendered>0,'page is told to re-evaluate its primary button');
 const page=read('planning.html');
 assert.ok(page.indexOf('id="save-reference-selection"')<page.indexOf('id="research-results"'),'confirm button sits above the candidate list');
 // The assistant demotes the old primary action while a reference choice is pending.
 const anodes=new Map(),a=id=>{if(!anodes.has(id))anodes.set(id,new Node('div'));return anodes.get(id);};
 const asandbox={window:{},document:{getElementById:a},localStorage:{getItem:()=>null,setItem(){},removeItem(){}}};
 vm.runInNewContext(read('planning-assistant.js'),asandbox);
 let pending=true;const view=asandbox.window.createPlanningAssistant({storageKey:'k',getState:()=>({ready:false,dirty:false,editing:false,busy:false,referencePending:pending})});
 assert.equal(a('assistant-submit').className,'secondary');
 pending=false;view.sync();assert.equal(a('assistant-submit').className,'send');
}

// U4: conclusions before raw text, and the Markdown original is a secondary view with an obvious way back.
async function conclusionsComeBeforeRawText(){
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node('div'));return nodes.get(id);};
 const reply=data=>({ok:true,status:200,json:async()=>data});
 const ledger='# 功能执行情况\n## 大功能 F01：导出\n- [ ] F01-01 导出CSV｜状态：未开始\n- [ ] F02 备份｜状态：未开始';
 const nested='# 功能执行情况\n- [ ] F03 搜索｜状态：未开始\n  - [ ] F03-01 输入关键词｜状态：未开始';
 const context=vm.createContext({document:{getElementById:node,querySelector:node,createElement:tag=>new Node(tag),body:node('body')},
  location:{search:'?project=p'},URLSearchParams,localStorage:{getItem:()=>null,setItem(){},removeItem(){}},setInterval(){},setTimeout(){},renderPlanningMarkdown(){},confirm:()=>true,
  createPlanningWorkflow(){return{setBusy(){},editing:false};},createPlanningSuggestions(){return{setBusy(){},discardPreview(){},onSaved(){}};},
  createPlanningSheetView(){return{show(){},loading(){},clear(){},error(){},finishPreview(){}};},
  fetch:async url=>{const route=url.split('?')[0];
   if(route==='/api/plan')return reply({content:'# p',revision:'r',path:'/P/p.md',planning:{ready:true}});
   if(route==='/api/project')return reply({name:'P',planning:{ready:true}});
   if(route==='/api/plan/table')return reply({sheets:[]});
   if(route==='/api/ledger/generate')return reply({content:ledger,added:['F01-01'],updated:[],preserved:['F02'],ledger_revision:'l',plan_revision:'r',source_revision:'s',summary:{done:0,total:2},note:'代码转换'});
   throw Error('Unexpected '+route);}});
 vm.runInContext(read('planning.html').match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));
 await node('generate-ledger').handlers.click();
 const items=node('ledger-preview-list').children.map(n=>n.textContent);
 assert.deepEqual(items,['新增 1 个最细功能点：F01-01 导出CSV','保持不变 1 个最细功能点：F02 备份']);
 assert.equal(node('ledger-preview-content').textContent,ledger,'raw Markdown is still available on demand');
 vm.runInContext('renderLedgerPreview('+JSON.stringify({content:nested,added:['F03','F03-01']})+')',context);
 assert.deepEqual(node('ledger-preview-list').children.map(n=>n.textContent),['新增 1 个最细功能点（另含 1 个上级条目）：F03 搜索、F03-01 输入关键词'],'list counts match the heading, which counts finest-level points');
 const report='# 规划源码核对\n\n## 功能核对\n\n- F01：有源码依据 — 列表组件\n  - org/shop / src/List.vue:12\n- F01-01：部分依据 — 只有导入\n- F02：未找到依据 — 资料没有备份\n\n## 版本绑定数据\n```json\n{}\n```';
 vm.runInContext('renderSourceSummary('+JSON.stringify(report)+')',context);
 const summary=node('source-review-summary');
 assert.equal(summary.hidden,false);
 assert.match(summary.textContent,/3 个功能中，有源码依据 1，部分依据 1，未找到依据 1/);
 assert.match(summary.textContent,/F01-01 部分依据：只有导入.*F02 未找到依据：资料没有备份/);
 assert.ok(!summary.children.some(n=>n.tagName==='details'),'a short list stays open');
 assert.doesNotMatch(summary.textContent,/F01 有源码依据/,'only open items are listed');
 const tricky='## 功能核对\n\n- F02：未找到依据 — '+'很长'.repeat(120)+'\n- F02：未找到依据 — 重复行\n\n## 版本绑定数据\n- F09：未找到依据 — 绑定数据里的文字';
 vm.runInContext('renderSourceSummary('+JSON.stringify(tricky)+')',context);
 assert.match(summary.textContent,/1 个功能中/,'each feature counts once and binding data is ignored');
 assert.match(summary.textContent,/…/,'long findings are trimmed');
 const many='## 功能核对\n\n'+[1,2,3,4].map(n=>'- F0'+n+'：未找到依据 — 缺 '+n).join('\n');
 vm.runInContext('renderSourceSummary('+JSON.stringify(many)+')',context);
 const fold=summary.children.find(n=>n.tagName==='details');
 assert.ok(fold&&!fold.open,'more than three open items fold so the next step stays in view');
 assert.match(summary.children[0].textContent,/4 个功能中/,'the count line stays visible');
 vm.runInContext("setPlanView('document')",context);
 assert.equal(node('document-view-notice').hidden,false,'Markdown view says where you are and offers the way back');
 vm.runInContext("setPlanView('sheet')",context);
 assert.equal(node('document-view-notice').hidden,true);
// U7: 核对→预览→保存 is one ordered task; only the current step is primary and later steps wait.
 vm.runInContext("reviewState.source=false;reviewState.preview=false;setBusy(false)",context);
 const steps=()=>['source','preview','save'].map(k=>node('review-step-'+k).attributes['data-state']);
 assert.deepEqual(steps(),['current','todo','todo']);
 assert.equal(node('review-source').className,'send');assert.equal(node('generate-ledger').className,'secondary');
 assert.equal(node('generate-ledger').disabled,true,'preview waits for the source check');assert.equal(node('save-ledger').disabled,true);
 assert.equal(node('review-step-preview-state').textContent,'完成上一步后可用');
 vm.runInContext("reviewState.source=true;setBusy(false)",context);
 assert.deepEqual(steps(),['done','current','todo']);assert.equal(node('generate-ledger').className,'send');assert.equal(node('generate-ledger').disabled,false);
 await node('generate-ledger').handlers.click();
 assert.deepEqual(steps(),['done','done','current']);assert.equal(node('save-ledger').className,'send');assert.equal(node('save-ledger').disabled,false);
 vm.runInContext("ledgerSyncedRevision=planRevision;setBusy(false)",context);
 assert.deepEqual(steps(),['done','done','done']);assert.equal(node('ledger-done').hidden,false,'the last step ends at the in-place board link');
 vm.runInContext("invalidateSourceReview();ledgerSyncedRevision=null;reviewState.source=true;reviewState.preview=true;dirty=true;setBusy(false)",context);
 assert.deepEqual(steps(),['done','done','todo'],'unsaved table edits: no review step is primary');
 assert.equal(node('save-ledger').className,'secondary');assert.equal(node('review-step-save-state').textContent,'先保存功能表修改');
 vm.runInContext("dirty=false;invalidateSourceReview();ledgerSyncedRevision=null;setBusy(false)",context);
 assert.deepEqual(steps(),['current','todo','todo'],'a changed plan restarts the task from the source check');
 const page=read('planning.html'),more=page.slice(page.indexOf('<details class="plan-more">'));
 assert.ok(more.includes('id="view-document"'),'the Markdown original is reached from 更多');
}

(async()=>{
 for(const test of [candidatesLeadWithBorrowableFeatures,conclusionsComeBeforeRawText]){await test();console.log('PASS',test.name);}
 console.log('U4/U6: borrowable features first, one next step, conclusions before raw text passed.');
})().catch(e=>{console.error(e);process.exit(1);});
