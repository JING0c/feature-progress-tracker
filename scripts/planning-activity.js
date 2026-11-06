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
    $('activity-count').textContent=records.length?' · '+records.length+' 条':'';
    const warnings=[warning,...(data.warnings||[])].filter(Boolean);
    $('activity-state').textContent=warnings.join('；')||(records.length?'已显示 '+records.length+' 条记录，按时间从新到旧排列。预览和讨论不会另存功能表。':'还没有操作记录。生成建议、预览或保存后会在这里显示。');
    for(const record of records){
     const card=node('article','');card.className='activity-card';
     const details=node('details','');details.className='activity-entry';details.open=expanded.has(record.id);
     details.addEventListener('toggle',()=>{if(current===displayGeneration){details.open?expanded.add(record.id):expanded.delete(record.id);}});
     const time=new Date(record.time),saved=record.snapshot;
     const summary=node('summary',(Number.isNaN(time.getTime())?'时间未记录':time.toLocaleString('zh-CN'))+' · '+record.title);
     const visibleDetail=record.detail.split('\n').filter(line=>!/^历史版本：/.test(line.trim())).join('\n');
     const lines=visibleDetail.split('\n').map(line=>line.trim()).filter(Boolean);
     const description=lines.filter(line=>/^(F\d|新增 F|移除 F)/.test(line)).join('；')||saved?.note||(/^(功能表|规划书)已保存$/.test(record.title)?'规划内容已保存，展开查看具体改动':lines.find(line=>!/^来源：|^[-+#@|`]|^\s*$/.test(line))||'展开查看具体内容');
     summary.append(node('span',description.slice(0,160)+(description.length>160?'…':'')));
     details.append(summary,node('pre',visibleDetail));card.append(details);
     if(record.state==='history')card.append(node('p',saved?.source==='保存前文件版本'?'这是保存前自动留存的文件；上方是留存时间，原修改时间未知。':'这是早期保存的功能表，没有对应的完整操作日志。'));
     if(saved){
      const button=node('button','查看当时功能表');button.type='button';button.className='secondary';
      button.addEventListener('click',()=>{$('activity-timeline').hidden=true;return options.openSnapshot?.(saved.id);});card.append(button);
     }else if(record.snapshot_missing)card.append(node('p','当时的功能表暂时不可读取，操作说明仍保留。'));
     list.append(card);
    }
    list.scrollTop=scroll;
   }catch(error){if(current===generation)$('activity-state').textContent=(warning?warning+'；':'')+'记录读取失败：'+error.message;}
  }
  async function open({reload=true}={}){
   options.closeSnapshot?.();$('activity-timeline').hidden=false;$('suggestion-activity').open=true;
   $('activity-timeline').focus?.({preventScroll:true});$('suggestion-activity').scrollIntoView({block:'start'});
   if(reload)await refresh();
  }
  $('open-plan-history').addEventListener('click',()=>open());
  $('refresh-activity').addEventListener('click',()=>refresh());
  refresh();return {refresh,open};
 };
})(window);
