(function(global){
 'use strict';
 global.createPlanningActivity=function(options){
  const $=id=>document.getElementById(id);let generation=0;
  function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
  async function refresh(warning=''){
   const current=++generation;
   try{
    const data=await options.load();if(current!==generation)return;
    const records=data.records||[];const list=$('activity-list');list.replaceChildren();
    $('activity-count').textContent=records.length?' · '+records.length+' 条记录':'';
    $('activity-state').textContent=warning||(records.length?'记录操作结果与具体改动；预览不代表已保存。':'还没有操作记录。生成建议、预览或保存后会在这里显示。');
    for(const record of records){
     const card=document.createElement('details');card.className='activity-entry';
     const time=new Date(record.time);const summary=node('summary',(Number.isNaN(time.getTime())?record.time:time.toLocaleString())+' · '+record.title);
     card.append(summary,node('pre',record.detail));list.append(card);
    }
   }catch(error){if(current===generation)$('activity-state').textContent=(warning?warning+'；':'')+'记录读取失败：'+error.message;}
  }
  $('refresh-activity').addEventListener('click',()=>refresh());
  refresh();return {refresh};
 };
})(window);
