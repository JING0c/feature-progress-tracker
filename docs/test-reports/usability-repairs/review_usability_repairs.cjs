const assert = require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const ROOT='/Users/olcgb/code/protuct_plan/scripts/';
class Node {constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.style={};this.open=false;this.hidden=false;this._text='';this.handlers={}} append(...items){this.children.push(...items)} prepend(...items){this.children.unshift(...items)} replaceChildren(...items){this.children=items;this._text=''} setAttribute(){} addEventListener(k,v){this.handlers[k]=v} set textContent(v){this._text=String(v);this.children=[]} get textContent(){return this._text+this.children.map(n=>n.textContent).join('')}}
const descendants=n=>n.children.flatMap(c=>[c,...descendants(c)]);
const cls=(n,c)=>(n.className||'').split(' ').includes(c);
const tick=()=>new Promise(r=>setImmediate(r));
function page(name, loader, search=''){
 const html=fs.readFileSync(ROOT+name,'utf8'),nodes=new Map();
 for(const m of html.split('<script')[0].matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)){const n=new Node(m[1]);n.hidden=/\shidden\b/.test(m[0]);nodes.set(m[2],n)}
 const get=id=>{assert.ok(nodes.has(id),id);return nodes.get(id)};
 const context=vm.createContext({document:{getElementById:get,createElement:t=>new Node(t),querySelectorAll:s=>{assert.equal(s,'details[open]');return [...nodes.values()].flatMap(n=>[n,...descendants(n)]).filter(n=>n.tagName==='details'&&n.open)}},location:{search},URLSearchParams,Date,JSON,Set,Map,Array,String,Number,setInterval(){},setTimeout(){},clearTimeout(){},fetch:async(url,options={})=>{assert.equal(options.method||'GET','GET');return {ok:true,json:async()=>loader(url)}}});
 vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],context);return {html,get,context};
}
(async()=>{
 const item=(id,name,status='进行中',children=[],checked=false)=>({id,name,checked,children,fields:{'状态':status,'验收':'完整验收 '+name,'其他字段':'<script>literal</script>'},notes:['原始注释 '+name]});
 let data={groups:[{id:'F01',name:'组',items:[item('F01-01','父','待审核',[item('F01-01-01','中层','受阻',[item('F01-01-01-01','叶','已完成',[],true)])]),item('F01-02','空叶','未开始')]}]};
 const dash=page('dashboard.html',()=>data);await tick();
 let cards=()=>descendants(dash.get('board')).filter(n=>cls(n,'card'));
 let [parent,middle,leaf,empty]=cards();
 assert.equal(cards().length,4);assert.ok(cls(parent,'status-review'));assert.ok(cls(middle,'status-blocked'));assert.ok(cls(leaf,'status-done'));
 for(const [index,p] of [[0,parent],[1,middle]]){assert.ok(cls(p.children[1],'children'));const details=p.children[2];assert.equal(details.tagName,'details');assert.equal(details.open,false);assert.match(details.textContent,/完整验收/);assert.match(details.textContent,/原始注释/);assert.match(details.textContent,/<script>literal<\/script>/)}
 assert.ok(cls(leaf.children[1],'meta'));assert.equal(leaf.children.filter(n=>n.tagName==='details').length,0);
 parent.open=false;middle.open=true;middle.children[2].open=true;leaf.open=true;data.groups[0].name='组 新';await dash.context.poll();
 [parent,middle,leaf]=cards();assert.equal(parent.open,false);assert.equal(middle.open,true);assert.equal(middle.children[2].open,true);assert.equal(leaf.open,true);assert.equal(parent.children[2].open,false);
 assert.match(dash.html,/\.card\[open\] > summary \.arrow/);assert.doesNotMatch(dash.html,/details\[open\] \.arrow/);
 console.log('Independent dashboard: 3 levels, status class, every field/note, hidden descendant disclosure persistence, scoped arrow selector PASS');
 let projects={workspace:'/very/long/管理目录',projects:[{id:'p1',name:'一',directory:'/very/long/one',planning:{ready:false}},{id:'p2',name:'二',directory:'/very/long/two',planning:{ready:false}}]};
 const p=page('projects.html',()=>projects);await tick();
 const locations=()=>descendants(p.get('project-list')).filter(n=>cls(n,'file-location'));
 assert.equal(locations().length,2);assert.ok(locations().every(n=>!n.open));assert.equal(locations()[0].children[0].textContent,'文件位置');assert.equal(p.get('workspace-location').open,false);
 locations()[0].open=true;p.get('workspace-location').open=true;projects.projects.reverse();projects.projects[1].directory='/moved/one';await p.context.poll();
 assert.equal(locations()[0].open,false);assert.equal(locations()[1].open,true);assert.match(locations()[1].textContent,/moved\/one/);assert.equal(p.get('workspace-location').open,true);
 projects.workspace=null;await p.context.poll();assert.equal(p.get('workspace-location').hidden,true);assert.equal(p.get('workspace-mode').hidden,false);
 console.log('Independent paths: default collapse, project identity/reorder persistence, full updated path retained, workspace/single mode PASS');
 const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
 const context=vm.createContext({window:{},document:{getElementById:get,createElement:t=>new Node(t)},Date,Number,Set});
 vm.runInContext(fs.readFileSync(ROOT+'planning-activity.js','utf8'),context);
 const mapping={save_plan:'保存规划',edit_features:'编辑功能表',record_suggestions:'记录功能建议',preview_suggestions:'预览采纳建议',search_references:'搜索 GitHub 参考',select_references:'保存参考选择',prepare_source_review:'准备源码核对',submit_source_review:'提交源码核对',generate_ledger:'生成功能台账',save_ledger:'保存功能台账',update_feature_progress:'更新功能进度',export_project:'导出规划书',create_project:'创建项目',read_project:'读取项目'};
 const records=Object.freeze(Object.keys(mapping).map((title,i)=>Object.freeze({id:String(i),time:'2020-01-01T00:00:00Z',state:'failed',title:title+' 失败',detail:'原始细节 '+title})));const raw=JSON.stringify(records);
 const controller=context.window.createPlanningActivity({load:async()=>({records})});await controller.refresh();assert.equal(JSON.stringify(records),raw);
 for(const [i,title] of Object.keys(mapping).entries()){const summary=get('activity-list').children[i].children[0].children[0];assert.ok(summary.textContent.includes(mapping[title]+'失败'));assert.ok(!summary._text.includes(title));}
 console.log('Independent legacy localization: 14 historical labels, frozen original records unchanged, detail retained PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
