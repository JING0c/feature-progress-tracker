const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tag = 'DIV') {
    this.tagName = tag.toUpperCase(); this.children = []; this.handlers = {};
    this.attributes = {}; this.dataset = {}; this.value = ''; this.checked = false;
    this.disabled = false; this.hidden = false; this._text = '';
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map(n => typeof n === 'string' ? n : n.textContent).join(''); }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  focus() {}
  reset() {}
  get style() { return this._style ||= {}; }
}
function descendants(node, tag) {
  return node.children.flatMap(child => typeof child === 'string' ? [] :
    [...(child.tagName === tag ? [child] : []), ...descendants(child, tag)]);
}
async function page(projects = []) {
  const html = fs.readFileSync(path.join(__dirname, '../scripts/projects.html'), 'utf8');
  const nodes = new Map(), requests = [], navigation = [];
  const get = id => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Node(tag)},
    location: {assign: url => navigation.push(url)},
    setTimeout() { return 1; }, clearTimeout() {}, Date, JSON, Number, String, Array,
    fetch: async (url, options = {}) => {
      if (options.method === 'POST') {
        requests.push(JSON.parse(options.body));
        return {ok:true, json:async()=>({project:{id:'new-id',planning:{ready:false}}})};
      }
      return {ok:true,json:async()=>({projects,workspace:'/manager'})};
    }
  });
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  await new Promise(resolve => setImmediate(resolve));
  return {nodes, get, requests, navigation, context, html};
}
async function run() {
  const pending = {id:'pending',name:'导入项目',source:'import',planning:{ready:false,reason:'先生成项目规划书'},summary:{total:9,done:3,working:8}};
  const ready = {id:'ready',name:'已规划项目',planning:{ready:true},summary:{total:4,done:1,working:2,review:1,blocked:0}};
  const p = await page([pending, ready]);
  const cards = p.get('project-list').children;
  const pendingLinks = descendants(cards[0], 'A');
  assert.ok(!pendingLinks.some(a=>a.textContent==='查看功能'), 'pending projects must not offer the board');
  assert.deepEqual(pendingLinks.map(a=>a.textContent), ['开始规划']);
  assert.ok(cards[0].textContent.includes('待规划'));
  assert.ok(!cards[0].textContent.includes('%'), 'pending is not 0% implementation');
  assert.ok(!cards[0].textContent.includes('无法读取'), 'pending is not an error');
  assert.ok(descendants(cards[1], 'A').some(a=>a.textContent==='查看功能'));
  assert.equal(p.get('summary').children[1].children[0].textContent, '2', 'only ready projects contribute feature counts');

  const unknown = await page([{id:'old',name:'旧接口项目',summary:{total:9,done:9}}]);
  assert.ok(!descendants(unknown.get('project-list'), 'A').some(a=>a.textContent==='查看功能'));

  for (const mode of ['new','import']) {
    const form = await page();
    form.get('project-name').value = '示例'; form.get('project-directory').value='/sample';
    form.get('mode-'+mode).checked=true;
    await form.get('mode-'+mode).handlers.change();
    assert.equal(form.get('submit-project').textContent, mode==='new'?'创建并开始规划':'导入并生成规划书');
    await form.get('project-form').handlers.submit({preventDefault(){}});
    assert.equal(form.requests[0].mode, mode);
    assert.deepEqual(form.navigation, ['/planning?project=new-id']);
  }
  assert.ok(p.html.includes('type="radio"'));
  assert.ok(p.html.includes('<legend>项目来源</legend>'));
  return 4;
}
module.exports = run;
if (require.main === module) run().then(n=>console.log('Project onboarding: '+n+' scenarios passed.')).catch(error=>{console.error(error);process.exitCode=1;});
