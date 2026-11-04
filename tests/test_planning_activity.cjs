const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{
 constructor(){this.children=[];this.handlers={};this._text='';}
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
 const controller=context.window.createPlanningActivity({load:async()=>data});await controller.refresh();
 assert.match(get('activity-list').textContent,/尚未保存/);assert.match(get('activity-list').textContent,/<script>/);
 assert.match(get('activity-count').textContent,/1 条记录/);
 const entry=get('activity-list').children[0];entry.open=true;entry.handlers.toggle();await controller.refresh();assert.equal(get('activity-list').children[0].open,true,'refresh retains open record');
 data={records:[{id:'initial-save',time:'2026-11-03T00:00:00Z',title:'功能表已保存',detail:'历史版本：v-one\n--- 修改前\n+++ 修改后\n+# 规划书'}]};await controller.refresh();assert.doesNotMatch(get('activity-list').children[0].children[0].textContent,/---|\+\+\+|# /,'list summary is readable, full diff stays inside details');
 data={records:[]};await controller.refresh('记录未保存：磁盘故障');assert.match(get('activity-state').textContent,/磁盘故障/);
 await controller.refresh();assert.match(get('activity-state').textContent,/还没有操作记录/);
 const waiting=[];const race=context.window.createPlanningActivity({load:()=>new Promise(resolve=>waiting.push(resolve))});
 const latest=race.refresh();waiting[1]({records:[]});await latest;waiting[0](data);await Promise.resolve();
 assert.equal(get('activity-list').children.length,0);
 console.log('Activity UI: persisted results, preview status, safe text, empty/warning and stale reads passed.');
})();
