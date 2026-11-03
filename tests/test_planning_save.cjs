const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the actual page event handler with an in-memory HTTP boundary.
// No browser storage or real project is changed by these contract checks.
async function scenario({accept = true, changed = false, previewFails = false, initialReady = true, latestReady = initialReady, action = 'save-ledger', planSaveFails = false, historyEmpty = false, researchFails = false, researchPause = false, referenceOnly = false} = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../scripts/planning.html'), 'utf8');
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
  const original = '# 台账\n进度：已验收 0/20 个最细功能点\n## 大功能 F01：预约\n- [ ] F01-01 冲突校验｜状态：未开始';
  const nodes = new Map(), calls = [], prompts = [];
  let projectReads = 0, researchChecks = 0, workflowOptions, clearedTimers = 0;
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      textContent: '', className: '', disabled: false, value: '', handlers: {},
      addEventListener(name, fn) { this.handlers[name] = fn; },
      setAttribute() {},
      replaceChildren() {}, append() {}, focus() {}, scrollIntoView() {},
      requestSubmit() { return this.handlers.submit({preventDefault() {}}); },
      querySelector() { return node('send'); }
    });
    return nodes.get(id);
  };
  const storage = new Map([['project-planning:__PLANNING_KEY__', JSON.stringify(historyEmpty ? [] : [
    {role: 'assistant', content: action==='apply-feature-proposal'?original+'\n<!-- feature-proposal -->':original, ledgerRevision: 'initial-revision', intent: action==='apply-feature-proposal'?'decompose':undefined}
  ])]]);
  const context = {
    document: {getElementById: node, querySelector: node, createElement: () => node(Symbol())},
    localStorage: {getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
    location: {search: '?project=project-a'}, URLSearchParams,
    setInterval() { return 1; }, clearInterval() { clearedTimers++; }, setTimeout() {}, renderPlanningMarkdown() {},
    createPlanningWorkflow(options){workflowOptions=options;return{ensureResearch:async()=>{if(researchFails)throw Error('GitHub 检索失败');if(researchPause&&!researchChecks++)throw Error('请保存参考选择');},setBusy(){},editing:false};},
    createPlanningSheetView() { return {show() {}, loading() {}, error() {}, clear() {}}; },
    confirm: text => { prompts.push(text); return accept; },
    fetch: async (url, options = {}) => {
      const route = url.split('?')[0], payload = options.body ? JSON.parse(options.body) : undefined;
      calls.push({url, route, payload, progress: node('reference-progress-status').textContent, progressHidden: node('reference-progress').hidden, elapsed: node('reference-progress-elapsed').textContent});
      let status = 200, data;
      const planning = ready => ({ready, reason:ready ? '规划书已完成' : '请先生成并保存项目规划书', planning_url:'/planning?project=project-a'});
      if (route === '/api/plan') data = {content: '', revision: 'plan-r', path: '/A/plan.md', planning:planning(initialReady), source:'new'};
      else if (route === '/api/plan/table') data = {title:'规划', sheets:[]};
      else if (route === '/api/project') data = {id:'project-a',name:'A',planning:planning(projectReads++ ? latestReady : initialReady),source:'new'};
      else if (route === '/api/projects') data = {projects: [{id:'project-a',name:'A',planning:planning(initialReady),source:'new'}]};
      else if (route === '/api/ledger/info') data = {path:'/A/ledger.md', revision: changed ? 'external-update' : 'initial-revision'};
      else if (route === '/api/ledger/preview') {
        status = previewFails ? 400 : 200;
        data = previewFails ? {error: '台账格式无效'} : {content: original.replace('0/20', '0/19'), summary:{done:0,total:19}, adjustments:['已验收 0/20 → 0/19'], count:21};
      } else if (route === '/api/ledger/save') data = {count:21, summary:{done:0,total:19}, adjustments:['已验收 0/20 → 0/19'], source_backup:'/A/source.md'};
      else if (route === '/api/planning' && action==='feature-timeout') {
        status=400;data={error:'智能体回复超时，请重试。'};
      }
      else if (route === '/api/planning') data = {reply:'# 项目规划书\n## 目标\n记录借阅。\n## 范围\n本机图书登记。\n## 功能与验收\n能够登记并查看图书。'};
      else if (route === '/api/plan/save') {
        status = planSaveFails ? 409 : 200;
        data = planSaveFails ? {error:'保存失败，保持待规划',planning:planning(false)} : {revision:'saved-plan',path:'/A/plan.md',planning:planning(true),source:'new'};
      }
      else throw Error('Unexpected request '+route);
      return {ok: status === 200, status, json: async () => data};
    }
  };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  const initialDisabled = {save:node('save-ledger').disabled, generate:node('generate-ledger').disabled, plan:node('save-plan').disabled};
  if(action==='feature-timeout'){await workflowOptions.guide('拆分新增功能',true);}else if(referenceOnly){await workflowOptions.resumePlanning();}else if(action==='submit'){node('input').value='新项目需求';await node('form').handlers.submit({preventDefault(){}});}else await node(action).handlers.click();
  await new Promise(resolve => setImmediate(resolve));
  if(researchPause){workflowOptions.resumePlanning();await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));}
  return {calls, prompts, original, clearedTimers, progress:node('reference-progress-status').textContent, progressHidden:node('reference-progress').hidden, status:node('status').textContent, initialDisabled, finalDisabled:{save:node('save-ledger').disabled,generate:node('generate-ledger').disabled,plan:node('save-plan').disabled}};
}

