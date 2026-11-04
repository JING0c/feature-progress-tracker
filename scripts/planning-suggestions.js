(function(global){
 'use strict';
 global.createPlanningSuggestions=function(options){
  const $=id=>document.getElementById(id),selected=new Set();let record=null,busy=false,fields=[],generation=0;
  const text=(tag,value)=>{const el=document.createElement(tag);el.textContent=value;return el;};
  function sync(){
   const state=options.getPlan(),stale=record?.plan_revision!==state.revision;
   $('generate-suggestions').disabled=busy||!state.ready;
   $('preview-suggestions').disabled=busy||!selected.size||stale||state.dirty;
   fields.forEach(f=>f.disabled=busy||stale||state.dirty);
   const expired='功能表已更新，这批建议已过期，请重新分析。';
   if(record?.id&&stale)$('suggestions-status').textContent=expired;
   else if($('suggestions-status').textContent===expired)$('suggestions-status').textContent='子智能体给出 '+(record?.suggestions.length||0)+' 条建议，默认不采纳。';
  }
  function render(data){
   record=data;selected.clear();fields=[];$('suggestions-list').replaceChildren();$('suggestion-diff').hidden=true;
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
   generation++;options.setBusy(true);$('suggestions-progress').hidden=false;const start=Date.now();
   $('suggestions-status').textContent='独立 Codex 子智能体正在分析当前功能…';
   const timer=setInterval(()=>{$('suggestions-status').textContent='独立 Codex 子智能体正在分析 · 已等待 '+Math.floor((Date.now()-start)/1000)+' 秒';},1000);
   try{const data=await options.request('/api/plan/suggestions',{revision:state.revision,focus:$('suggestions-focus').value.trim()});render(data);}
   catch(error){$('suggestions-status').textContent='建议未生成：'+error.message;}
   finally{clearInterval(timer);$('suggestions-progress').hidden=true;options.setBusy(false);}
  });
  $('preview-suggestions').addEventListener('click',async()=>{
   if(busy||!record)return;const state=options.getPlan();if(state.dirty){$('suggestions-status').textContent='请先保存当前功能表修改。';return;}
   options.setBusy(true);
   try{
    const data=await options.request('/api/plan/suggestions/preview',{revision:state.revision,suggestion_id:record.id,selected:[...selected]});
    $('suggestion-diff').hidden=false;$('suggestion-diff-text').textContent=data.diff;
    options.onPreview(data);$('suggestions-status').textContent='所选建议已放入功能表预览，尚未保存；可继续编辑，再点击表格上方“保存功能表”。';
   }catch(error){$('suggestions-status').textContent=error.message;}
   finally{options.setBusy(false);}
  });
  options.request('/api/plan/suggestions').then(data=>{if(!generation)render(data);}).catch(error=>{$('suggestions-status').textContent=error.message;});
  return {setBusy(value){busy=value;sync();}};
 };
})(window);
