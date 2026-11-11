const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.handlers = {}; this.attributes = {};
    this.dataset = {}; this.style = {}; this._text = ''; this.hidden = false;
    this.disabled = false; this.open = false; this.scrollTop = 0; this.scrollLeft = 0;
  }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(key, handler) { this.handlers[key] = handler; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(n => typeof n === 'string' ? n : n.textContent).join(''); }
  set innerHTML(_) { throw Error('Unsafe HTML'); }
  focus() { this.focused = true; }
  scrollIntoView() {}
  click() { this.clicked = true; return this.handlers.click?.(); }
  remove() { this.removed = true; }
}
function all(root, tag) {
  return root.children.flatMap(n => typeof n === 'string' ? [] : [...(n.tagName === tag ? [n] : []), ...all(n, tag)]);
}
const read = filename => fs.readFileSync(path.join(__dirname, '../scripts', filename), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function base(filename, handler) {
  const html = read(filename), nodes = new Map(), calls = [], timers = new Map();
  const markup = html.split('<script')[0];
  for (const match of markup.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const node = new Node(match[1]); node.hidden = /\shidden\b/.test(match[0]); nodes.set(match[2], node);
  }
  const get = id => { assert.ok(nodes.has(id), 'page references missing DOM #' + id); return nodes.get(id); };
  const context = vm.createContext({
    document: {getElementById:get, createElement:tag => new Node(tag), createTextNode:text => { const n = new Node('#text'); n.textContent=text; return n; }, body:new Node('body'), querySelectorAll:() => []},
    location:{search:'?project=project-a'}, URLSearchParams, Date, JSON, Number, String, Array, Set, Map, Blob,
    URL:{createObjectURL:() => 'blob:readonly', revokeObjectURL(){}}, navigator:{clipboard:{writeText:async()=>{}}},
    setTimeout(fn, delay) { const key=Symbol(); timers.set(key,{fn,delay}); return key; }, clearTimeout(key){timers.delete(key);},
    setInterval(fn,delay){const key=Symbol();timers.set(key,{fn,delay});return key;},
    fetch:async(url, options={}) => {
      calls.push({url,options});
      assert.equal(options.method || 'GET','GET','viewer must never issue mutations');
      assert.equal(options.body,undefined,'viewer must not send editable documents');
      assert.equal(options.headers,undefined,'viewer must not receive or send a write token');
      const data=await handler(url,options);
      return data && data.error ? {ok:false,json:async()=>data} : {ok:true,json:async()=>data,blob:async()=>new Blob([typeof data==='string'?data:JSON.stringify(data)])};
    }
  });
  context.window=context;
  function load(filename){vm.runInContext(read(filename),context,{filename});}
  function start(){const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];assert.equal(scripts.length,1);vm.runInContext(scripts[0][1],context,{filename});}
  return {html,nodes,get,calls,timers,context,load,start};
}
function model(revision='r1',title='上传图片') {
  return {revision,sheets:[
    {id:'features',kind:'feature-list',name:'功能清单',columns:['采用','大功能','小功能','功能介绍'],rows:[
      {key:'F01',feature_id:'F01',cells:['是','图片管理','','主功能']},
      {key:'F01-01',feature_id:'F01-01',cells:['否','图片管理',title,'说明：'+title+'\n验收：可以上传']}
    ]},
    {id:'details',name:'功能规划与验收',columns:['编号','功能名称'],rows:[{key:'F01',parent:null,cells:['F01','图片管理']},{key:'F01-01',parent:'F01',cells:['F01-01',title]}]},
    {id:'risks',name:'风险与待确认',columns:['事项','内容'],rows:[{key:'r',cells:['限制','待确认尺寸']}]}
  ]};
}
function projectFixture(overrides={}) {
  return {doc:{content:'# 项目规划书\n\n## 目标\n图片管理\n',revision:'r1',path:'/project-a/项目规划书.md',planning:{ready:true}},
    metadata:{id:'project-a',name:'图片工具',planning:{ready:true}},model:model(),records:[],history:{},...overrides};
}
async function planning(fixture=projectFixture(), hook) {
  const page=base('planning.html',async url => {
    const query=new URL('http://localhost'+url),route=query.pathname;
    assert.equal(query.searchParams.get('project'),'project-a','all project requests keep project identity');
    const handled=hook && await hook(route,query); if(handled!==undefined)return handled;
    if(route==='/api/plan') return fixture.doc;
    if(route==='/api/project')return fixture.metadata;
    if(route==='/api/plan/table')return fixture.model;
    if(route==='/api/plan/export')return 'XLSX fixture';
    if(route==='/api/plan/activity')return {records:fixture.records};
    if(route==='/api/plan/history')return fixture.history[query.searchParams.get('version')] || {error:'历史不存在'};
    throw Error('unexpected route '+route);
  });
  for(const module of ['planning-markdown.js','planning-sheet-view.js','planning-activity.js'])page.load(module);
  page.start();await tick();return page;
}
function button(root,text){const found=all(root,'button').find(node=>node.textContent===text);assert.ok(found,'button '+text);return found;}
async function run(){
  const fixture=projectFixture();const p=await planning(fixture);
  assert.equal(p.get('plan-document').hidden,false);
  assert.equal(p.get('board-link').href,'/?project=project-a');
  assert.match(p.get('project-title').textContent,/图片工具/);
  assert.equal(all(p.get('plan-sheet'),'input').length,0,'adoption is plain text');
  assert.match(p.get('plan-sheet').textContent,/不采用/);
  assert.equal(p.get('export-excel').href,'/api/plan/export?project=project-a');
  await p.get('export-excel').handlers.click({preventDefault(){}});assert.match(p.get('download-status').textContent,/Excel 已下载/);
  assert.ok([...p.timers.values()].some(t=>t.delay===3000),'polls saved files');
  assert.doesNotMatch(p.html,/<(?:form|textarea)\b|__PLANNING_TOKEN__/);

  await p.get('view-document').click();
  const docNodes=p.get('plan-content').children;
  await p.context.refreshPlan();
  assert.equal(p.get('plan-content').children,docNodes,'unchanged poll does not re-render content');
  assert.equal(p.get('plan-sheet').hidden,true,'poll preserves document view');
  assert.equal(p.get('view-document').attributes['aria-pressed'],'true');
  await p.get('view-sheet').click();
  await button(p.get('plan-sheet'),'风险与待确认').click();
  fixture.doc={...fixture.doc,content:fixture.doc.content+'新版\n',revision:'r2'};fixture.model=model('r2','上传新图片');
  await p.context.refreshPlan();
  assert.match(p.get('plan-sheet').textContent,/待确认尺寸/,'poll preserves selected chapter');
  assert.equal(button(p.get('plan-sheet'),'风险与待确认').attributes['aria-pressed'],'true');
  await button(p.get('plan-sheet'),'功能清单').click();
  const detail=all(p.get('plan-sheet'),'details')[1];detail.open=true;detail.handlers.toggle();
  const scroll=p.get('plan-sheet').children[2];scroll.scrollLeft=280;
  fixture.doc={...fixture.doc,content:fixture.doc.content+'再更新\n',revision:'r3'};fixture.model=model('r3','继续上传');
  await p.context.refreshPlan();
  assert.equal(all(p.get('plan-sheet'),'details')[1].open,true,'poll preserves expanded feature details');
  assert.equal(p.get('plan-sheet').children[2].scrollLeft,280,'poll preserves table scroll');
  await button(p.get('plan-sheet'),'查看功能明细').click();
  await button(p.get('plan-sheet'),'收起层级').click();
  fixture.doc={...fixture.doc,content:fixture.doc.content+'再次更新\n',revision:'r4'};fixture.model=model('r4');
  await p.context.refreshPlan();
  assert.equal(all(p.get('plan-sheet'),'tbody')[0].children[1].hidden,true,'poll preserves collapsed hierarchy');

  fixture.records=[{id:'saved',time:'2026-11-10T00:00:00Z',title:'功能表已保存',detail:'F01 名称更新',snapshot:{id:'old'}}];
  fixture.history.old={id:'old',content:'# 旧规划',model:model('old','旧功能'),saved_at:'2026-11-09T00:00:00Z',source:'对话保存',diff:'旧内容'};
  await p.get('open-plan-history').click();
  const saved=p.get('activity-list').children[0];
  const recordDetail=all(saved,'details')[0];recordDetail.open=true;recordDetail.handlers.toggle();
  await p.context.refreshPlan();assert.equal(all(p.get('activity-list'),'details')[0].open,true,'record expansion survives refresh');
  await button(p.get('activity-list'),'查看当时功能表').click();
  assert.equal(p.get('plan-history').hidden,false);
  assert.equal(p.get('history-download-excel').href,'/api/plan/export?version=old&project=project-a');
  assert.match(p.get('history-document').textContent,/旧规划/);
  await p.get('history-download-excel').handlers.click({preventDefault(){}});assert.ok(p.calls.some(c=>c.url==='/api/plan/export?version=old&project=project-a'));
  assert.doesNotMatch(p.get('plan-content').textContent,/旧规划/,'history never replaces current plan');
  await p.get('history-back').click();assert.equal(p.get('activity-timeline').hidden,false);

  let fail=false;const recover=projectFixture();const retry=await planning(recover,route=>fail&&route==='/api/plan'?{error:'文件暂不可读'}:undefined);
  const stable=retry.get('plan-content').textContent;fail=true;await retry.context.refreshPlan();
  assert.equal(retry.get('plan-content').textContent,stable);assert.match(retry.get('read-warning').textContent,/文件暂不可读/);
  assert.equal(retry.get('sync-status').dataset.error,'true');fail=false;await retry.context.refreshPlan();assert.equal(retry.get('sync-status').dataset.error,'false');
  const empty=await planning(projectFixture({doc:{content:'# 项目规划书\n\n尚未生成规划书，请在规划页面梳理需求。\n',revision:'empty',planning:{ready:false}}}));
  assert.equal(empty.get('plan-empty').hidden,false);assert.equal(empty.get('board-link').hidden,true);assert.equal(empty.get('download-tools').hidden,true);
  assert.match(empty.get('empty-message').textContent,/Codex 或 Claude Code/);
  assert.ok(!empty.calls.some(c=>c.url.startsWith('/api/plan/table')),'empty plan does not request an invalid model');

  let mismatch=true;const staleFixture=projectFixture();const stale=await planning(staleFixture,route=>route==='/api/plan/table'&&mismatch?model('wrong'):undefined);
  assert.equal(stale.get('plan-document').hidden,true);assert.match(stale.get('read-warning').textContent,/正在更新/);
  mismatch=false;await stale.context.refreshPlan();assert.equal(stale.get('plan-document').hidden,false);

  let resolveHistory;const race=await planning(projectFixture(),route=>route==='/api/plan/history'?new Promise(resolve=>{resolveHistory=resolve;}):undefined);
  const pending=race.context.showHistory('old');await tick();await race.get('history-back').click();
  resolveHistory(fixture.history.old);await pending;assert.equal(race.get('plan-history').hidden,true,'late history reply cannot reopen a closed page');

  let data={workspace:'/manager',projects:[{id:'pending',name:'待规划',planning:{ready:false},source:'new'},
    {id:'ready',name:'已规划',planning:{ready:true},summary:{total:4,done:1,working:2,review:1,blocked:0}}]};
  const projects=base('projects.html',async url=>{assert.equal(url,'/api/projects');return data;});projects.start();await tick();
  const cards=projects.get('project-list').children;
  assert.deepEqual(all(cards[0],'a').map(n=>n.textContent),['查看规划']);
  assert.equal(all(cards[0],'a')[0].href,'/planning?project=pending');
  assert.deepEqual(all(cards[1],'a').map(n=>n.textContent),['查看看板','查看规划']);
  assert.equal(projects.get('summary').children[1].children[0].textContent,'2');
  assert.doesNotMatch(projects.html,/<(?:form|input)\b|__PLANNING_TOKEN__/);
  data={workspace:'/manager',projects:[]};await projects.context.poll();assert.match(projects.get('project-list').textContent,/Codex 或 Claude Code/);
  console.log('Read-only viewers: 10 scenarios passed (GET-only, scope, adoption text, polling state, history, stale/error/empty, project navigation).');
  return 10;
}
module.exports=run;
if(require.main===module)run().catch(error=>{console.error(error);process.exitCode=1;});
