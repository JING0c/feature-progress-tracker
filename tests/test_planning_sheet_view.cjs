const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tag) { this.tagName=tag; this.children=[]; this.attributes={}; this.handlers={}; this.style={}; this._text=''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; this._text=''; }
  setAttribute(key,value) { this.attributes[key]=String(value); }
  addEventListener(key,handler) { this.handlers[key]=handler; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text+this.children.map(node=>node.textContent).join(''); }
  set innerHTML(_) { throw Error('Only safe text DOM is allowed'); }
}
function all(root,tag) { return root.children.flatMap(n=>[...(n.tagName===tag?[n]:[]),...all(n,tag)]); }
function run() {
  const sandbox={window:{},document:{createElement:tag=>new Node(tag)}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../scripts/planning-sheet-view.js'),'utf8'),sandbox);
  const container=new Node('div'),view=sandbox.window.createPlanningSheetView(container);
  const columns=['编号','功能名称','说明与验收','优先级','依赖','备注'];
  const row=(key,parent,depth,name)=>({key,parent,depth,cells:[key,name,'<script>alert(1)</script>\n多行内容','','','']});
  const model={sheets:[{id:'features',name:'功能规划',columns,rows:[row('F01',null,0,'借阅'),row('F01-01','F01',1,'借出'),row('F01-01-01','F01-01',2,'居民校验'),row('F02',null,0,'备份')]},{id:'risk',name:'风险事项',columns:['事项','内容'],rows:[{key:'risk-1',parent:null,depth:0,cells:['本地日期','待确认日期来源']}]}]};
  view.show(model);
  const bodyRows=()=>all(container,'tbody')[0].children;
  const button=name=>all(container,'button').find(n=>n.textContent===name||n.attributes['aria-label']===name);
  assert.equal(bodyRows().length,4);
  assert.equal(all(container,'script').length,0);
  assert.match(container.textContent,/<script>alert\(1\)<\/script>/);
  assert.equal(all(container,'td').some(n=>n.textContent.includes('多行内容')),true);
  button('收起 F01 借阅').handlers.click();
  assert.deepEqual(bodyRows().map(n=>n.hidden),[false,true,true,false]);
  assert.equal(button('展开 F01 借阅').attributes['aria-expanded'],'false');
  button('展开 F01 借阅').handlers.click();
  button('收起 F01-01 借出').handlers.click();
  assert.deepEqual(bodyRows().map(n=>n.hidden),[false,false,true,false]);
  button('风险事项').handlers.click();
  assert.match(container.textContent,/待确认日期来源/);
  button('功能规划').handlers.click();
  assert.deepEqual(bodyRows().map(n=>n.hidden),[false,false,true,false],'fold state persists across tabs');
  button('全部展开').handlers.click();
  assert.ok(bodyRows().every(n=>!n.hidden));
  button('收起层级').handlers.click();
  assert.deepEqual(bodyRows().map(n=>n.hidden),[false,true,true,false]);
  view.show({sheets:[]}); assert.match(container.textContent,/还没有规划内容/);
  view.error(); assert.match(container.textContent,/文档视图/);
  view.show({sheets:[{id:'cycle',name:'异常层级',columns,rows:[row('a','b',1,'甲'),row('b','a',1,'乙')]}]});
  assert.equal(bodyRows().length,2,'defensive cycle traversal terminates');
  view.clear();
  const listing={id:'list',kind:'feature-list',name:'功能清单',columns:['大功能','小功能','细分功能','功能介绍'],
    rows:[
      {key:'list1',parent:null,cells:['F01 借阅','F01-01 借出','居民校验','检查居民编号']},
      {key:'list2',parent:null,cells:['F01 借阅','F01-01 借出','额度校验','检查借阅数量']},
      {key:'list3',parent:null,cells:['F02 预约','F02-01 借出','日期校验','<img src=x>']}
    ],merges:[{row:0,column:0,rowSpan:2},{row:0,column:1,rowSpan:2}]};
  view.show({sheets:[model.sheets[0],listing]});
  assert.equal(all(container,'th').filter(n=>n.attributes.scope==='col')[1].textContent,'大功能','prefer the reference-style list');
  const cells=all(container,'td');
  assert.equal(cells.filter(n=>n.attributes.rowspan==='2').length,2);
  assert.equal(bodyRows()[1].children.length,3,'covered cells are omitted rather than repeated');
  assert.equal(bodyRows()[2].children.length,5,'a different parent retains its own cells');
  assert.equal(cells.filter(n=>n.textContent==='F01 借阅').length,1);
  assert.equal(all(container,'img').length,0);
  assert.ok(!button('全部展开'),'flat list has no misleading collapse controls');
  button('查看功能明细').handlers.click();
  assert.equal(all(container,'th').filter(n=>n.attributes.scope==='col')[1].textContent,'编号');
  console.log('Planning sheet view: hierarchy, nested collapse, tab state, batch controls, safe content, empty/error/cycle checks passed.');
}
module.exports=run;
if(require.main===module)run();
