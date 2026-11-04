(function(global){
 'use strict';
 global.createPlanningProgress=function(options){
  const $=id=>document.getElementById(id);const running=new Set();let current=null,sequence=0;
  const panel=$('operation-progress-panel');
  function paint(task){
   if(current!==task)return;
   panel.hidden=false;panel.setAttribute('data-state',task.status);
   $('operation-title').textContent=task.title;
   $('operation-percent').textContent=task.percent+'%';
   const bar=$('operation-bar');bar.max=100;bar.value=task.percent;bar.setAttribute('aria-valuetext',task.percent+'%，'+task.stage);
   $('operation-stage').textContent=(task.status==='failed'?'失败于：':'当前步骤：')+task.stage;
   $('operation-detail').textContent=task.detail||'';
   $('operation-elapsed').textContent='已用时 '+Math.floor((Date.now()-task.started)/1000)+' 秒';
   $('operation-dismiss').hidden=task.status==='running';
  }
  $('operation-dismiss').addEventListener('click',()=>{if(current?.status!=='running'){current=null;panel.hidden=true;}});
  async function run(title,work,server=true){
   const id='op-'+Date.now().toString(36)+'-'+(++sequence)+'-'+Math.random().toString(36).slice(2,10);
   const task={id,title,percent:0,stage:'准备请求',detail:'',status:'running',started:Date.now()};running.add(task);current=task;paint(task);
   let polling=false;
   const tick=async()=>{
    if(current!==task||task.status!=='running')return;
    paint(task);if(!server||polling)return;polling=true;
    try{
     const state=await options.poll(id);
     if(current!==task||task.status!=='running')return;
     if(state.status==='pending')return;
     task.percent=Math.max(task.percent,Math.min(95,Number(state.percent)||0));
     task.stage=state.stage||task.stage;task.detail=state.detail||'';
     if(state.status==='failed')task.status='failed';paint(task);
    }catch(error){if(current===task&&task.status==='running'){task.detail='进度暂时无法读取，仍在等待操作结果。';paint(task);}}
    finally{polling=false;}
   };
   const timer=setInterval(tick,750);
   try{
    const result=await work(id,(percent,stage,detail='')=>{task.percent=Math.max(task.percent,Math.min(95,percent));task.stage=stage;task.detail=detail;paint(task);});
    task.status='completed';task.percent=100;task.stage='完成';task.detail='操作结果已返回';paint(task);return result;
   }catch(error){
    if(server){try{const state=await options.poll(id);if(state.status!=='pending'){task.percent=Math.max(task.percent,Math.min(95,Number(state.percent)||0));task.stage=state.stage||task.stage;}}catch(_){} }
    task.status='failed';task.detail=error.message;paint(task);throw error;
   }
   finally{clearInterval(timer);running.delete(task);if(current===task&&running.size){current=[...running].at(-1);paint(current);}}
  }
  return {run};
 };
})(window);
