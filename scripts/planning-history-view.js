(function(global){
 'use strict';
 global.createPlanningHistoryView=function({request,downloadExcel}){
  const $=id=>document.getElementById(id);let current=null,sequence=0;
  const view=createPlanningSheetView($('history-sheet'));
  const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node;};
  function time(value){return new Date(value).toLocaleString('zh-CN');}
  async function show(identity){
   const serial=++sequence;$('history-status').textContent='正在读取历史版本…';
   try{
    const data=await request('/api/plan/history?version='+encodeURIComponent(identity));if(serial!==sequence)return;
    current=data;$('history-detail').hidden=false;$('history-title').textContent='历史版本 '+data.id;
    $('history-meta').textContent=time(data.saved_at)+' · '+data.source+(data.note?' · '+data.note:'');
    const refs=$('history-references');refs.replaceChildren(text('p','本版参考项目：'));
    for(const repo of data.references||[]){if(!/^[\w.-]+\/[\w.-]+$/.test(repo.name))continue;const link=text('a',repo.name);link.href='https://github.com/'+repo.name;link.target='_blank';link.rel='noopener noreferrer';refs.append(link,text('span',' '));}
    if(!data.references?.length)refs.append(text('span','未选择参考项目'));
    view.show(data.model);renderPlanningMarkdown($('history-document'),data.content);$('history-diff').textContent=data.diff||'与上一版正文相同；可查看修改说明和参考项目选择。';$('history-status').textContent='历史只读，当前规划保持原样。';
   }catch(error){if(serial===sequence)$('history-status').textContent=error.message;}
  }
  $('open-plan-history').addEventListener('click',async()=>{
   const serial=++sequence;
   $('plan-history').hidden=false;$('history-status').textContent='正在读取版本列表…';
   try{
    const data=await request('/api/plan/history');if(serial!==sequence)return;const box=$('history-list');box.replaceChildren();
    for(const version of data.versions){
     const item=document.createElement('div');item.className='history-item';const button=text('button','查看 '+version.id.slice(0,14));button.type='button';button.addEventListener('click',()=>show(version.id));
     item.append(button,text('span',time(version.saved_at)+' · '+version.source+' · '+(version.references||[]).length+'个参考项目'),text('span',version.note||''));box.append(item);
    }
    $('history-status').textContent=data.versions.length?'共 '+data.versions.length+' 个归档版本。':'尚无归档版本；以后每次网页成功保存都会归档。';$('plan-history').scrollIntoView({block:'start'});
   }catch(error){if(serial===sequence)$('history-status').textContent=error.message;}
  });
  $('history-download-md').addEventListener('click',()=>{
   if(!current)return;const url=URL.createObjectURL(new Blob([current.content],{type:'text/markdown;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=current.id+'.md';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('history-download-excel').addEventListener('click',async()=>{
   if(!current)return;const version=current;$('history-download-excel').disabled=true;
   try{await downloadExcel(version.content,version.id+'.xlsx');$('history-status').textContent='已导出该历史版本，当前规划未改动。';}
   catch(error){$('history-status').textContent=error.message;}finally{$('history-download-excel').disabled=false;}
  });
 };
})(window);
