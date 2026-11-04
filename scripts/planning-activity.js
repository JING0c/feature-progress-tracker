(function(global){
 'use strict';
 global.createPlanningActivity=function(options){
  const $=id=>document.getElementById(id);const expanded=new Set();let generation=0,displayGeneration=0;
  function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
  async function refresh(warning=''){
   const current=++generation;
   try{
    const data=await options.load();if(current!==generation)return;
    const records=data.records||[];const list=$('activity-list');const scroll=list.scrollTop||0;displayGeneration=current;list.replaceChildren();
    $('activity-count').textContent=records.length?' · '+records.length+' 条记录':'';
    $('activity-state').textContent=warning||(records.length?'记录操作结果与具体改动；预览不代表已保存。':'还没有操作记录。生成建议、预览或保存后会在这里显示。');
    for(const record of records){
     const card=document.createElement('details');card.className='activity-entry';card.open=expanded.has(record.id);
     card.addEventListener('toggle',()=>{if(current===displayGeneration){card.open?expanded.add(record.id):expanded.delete(record.id);}});
     const time=new Date(record.time);const summary=node('summary',(Number.isNaN(time.getTime())?record.time:time.toLocaleString())+' · '+record.title);
     const lines=record.detail.split('\n').map(line=>line.trim()).filter(Boolean);
     const description=lines.filter(line=>/^(F\d|新增 F|移除 F)/.test(line)).join('；')||(/^(功能表|规划书)已保存$/.test(record.title)?'规划内容已保存，可展开查看完整变更':lines.find(line=>!/^历史版本：|^来源：|^[-+#@|`]|^\s*$/.test(line))||'已生成规划内容，可展开查看详情');
     summary.append(node('span',description.slice(0,160)+(description.length>160?'…':'')));
     card.append(summary,node('pre',record.detail));list.append(card);
    }
    list.scrollTop=scroll;
   }catch(error){if(current===generation)$('activity-state').textContent=(warning?warning+'；':'')+'记录读取失败：'+error.message;}
  }
  $('refresh-activity').addEventListener('click',()=>refresh());
  refresh();return {refresh};
 };
})(window);
