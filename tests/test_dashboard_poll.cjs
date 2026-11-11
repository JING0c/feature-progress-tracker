const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const tick = () => new Promise(resolve => setImmediate(resolve));

async function run(html = fs.readFileSync(path.join(__dirname, '../scripts/dashboard.html'), 'utf8')) {
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1);
  const nodes = new Map(), requests = [], rendered = [];
  const node = () => ({dataset: {}, textContent: '', href: '', style: {}, append() {}, setAttribute() {}, addEventListener() {}});
  let interval;
  const context = vm.createContext({
    document: {
      getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); },
      createElement: node, querySelectorAll: () => []
    },
    location: {search: '?project=p-dashboard'}, URLSearchParams, Date, JSON, Set, Map, Array, String, Number,
    setInterval(fn) { interval = fn; },
    fetch(url, options) {
      assert.equal(options?.method || 'GET', 'GET');
      assert.equal(options?.cache, 'no-store');
      if (url === '/api/projects') return Promise.resolve({ok: true, json: async () => ({projects: []})});
      assert.equal(url, '/api/ledger?project=p-dashboard');
      return new Promise((resolve, reject) => requests.push({resolve, reject}));
    },
    capture(data) { rendered.push(JSON.parse(JSON.stringify(data))); }
  });
  vm.runInContext(scripts[0][1], context, {filename: 'dashboard.html'});
  // Observe the data delivered to the real polling path; card rendering has its own tests.
  vm.runInContext('render = capture;', context);

  assert.equal(requests.length, 1);
  interval(); interval();
  assert.equal(requests.length, 1, 'slow polling must not allow newer overlapping requests');
  const old = {groups: [{name: '旧台账'}]}, latest = {groups: [{name: '最新台账'}]};
  requests[0].resolve({ok: true, json: async () => old}); await tick();
  interval(); interval();
  assert.equal(requests.length, 2, 'a completed request releases the guard exactly once');
  requests[1].resolve({ok: true, json: async () => latest}); await tick();
  assert.deepEqual(rendered.map(data => data.groups[0].name), ['旧台账', '最新台账']);

  interval(); requests[2].reject(new Error('temporary read failure')); await tick();
  assert.equal(rendered.at(-1).groups[0].name, '最新台账', 'failed read keeps the latest visible content');
  assert.equal(nodes.get('message').dataset.error, 'true');
  interval();
  assert.equal(requests.length, 4, 'failure also releases the guard for recovery');
  requests[3].resolve({ok: true, json: async () => latest}); await tick();
  assert.equal(rendered.length, 2, 'unchanged data must not replace expanded cards');
  assert.equal(nodes.get('message').dataset.error, 'false');
  console.log('Dashboard polling: no overlapping stale writes, latest content retained, failure recovery, unchanged-render checks passed.');
  return 4;
}

module.exports = run;
if (require.main === module) run().catch(error => {console.error(error); process.exitCode = 1;});