async function run() {
  const saved = await scenario();
  const preview = saved.calls.find(c => c.route === '/api/ledger/preview');
  assert.ok(preview, 'must preview computed totals before asking to save');
  assert.equal(preview.payload.content, saved.original);
  assert.equal(preview.payload.revision, 'initial-revision');
  assert.ok(saved.prompts[0].includes('0/19'), 'confirmation must show the corrected leaf total');
  const write = saved.calls.find(c => c.route === '/api/ledger/save');
  assert.equal(write.payload.content, saved.original, 'send the original so the server can preserve it');
  assert.equal(write.payload.revision, 'initial-revision');
  assert.ok(saved.status.includes('19'), 'success must describe leaf count');
  assert.ok(saved.status.includes('/A/source.md'), 'make the saved original discoverable');
  assert.ok(saved.calls.every(c => c.url.endsWith('?project=project-a')));
  const cancelled = await scenario({accept:false});
  assert.ok(cancelled.calls.some(c => c.route === '/api/ledger/preview'));
  assert.ok(!cancelled.calls.some(c => c.route === '/api/ledger/save'));
  const conflict = await scenario({changed:true});
  assert.equal(conflict.prompts.length, 0);
  assert.ok(!conflict.calls.some(c => c.route === '/api/ledger/save'));
  assert.match(conflict.status, /已更新/);
  const invalid = await scenario({previewFails:true});
  assert.equal(invalid.prompts.length, 0);
  assert.ok(!invalid.calls.some(c => c.route === '/api/ledger/save'));
  assert.match(invalid.status, /台账格式无效/);
  const pending = await scenario({initialReady:false});
  assert.equal(pending.initialDisabled.save, true, 'pending project cannot save a ledger');
  assert.equal(pending.initialDisabled.generate, true, 'pending project cannot generate a ledger');
  assert.equal(pending.initialDisabled.plan, true, 'an imported reference cannot be manually saved to unlock');
  assert.ok(!pending.calls.some(c => ['/api/ledger/preview','/api/ledger/save'].includes(c.route)));
  assert.match(pending.status, /规划书/);
  const relocked = await scenario({initialReady:true, latestReady:false});
  assert.equal(relocked.initialDisabled.save, false);
  assert.equal(relocked.prompts.length, 0);
  assert.ok(!relocked.calls.some(c => c.route === '/api/ledger/save'));
  const blockedGeneration = await scenario({initialReady:false, action:'generate-ledger'});
  assert.ok(!blockedGeneration.calls.some(c => c.route === '/api/planning'));
  const unlocked = await scenario({initialReady:false, action:'draft'});
  assert.equal(unlocked.calls.find(c => c.route === '/api/planning').payload.intent, 'plan');
  assert.equal(unlocked.finalDisabled.save, false);
  assert.equal(unlocked.finalDisabled.generate, false);
  const failedPlan = await scenario({initialReady:false, action:'draft', planSaveFails:true});
  assert.equal(failedPlan.finalDisabled.save, true);
  assert.equal(failedPlan.finalDisabled.generate, true);
  assert.equal(failedPlan.finalDisabled.plan, false, 'failed generated draft can retry saving');
  assert.match(failedPlan.status, /保存失败/);
  const first=await scenario({initialReady:false,historyEmpty:true,action:'submit'});
  assert.equal(first.calls.find(c=>c.route==='/api/planning').payload.intent,'plan','first need produces an editable plan');
  assert.ok(first.calls.some(c=>c.route==='/api/plan/save'));
  const noResearch=await scenario({initialReady:false,historyEmpty:true,action:'submit',researchFails:true});
  assert.ok(!noResearch.calls.some(c=>c.route==='/api/planning'),'research failure stops planning');
  assert.match(noResearch.status,/GitHub/);
  const resumed=await scenario({initialReady:false,action:'draft',researchPause:true});
  assert.equal(resumed.calls.find(c=>c.route==='/api/planning').payload.intent,'plan','reference selection resumes the original explicit plan intent');
  assert.ok(resumed.calls.some(c=>c.route==='/api/plan/save'));
  const reference = await scenario({initialReady:false, historyEmpty:true, referenceOnly:true});
  const generation = reference.calls.find(c=>c.route==='/api/planning');
  assert.equal(generation.payload.intent,'plan');
  assert.match(generation.progress,/正在.*生成功能表/);
  assert.equal(generation.progressHidden,false);
  assert.match(reference.calls.find(c=>c.route==='/api/plan/save').progress,/正在保存规划书/);
  assert.match(reference.progress,/功能表已生成并保存/);
  assert.equal(reference.progressHidden,true);
  const referenceFailure = await scenario({initialReady:false, historyEmpty:true, referenceOnly:true, planSaveFails:true});
  assert.match(referenceFailure.progress,/文件保存失败/);
  assert.equal(referenceFailure.progressHidden,true);
  const feature = await scenario({action:'apply-feature-proposal'});
  assert.equal(feature.calls.find(c=>c.route==='/api/planning').payload.merge_feature,true);
  assert.ok(feature.calls.some(c=>c.route==='/api/plan/save'),'confirmed proposal must be written through versioned save');
  const timeout = await scenario({action:'feature-timeout'});
  const split = timeout.calls.find(c=>c.route==='/api/planning');
  assert.equal(split.payload.intent,'decompose');
  assert.equal(split.progressHidden,false);
  assert.match(split.progress,/第 2 步.*拆分/);
  assert.match(split.elapsed,/已等待 \d+ 秒/);
  assert.equal(timeout.clearedTimers,1);
  assert.equal(timeout.progressHidden,true);
  assert.match(timeout.progress,/参考选择已保存.*超时.*重试/);
  console.log('Planning save: 16 scenarios passed, including prerequisite, generation, failure and relocking checks.');
}
module.exports = run;
if (require.main === module) run().catch(error => { console.error(error); process.exitCode = 1; });
