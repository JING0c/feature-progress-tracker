const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Node{
 constructor(tag){this.tagName=tag;this.children=[];this.handlers={};this.attributes={};this.dataset={};this.hidden=false;this.className='';this._text='';this.open=false;}
 append(...n){this.children.push(...n);}prepend(...n){this.children.unshift(...n);}replaceChildren(...n){this.children=n;this._text='';}
 setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,fn){(this.handlers[k]??=[]).push(fn);}
 dispatch(k,e={preventDefault(){this.prevented=true;}}){for(const fn of this.handlers[k]||[])fn(e);return e;}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 focus(){focused=this;}querySelector(sel){return all(this).find(n=>n.tagName===sel)||null;}
}
let focused=null;
const all=root=>root.children.flatMap(n=>[n,...all(n)]);
// Drives the real board script with an in-memory ledger; the DOM is a minimal stub.
async function run(){
 const ids=new Map(),node=id=>{if(!ids.has(id))ids.set(id,new Node('div'));return ids.get(id);};
 const docHandlers={};
 const ledger={groups:[{id:'F01',name:'购物清单',items:[
  {id:'F01-01',name:'添加商品',checked:false,issue:true,dispute:false,notes:['旧记录：曾经重开'],children:[],fields:{'状态':'待审核','验收':'名称必填。'.repeat(40),'依赖':'无','说明':'输入名称和数量','所需技术':'表单','执行 Agent':'A','实现证据':'测试通过','审核 Agent':'B','评分':'90'}},
  {id:'F01-02',name:'查看清单',checked:false,notes:[],fields:{'状态':'未开始','验收':'显示全部'},children:[{id:'F01-02-01',name:'空清单提示',checked:false,notes:[],fields:{'状态':'未开始','验收':'无商品时提示'},children:[]}]}]}]};
 const context=vm.createContext({
  document:{getElementById:node,createElement:tag=>new Node(tag),querySelectorAll:sel=>sel==='details.card'?all(node('board')).filter(n=>n.tagName==='details'):[],addEventListener:(k,fn)=>docHandlers[k]=fn,title:''},
  location:{search:'?project=p'},URLSearchParams,setInterval(){},
  fetch:async url=>({ok:true,json:async()=>url.startsWith('/api/project')?{name:'P'}:JSON.parse(JSON.stringify(ledger))})});
 const html=fs.readFileSync(path.join(__dirname,'../scripts/dashboard.html'),'utf8');
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));
 const cards=all(node('board')).filter(n=>n.tagName==='details');
 const leaf=cards.find(c=>c.dataset.key==='F01:F01-01');
 assert.ok(!leaf.textContent.includes('名称必填'),'the card itself stays compact; long fields are not inside it');
 const e=leaf.children[0].dispatch('click');
 assert.ok(e.prevented,'a card without children does not expand in place');
 const panel=node('detail-panel');
 assert.equal(panel.hidden,false);
 assert.equal(node('detail-title').textContent,'F01-01 添加商品');assert.equal(focused,node('detail-title'),'focus moves to the panel heading');
 assert.match(node('detail-badges').textContent,/待审核.*有问题/);
 assert.equal(node('detail-badges').children[0].className,'badge review','panel badge has the same colour class as the card');
 ledger.groups[0].items[0].fields['状态']='已完成';vm.runInContext('render('+JSON.stringify(ledger)+')',context);
 assert.equal(node('detail-badges').children[0].textContent,'待审核（状态待核实）','unchecked 已完成 reads the same as on the card');
 ledger.groups[0].items[0].fields['状态']='待审核';vm.runInContext('render('+JSON.stringify(ledger)+')',context);
 const body=node('detail-body'),top=body.children.filter(n=>n.className==='field').map(n=>n.children[0].textContent);
 assert.deepEqual(top,['状态','验收','依赖'],'main fields come first');
 const groups=body.children.filter(n=>n.className==='detail-group').map(n=>n.children[0].textContent);
 assert.deepEqual(groups,['说明、技术与准备（2）','实施与证据（2）','审核与评分（2）','其他记录（1）']);
 assert.ok(body.children.filter(n=>n.className==='detail-group').every(g=>!g.open),'secondary groups start folded');
 body.children.find(n=>n.className==='detail-group').open=true;body.children.find(n=>n.className==='detail-group').dispatch('toggle');
 // Polling re-renders the board; the open panel and its open group survive.
 vm.runInContext('render('+JSON.stringify(ledger)+')',context);
 assert.equal(panel.hidden,false);assert.equal(node('detail-title').textContent,'F01-01 添加商品');
 assert.equal(node('detail-body').children.find(n=>n.className==='detail-group').open,true,'open group survives refresh');
 // Parent cards still expand to show their children, and the panel can walk down and back up.
 const parent=all(node('board')).filter(n=>n.tagName==='details').find(c=>c.dataset.key==='F01:F01-02');
 assert.ok(!parent.children[0].dispatch('click').prevented,'a card with children still expands its children');
 assert.match(node('detail-body').textContent,/包含 1 个更细的功能点/);
 all(node('detail-body')).find(n=>n.textContent.startsWith('F01-02-01'))?.dispatch('click');
 assert.equal(node('detail-title').textContent,'F01-02-01 空清单提示');assert.match(node('detail-path').textContent,/购物清单 › 查看清单/);
 all(node('detail-body')).find(n=>n.textContent.startsWith('↑ 上一级'))?.dispatch('click');
 assert.equal(node('detail-title').textContent,'F01-02 查看清单');
 docHandlers.keydown({key:'Escape'});
 assert.equal(panel.hidden,true,'Escape closes the panel');
 leaf.children[0].dispatch('click');node('detail-close').dispatch('click');assert.equal(panel.hidden,true,'← 返回看板 closes the panel');
 const current=all(node('board')).filter(n=>n.tagName==='details').find(c=>c.dataset.key==='F01:F01-01');
 assert.equal(focused,current.children[0],'closing returns focus to the (re-rendered) card it came from');
 // A function removed from the ledger closes its open panel rather than showing stale data.
 leaf.children[0].dispatch('click');ledger.groups[0].items.shift();vm.runInContext('render('+JSON.stringify(ledger)+')',context);assert.equal(panel.hidden,true);
 console.log('Board detail panel: compact cards, grouped fields, refresh-safe panel, child/parent navigation, close paths passed.');
}
run().catch(e=>{console.error(e);process.exit(1);});
