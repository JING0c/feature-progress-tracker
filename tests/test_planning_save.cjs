const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the actual page event handler with an in-memory HTTP boundary.
// No browser storage or real project is changed by these contract checks.
async function scenario({accept = true, changed = false, previewFails = false} = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../scripts/planning.html'), 'utf8');
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
  const original = '# 台账\n进度：已验收 0/20 个最细功能点\n## 大功能 F01：预约\n- [ ] F01-01 冲突校验｜状态：未开始';
  const nodes = new Map(), calls = [], prompts = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      textContent: '', className: '', disabled: false, value: '', handlers: {},
      addEventListener(name, fn) { this.handlers[name] = fn; },
      replaceChildren() {}, append() {}, focus() {}, scrollIntoView() {},
      querySelector() { return node('send'); }
    });
    return nodes.get(id);
  };
  const storage = new Map([['project-planning:__PLANNING_KEY__', JSON.stringify([
    {role: 'assistant', content: original, ledgerRevision: 'initial-revision'}
  ])]]);
  const context = {
    document: {getElementById: node, querySelector: node, createElement: () => node(Symbol())},
    localStorage: {getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
    location: {search: '?project=project-a'}, URLSearchParams,
    setInterval() {}, setTimeout() {}, renderPlanningMarkdown() {},
    confirm: text => { prompts.push(text); return accept; },
    fetch: async (url, options = {}) => {
      const route = url.split('?')[0], payload = options.body ? JSON.parse(options.body) : undefined;
      calls.push({url, route, payload});
      let status = 200, data;
      if (route === '/api/plan') data = {content: '', revision: 'plan-r', path: '/A/plan.md'};
      else if (route === '/api/projects') data = {projects: [{id:'project-a',name:'A'}]};
      else if (route === '/api/ledger/info') data = {path:'/A/ledger.md', revision: changed ? 'external-update' : 'initial-revision'};
      else if (route === '/api/ledger/preview') {
        status = previewFails ? 400 : 200;
        data = previewFails ? {error: '台账格式无效'} : {content: original.replace('0/20', '0/19'), summary:{done:0,total:19}, adjustments:['已验收 0/20 → 0/19'], count:21};
      } else if (route === '/api/ledger/save') data = {count:21, summary:{done:0,total:19}, adjustments:['已验收 0/20 → 0/19'], source_backup:'/A/source.md'};
      else throw Error('Unexpected request '+route);
      return {ok: status === 200, status, json: async () => data};
    }
  };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  await node('save-ledger').handlers.click();
  return {calls, prompts, original, status:node('status').textContent};
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
  console.log('Planning save: 4 scenarios passed (preview, cancel, conflict, invalid).');
}
module.exports = run;
if (require.main === module) run().catch(error => { console.error(error); process.exitCode = 1; });
