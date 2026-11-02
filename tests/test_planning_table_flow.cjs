const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

async function run(){
  const nodes=new Map(),pending=[],calls=[],shown=[],downloads=[];
  let exportFails=false;
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',attributes:{},handlers:{},hidden:false,
      addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(k,v){this.attributes[k]=v;},
      replaceChildren(){},append(){},focus(){},scrollIntoView(){},remove(){},
      click(){downloads.push({href:this.href,filename:this.download});},querySelector(){return node('send');}
    });
    return nodes.get(id);
  };
  const context=vm.createContext({
    document:{getElementById:node,querySelector:node,createElement:()=>node(Symbol()),body:node('body')},
    location:{search:'?project=project-table'},URLSearchParams,
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},
    setInterval(){},setTimeout(){},renderPlanningMarkdown(){},
    createPlanningSheetView(){return{show(data){shown.push(data);},loading(){},error(){shown.push('error');},clear(){}};},
    URL:{createObjectURL(){return 'blob:export';},revokeObjectURL(){}},
    fetch:async(url,options={})=>{
      const route=url.split('?')[0],payload=options.body?JSON.parse(options.body):null;
      calls.push({url,route,payload});
      if(route==='/api/plan/table')return new Promise(resolve=>pending.push({payload,resolve}));
      if(route==='/api/plan/export')return{ok:!exportFails,json:async()=>({error:'导出失败'}),blob:async()=>({})};
      return{ok:true,json:async()=>route==='/api/plan'?{content:'',revision:'r',path:'/P/项目规划书.md',planning:{ready:false}}:{name:'P',source:'new',planning:{ready:false}}};
    }
  });
  const source=fs.readFileSync(path.join(__dirname,'../scripts/planning.html'),'utf8');
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  await new Promise(r=>setImmediate(r));
  vm.runInContext('showPlan("# older");showPlan("# current draft");dirty=true;',context);
  assert.equal(pending.length,2);
  pending[1].resolve({ok:true,json:async()=>({title:'current',sheets:[]})});
  await new Promise(r=>setImmediate(r));
  pending[0].resolve({ok:true,json:async()=>({title:'older',sheets:[]})});
  await new Promise(r=>setImmediate(r));
  assert.equal(shown.length,1);assert.equal(shown[0].title,'current','late responses cannot replace latest plan');
  await node('export-excel').handlers.click();
  const exported=calls.find(c=>c.route==='/api/plan/export');
  assert.equal(exported.payload.content,'# current draft');
  assert.equal(exported.url,'/api/plan/export?project=project-table');
  assert.equal(downloads[0].filename,'项目规划书.xlsx');
  assert.equal(node('save-ledger').disabled,true,'export never unlocks pending project');
  assert.match(node('status').textContent,/仍未保存/);
  exportFails=true;await node('export-excel').handlers.click();
  assert.equal(downloads.length,1);assert.match(node('status').textContent,/导出失败/);
  assert.ok(!calls.some(c=>c.route.endsWith('/save')));
  vm.runInContext('showPlan("# fallback")',context);
  pending[2].resolve({ok:false,json:async()=>({error:'cannot parse'})});
  await new Promise(r=>setImmediate(r));
  assert.equal(shown.at(-1),'error');
  node('view-document').handlers.click();
  assert.equal(node('plan-content').hidden,false);assert.equal(node('plan-sheet').hidden,true);
  node('view-sheet').handlers.click();
  assert.equal(node('plan-content').hidden,true);assert.equal(node('view-sheet').attributes['aria-pressed'],'true');
  console.log('Planning table flow: 5 scenarios passed (race, draft export, no unlock, failed export, source fallback).');
}
module.exports=run;
if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
