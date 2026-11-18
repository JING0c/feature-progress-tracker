const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../scripts',name),'utf8');

// Both project pages must show the same bar: identity on the left, the same destinations in the same order.
function header(html){
 const match=html.match(/<header id="project-nav" class="project-nav">([\s\S]*?)<\/header>/);
 assert.ok(match,'project bar exists');
 const tabs=[...match[1].matchAll(/class="project-tab[^"]*"[^>]*>([^<]+)</g)].map(m=>m[1]);
 const current=[...match[1].matchAll(/aria-current="page"[^>]*>([^<]+)</g)].map(m=>m[1]);
 const last=/<\/nav><\/header>$/.test(match[0])&&match[1].trim().endsWith('</nav>')&&match[1].lastIndexOf('project-tabs')>match[1].lastIndexOf('project-crumb')?'tabs':'other';
 return{last,crumb:match[1].match(/<nav class="project-crumb"[\s\S]*?<\/nav>/)[0],tabs,current};
}
const planning=header(read('planning.html')),board=header(read('dashboard.html'));
assert.deepEqual(planning.tabs,['功能规划','进度看板','操作记录']);
assert.deepEqual(board.tabs,planning.tabs,'same destinations in the same order on both pages');
assert.equal(planning.crumb,board.crumb,'project identity block is identical');
assert.match(planning.crumb,/href="\/projects">项目总览</);
assert.equal(planning.last,'tabs');assert.equal(board.last,'tabs','tabs are the last item so they sit at the same right edge on both pages');
assert.deepEqual(planning.current,['功能规划']);assert.deepEqual(board.current,['进度看板']);

// The sidebar is the page's table of contents; file and export tools live in the collapsed "更多" menu.
const page=read('planning.html');
const sidebar=page.slice(page.indexOf('<aside id="plan-sidebar"'),page.indexOf('</aside>',page.indexOf('<aside id="plan-sidebar"')));
const more=sidebar.slice(sidebar.indexOf('<details class="plan-more">'));
for(const id of ['reload-plan','copy-plan','export-excel','download-plan','plan-location'])assert.ok(more.includes('id="'+id+'"'),id+' is inside 更多');
assert.ok(!sidebar.includes('open-plan-history'),'records are a project destination, not a page section');

// The bar stays visible and page toolbars sit below it.
assert.match(read('project-nav.css'),/\.project-nav\{position:sticky;top:0/);
assert.match(read('planning-workflow.css'),/\.plan-document-title\{position:sticky;top:var\(--project-nav-height/);
for(const name of ['planning-workflow.css','planning.html','planning-sheet.css']){for(const m of read(name).matchAll(/scroll-margin-top:([^;}]+)/g))assert.match(m[1],/--project-nav-height/,name+' scroll margin must clear the sticky project bar: '+m[1]);}
assert.ok(read('serve_dashboard.py').includes("'/assets/project-nav.js'")&&read('serve_dashboard.py').includes("'/assets/project-nav.css'"),'assets are served');

// The script scopes every destination to the current project and shows its name.
const nodes={},links=[{attrs:{'data-project-href':'/planning'}},{attrs:{'data-project-href':'/planning','data-project-hash':'#activity'}},{attrs:{'data-project-href':'/'}}];
for(const link of links)link.getAttribute=k=>link.attrs[k]??null;
const style={};
const context={location:{search:'?project=p-1'},URLSearchParams,
 document:{querySelectorAll:()=>links,getElementById:id=>nodes[id]||(nodes[id]={textContent:'',getBoundingClientRect:()=>({height:57})}),documentElement:{style:{setProperty:(k,v)=>style[k]=v}}}};
context.window=context;
vm.runInNewContext(read('project-nav.js'),context);
assert.deepEqual(links.map(l=>l.href),['/planning?project=p-1','/planning?project=p-1#activity','/?project=p-1']);
assert.equal(style['--project-nav-height'],'57px');
context.ProjectNav.setName('家庭购物清单');
assert.equal(nodes['nav-project-name'].textContent,'家庭购物清单');
console.log('Project nav: identical bar on planning and board, scoped links, sticky offsets, tools kept in 更多 passed.');
