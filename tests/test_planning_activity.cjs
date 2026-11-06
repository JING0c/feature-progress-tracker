const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{
 constructor(){this.children=[];this.handlers={};this._text='';}
 scrollIntoView(){} focus(){this.focused=true;} setAttribute(k,v){this[k]=v;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 addEventListener(k,v){this.handlers[k]=v;}
 set textContent(v){this._text=String(v);}
 get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 set innerHTML(v){throw Error('unsafe HTML');}
}
(async()=>{
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
 const context={window:{},document:{createElement:()=>new Node(),getElementById:get},Date};
 vm.runInNewContext(fs.readFileSync('scripts/planning-activity.js','utf8'),context);
 let data={records:[{id:'event-1',time:'2026-11-03T00:00:00Z',title:'预览（尚未保存）',detail:'<script>unsafe</script> 修改前：A 修改后：B'}]};
 const opened=[];const controller=context.window.createPlanningActivity({load:async()=>data,openSnapshot:id=>opened.push(id)});await controller.refresh();
 assert.match(get('activity-list').textContent,/尚未保存/);assert.match(get('activity-list').textContent,/<script>/);
 assert.match(get('activity-count').textContent,/1 条/);
 const entry=get('activity-list').children[0].children[0];entry.open=true;entry.handlers.toggle();await controller.refresh();assert.equal(get('activity-list').children[0].children[0].open,true,'refresh retains open record');
 data={records:[{id:'initial-save',time:'2026-11-03T00:00:00Z',title:'功能表已保存',detail:'历史版本：v-one\n--- 修改前\n+++ 修改后\n@@ -1 +1 @@\n # 项目规划书\n-尚未生成规划书。\n+正文'}]};await controller.refresh();assert.doesNotMatch(get('activity-list').children[0].children[0].children[0].textContent,/---|\+\+\+|# /,'list summary is readable, full diff stays inside details');

 data={records:[{id:'saved',time:'2026-11-03T00:00:00Z',title:'功能表已保存',state:'success',detail:'历史版本：v-secret\nF01 · 验收标准\n修改前：A\n修改后：B',snapshot:{id:'v-secret',saved_at:'2026-11-03T00:00:00Z',source:'功能表编辑',note:'补充导出'}}]};await controller.refresh();
 const saved=get('activity-list').children[0];const action=saved.children.find(n=>n.textContent==='查看当时功能表');assert.ok(action,'save record opens its exact table');await action.handlers.click();assert.deepEqual(opened,['v-secret']);assert.doesNotMatch(saved.textContent,/v-secret/,'internal hash is absent even in expanded detail');assert.match(saved.textContent,/修改后：B/);
 data={records:[{id:'preview',time:'2026-11-03T00:00:00Z',title:'预览（尚未保存）',state:'success',detail:'尚未保存'}],warnings:['一份旧功能表损坏，原文件已保留']};await controller.refresh();assert.doesNotMatch(get('activity-list').textContent,/查看当时功能表/);assert.match(get('activity-state').textContent,/损坏/);
 await get('open-plan-history').handlers.click();assert.equal(get('suggestion-activity').open,true,'sidebar opens the same records');
 data={records:[]};await controller.refresh('记录未保存：磁盘故障');assert.match(get('activity-state').textContent,/磁盘故障/);
 await controller.refresh();assert.match(get('activity-state').textContent,/还没有操作记录/);
 const waiting=[];const race=context.window.createPlanningActivity({load:()=>new Promise(resolve=>waiting.push(resolve))});
 const latest=race.refresh();waiting[1]({records:[]});await latest;waiting[0](data);await Promise.resolve();
 assert.equal(get('activity-list').children.length,0);
 console.log('Activity UI: persisted results, preview status, safe text, empty/warning and stale reads passed.');
})();
