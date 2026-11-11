const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor() { this.children = []; this.dataset = {}; this.style = {}; this._text = ''; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._text = ''; }
  setAttribute() {}
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
}
const nodes = new Map();
const get = id => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
const context = vm.createContext({
  document: {getElementById:get, createElement:() => new Node(), querySelectorAll:() => []},
  location:{search:''}, URLSearchParams, Date, JSON, Set, Map, Array, String, Number,
  fetch:() => new Promise(() => {}), setInterval() {}
});
const html = fs.readFileSync(path.join(__dirname, '../scripts/dashboard.html'), 'utf8');
vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1], context);
const item = (id, status, checked = false, children = []) => ({id, name:id, fields:{'状态':status}, checked, children, notes:[]});
const render = children => context.render({groups:[{id:'F01', name:'订单', items:children}]});

render([item('F01-01','进行中',false,[item('F01-01-01','已取消'),item('F01-01-02','已取消')]), item('F02','未开始')]);
assert.match(get('overview').textContent, /已验收 0 \/ 2 个最细功能点/);
assert.match(get('board').textContent, /F01 · 已验收 0 \/ 2 个最细功能点/);

render([item('F01-01','已完成',true,[item('F01-01-01','已取消'),item('F01-01-02','已取消')]), item('F02','未开始')]);
assert.match(get('overview').textContent, /^50%已验收 1 \/ 2 个最细功能点/);

render([item('F01-01','已取消',false,[item('F01-01-01','进行中')]), item('F02','未开始')]);
assert.match(get('overview').textContent, /已验收 0 \/ 1 个最细功能点/);

render([item('F01-01','已完成',true,[item('F01-01-01','已完成',true),item('F01-01-02','已取消')])]);
assert.match(get('overview').textContent, /^100%已验收 1 \/ 1 个最细功能点/);
console.log('Dashboard adoption: active parent without effective children counts once, cancelled subtree excluded, no parent-child double count.');
