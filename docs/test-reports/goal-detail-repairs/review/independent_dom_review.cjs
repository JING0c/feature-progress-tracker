const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const [script, modelPath]=process.argv.slice(2);
class Node {constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.handlers={};this.style={};this._text='';this.hidden=false;}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this._text='';}setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,f){this.handlers[k]=f;}set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}set innerHTML(v){throw new Error('Unsafe HTML rendering');}}
const all=(node,tag)=>node.children.flatMap(n=>[...(n.tagName===tag?[n]:[]),...all(n,tag)]);
const sandbox={window:{},document:{createElement:t=>new Node(t)}};vm.runInNewContext(fs.readFileSync(script,'utf8'),sandbox);
const model=JSON.parse(fs.readFileSync(modelPath,'utf8'));const container=new Node('div');const view=sandbox.window.createPlanningSheetView(container);view.show(model);
const details=all(container,'details');assert.equal(details.length,2);for(const [i,tech,prep] of [[0,'Python技术唯一值','样本准备唯一值'],[1,'SQLite技术唯一值','图书准备唯一值']]){assert.equal(details[i].textContent.split(tech).length-1,1);assert.equal(details[i].textContent.split(prep).length-1,1);assert.ok(!details[i].textContent.includes('备注：采用：'));}
assert.ok(details[1].textContent.includes('所需技术：Go为示例，不能删'));assert.ok(details[1].textContent.includes('子项外加唯一值'));
const button=t=>all(container,'button').find(n=>n.textContent===t);button('展开技术与准备列').handlers.click();assert.ok(all(container,'th').some(n=>n.textContent==='所需技术'&&!n.hidden));assert.ok(all(container,'td').some(n=>n.textContent==='SQLite技术唯一值'&&!n.hidden));
button('查看功能明细').handlers.click();assert.ok(all(container,'td').some(n=>n.textContent==='子项备注唯一值\n外加列：子项外加唯一值'));
console.log(JSON.stringify({pass:true,checks:['real JSON model → real renderer','each detail tech/preparation once','handwritten wording retained','unknown notes retained','technical column toggle','detail view notes'],details:details.length}));
