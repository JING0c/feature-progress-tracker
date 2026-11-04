(function(global){
 'use strict';
 global.createPlanningSuggestions=function(options){
  const $=id=>document.getElementById(id),selected=new Set();let record=null,busy=false,fields=[],generation=0,previewPending=false,savedRevision=null,lastError='';
  const text=(tag,value)=>{const el=document.createElement(tag);el.textContent=value;return el;};
  function sync(){
   const state=options.getPlan(),stale=record?.plan_revision!==state.revision;
   $('generate-suggestions').disabled=busy||!state.ready;
   $('preview-suggestions').disabled=busy||!selected.size||stale||state.dirty;
   fields.forEach(f=>f.disabled=busy||stale||state.dirty);
   const expired='功能表已更新，这批建议已过期，请重新分析。';
   const savedMessage='建议预览的编辑结果已保存。可重新分析最新功能表，获取下一轮建议。';
   if(lastError){$('suggestions-status').textContent=lastError;}
   else if(savedRevision===state.revision&&savedRevision){$('suggestions-status').textContent=savedMessage;}
   else if(record?.id&&stale)$('suggestions-status').textContent=expired;
   else if([$('suggestions-status').textContent].some(text=>text===expired||text===savedMessage))$('suggestions-status').textContent='子智能体给出 '+(record?.suggestions.length||0)+' 条建议，默认不采纳。';
  }
  function render(data){
   record=data;previewPending=false;savedRevision=null;lastError='';selected.clear();fields=[];$('suggestions-list').replaceChildren();$('suggestion-diff').hidden=true;
   for(const item of data.suggestions||[]){
    const card=document.createElement('article');card.className='suggestion-card';
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=false;check.setAttribute('aria-label','采纳 '+item.title);
    check.addEventListener('change',()=>{check.checked?selected.add(item.id):selected.delete(item.id);sync();});fields.push(check);label.append(check,text('strong',item.title));
    const detail=document.createElement('details');detail.append(text('summary','查看具体修改'));
    for(const change of item.changes){detail.append(text('h4',(change.action==='add'?'新增 ':'调整 ')+change.id));for(const [key,value] of Object.entries(change.fields))detail.append(text('p',key+'：'+value));}
    card.append(label,text('p',item.reason),detail);$('suggestions-list').append(card);
   }
   $('suggestions-status').textContent=data.id?(data.suggestions.length?'子智能体给出 '+data.suggestions.length+' 条建议，默认不采纳。':'本轮没有需要补充的建议。'):'让子智能体检查当前功能的遗漏与改进空间。';sync();
  }
  $('generate-suggestions').addEventListener('click',async()=>{
   if(busy)return;const state=options.getPlan();
   if(state.dirty){$('suggestions-status').textContent='请先保存当前功能表修改，再生成建议。';return;}
   const focus=options.getFocus?.()||'';
   if(focus.length>3000){$('suggestions-status').textContent='建议重点最多3000字，请精简后生成；输入内容已保留。';return;}
   generation++;savedRevision=null;lastError='';options.setBusy(true);$('suggestions-progress').hidden=false;
   $('suggestions-status').textContent='独立 Codex 子智能体正在分析当前功能…';
   try{const data=await options.request('/api/plan/suggestions',{revision:state.revision,focus,discussion:options.getDiscussion?.()||''});render(data);}
   catch(error){lastError='建议未生成：'+error.message;$('suggestions-status').textContent=lastError;}
   finally{$('suggestions-progress').hidden=true;options.setBusy(false);}
  });
  $('preview-suggestions').addEventListener('click',async()=>{
   if(busy||!record)return;const state=options.getPlan();if(state.dirty){$('suggestions-status').textContent='请先保存当前功能表修改。';return;}
   lastError='';options.setBusy(true);
   try{
    const data=await options.request('/api/plan/suggestions/preview',{revision:state.revision,suggestion_id:record.id,selected:[...selected]});
    $('suggestion-diff').hidden=false;$('suggestion-diff-text').textContent=data.diff;
    const changedIds=[...new Set(record.suggestions.filter(item=>selected.has(item.id)).flatMap(item=>item.changes.map(change=>change.id)))];
    await options.onPreview({...data,changedIds});previewPending=true;$('suggestions-status').textContent='所选建议已放入功能表预览，尚未保存；可继续编辑，再点击表格上方“保存功能表”。';
   }catch(error){$('suggestions-status').textContent=error.message;}
   finally{options.setBusy(false);}
  });
  options.request('/api/plan/suggestions').then(data=>{if(!generation)render(data);}).catch(error=>{$('suggestions-status').textContent=error.message;});
  return {discardPreview(){if(previewPending){previewPending=false;$('suggestion-diff').hidden=true;$('suggestions-status').textContent='已放弃上次预览，没有保存该预览；可重新选择建议并预览。';}},onSaved(revision){if(previewPending){savedRevision=revision;previewPending=false;sync();}},setBusy(value){busy=value;sync();}};
 };
})(window);
