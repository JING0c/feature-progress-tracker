(function(global){
 'use strict';
 global.createPlanningHistoryView=function({request,downloadExcel,onClose=()=>{},localOperation=(title,work)=>work()}){
  const $=id=>document.getElementById(id);let current=null,sequence=0;
  const view=createPlanningSheetView($('history-sheet'));
  const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node;};
  function time(value){const date=new Date(value);return Number.isNaN(date.getTime())?'时间未记录':date.toLocaleString('zh-CN');}
  function filename(version){return '功能表-'+(version.saved_at||'历史记录').replace(/[^0-9A-Za-z\u4e00-\u9fff]+/g,'-');}
  function hide(){sequence++;current=null;$('plan-history').hidden=true;$('history-detail').hidden=true;}
  async function show(identity){
   const serial=++sequence;current=null;$('plan-history').hidden=false;$('history-detail').hidden=true;
   $('history-title').textContent='当时的功能表';$('history-status').textContent='正在读取该次保存的功能表…';
   $('history-title').focus?.({preventScroll:true});$('plan-history').scrollIntoView({block:'start'});
   try{
    const data=await request('/api/plan/history?version='+encodeURIComponent(identity));if(serial!==sequence)return;
    current=data;$('history-detail').hidden=false;
    const backup=data.source==='保存前文件版本';
    $('history-title').textContent=time(data.saved_at)+(backup?' 留存的功能表':' 保存的功能表');
    const source={'用户保存':'点击保存功能表','功能表编辑':'编辑功能表后保存','智能体生成':'规划生成后保存','规划保存':'保存规划书','保存前文件版本':'保存前留存的功能表，原修改时间未知'}[data.source]||data.source;
    $('history-meta').textContent='产生方式：'+source+(data.note?'。保存备注：'+data.note:'');
    const refs=$('history-references');refs.replaceChildren(text('p','保存时选中的参考项目：'));
    for(const repo of data.references||[]){if(!/^[\w.-]+\/[\w.-]+$/.test(repo.name))continue;const link=text('a',repo.name);link.href='https://github.com/'+repo.name;link.target='_blank';link.rel='noopener noreferrer';refs.append(link,text('span',' '));}
    if(!data.references?.length)refs.append(text('span','未选择参考项目'));
    view.show(data.model);renderPlanningMarkdown($('history-document'),data.content);
    $('history-diff').textContent=data.diff||'功能表正文与上次保存相同；备注或参考选择可能有变化。';
    $('history-status').textContent='只读副本。查看和下载不会修改当前功能表，也不会产生新的保存记录。'+(data.warnings?.length?' '+data.warnings.join('；'):'');
    $('plan-history').scrollIntoView({block:'start'});
   }catch(error){if(serial===sequence)$('history-status').textContent='这份功能表暂时无法读取：'+error.message+'。可以返回操作记录查看修改说明。';}
  }
  $('history-back').addEventListener('click',()=>{hide();onClose();});
  $('history-download-md').addEventListener('click',async()=>{
   if(!current)return;const version=current;try{await localOperation('下载当时功能表 Markdown',()=>{const url=URL.createObjectURL(new Blob([version.content],{type:'text/markdown;charset=utf-8'})),link=text('a','');link.href=url;link.download=filename(version)+'.md';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});}catch(error){if(current===version)$('history-status').textContent=error.message;}
  });
  $('history-download-excel').addEventListener('click',async()=>{
   if(!current)return;const version=current;$('history-download-excel').disabled=true;
   try{await downloadExcel(version.content,filename(version)+'.xlsx');if(current===version)$('history-status').textContent='已导出当时的功能表，当前规划未改动。';}
   catch(error){if(current===version)$('history-status').textContent=error.message;}finally{$('history-download-excel').disabled=false;}
  });
  return {show,hide};
 };
})(window);
