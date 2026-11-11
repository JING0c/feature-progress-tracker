const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Execute the page's real renderer and polling path. This lightweight DOM fixture
// observes hierarchy and disclosure state; browser checks cover layout and keys.
class Node {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.open = false; this._text = ''; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._text = ''; }
  setAttribute() {}
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
}
const descend = root => root.children.flatMap(n => [n, ...descend(n)]);
const hasClass = (node, cls) => (node.className || '').split(' ').includes(cls);
const item = (id, name, children = [], fields = {}) => ({id, name, children, checked:false, fields:{'状态':'进行中', ...fields}, notes:[]});
const tick = () => new Promise(resolve => setImmediate(resolve));

async function run() {
  const nodes = new Map(), get = id => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
  let data = {groups:[{id:'F01', name:'订单', items:[item('F01-01', '处理订单', [item('F01-01-01', '确认订单', [], {'验收':'确认后显示已收到'})], {'说明':'父级完整说明'})]}]};
  const context = vm.createContext({
    document:{getElementById:get, createElement:tag => new Node(tag), querySelectorAll:selector => {
      assert.equal(selector, 'details[open]');
      return [...nodes.values()].flatMap(descend).filter(n => n.tagName === 'details' && n.open);
    }},
    location:{search:''}, URLSearchParams, Date, JSON, Set, Map, Array, String, Number,
    fetch:async(url, options) => { assert.equal(url, '/api/ledger'); assert.equal(options.method || 'GET','GET'); return {ok:true, json:async() => data}; },
    setInterval() {}
  });
  const html = fs.readFileSync(path.join(__dirname, '../scripts/dashboard.html'), 'utf8');
  vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1], context);
  await tick();
  const find = (cls, text) => descend(get('board')).find(n => hasClass(n, cls) && (!text || n.textContent.includes(text)));
  let parent = find('card', '处理订单'), child = descend(parent).find(n => hasClass(n,'card'));
  assert.ok(hasClass(parent.children[1], 'children'), 'expanding a parent exposes its child list before full metadata');
  assert.ok(parent.children[1].children.includes(child), 'the child remains contained inside its parent');
  let detail = parent.children.find(n => n.tagName === 'details');
  assert.ok(detail, 'full parent details have their own native disclosure');
  assert.equal(detail.open, false, 'long parent metadata starts collapsed');
  assert.equal(detail.children[0].textContent, '查看本功能详情');
  assert.match(detail.textContent, /父级完整说明/);
  assert.ok(hasClass(child.children[1], 'meta'), 'opening a leaf directly exposes its details');
  assert.match(child.children[1].textContent, /确认后显示已收到/);
  assert.notEqual(parent.dataset.key, detail.dataset.key, 'parent and full-detail state have distinct keys');
  assert.notEqual(child.dataset.key, detail.dataset.key, 'child and parent-detail state cannot open one another');

  parent.open = true; child.open = true;
  data.groups[0].items[0].fields['说明'] = '轮询后的父级完整说明';
  await context.poll();
  parent = find('card', '处理订单'); child = descend(parent).find(n => hasClass(n,'card'));
  detail = parent.children.find(n => n.tagName === 'details');
  assert.equal(parent.open, true); assert.equal(child.open, true);
  assert.equal(detail.open, false, 'opening the parent and child must not open full parent details during refresh');
  detail.open = true; child.open = false;
  data.groups[0].items[0].name = '处理新订单';
  await context.poll();
  parent = find('card', '处理新订单'); child = descend(parent).find(n => hasClass(n,'card'));
  detail = parent.children.find(n => n.tagName === 'details');
  assert.equal(parent.open, true); assert.equal(detail.open, true);
  assert.equal(child.open, false, 'closed child state stays independent of an open parent detail');
  assert.match(detail.textContent, /轮询后的父级完整说明/);
  console.log('Dashboard hierarchy: child-first containment, direct leaf details, complete parent metadata, independent polling state passed.');
}
module.exports = run;
if (require.main === module) run().catch(error => { console.error(error); process.exitCode = 1; });
