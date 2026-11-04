(function(global){
 'use strict';
 global.createPlanningAssistant=function(options){
  const $=id=>document.getElementById(id);
  let mode='suggest',suggestions={phase:'input',total:0,selected:0},storageFailed=false;
  try{$('input').value=localStorage.getItem(options.storageKey)||$('input').value;}catch(error){storageFailed=true;}
  function persistInput(){
   try{if($('input').value)localStorage.setItem(options.storageKey,$('input').value);else localStorage.removeItem(options.storageKey);storageFailed=false;}
   catch(error){storageFailed=true;}
   $('assistant-draft-state').textContent=storageFailed?'输入暂时无法保存在浏览器，请复制保留。':$('input').value?'输入草稿已保留在当前浏览器':'输入仅用于讨论或建议；功能表需另行保存。';
  }
  function shouldGenerate(){return options.getState().ready&&mode==='suggest';}
  function validate(){
   const value=$('input').value.trim();
   const error=shouldGenerate()&&value.length>3000?'建议重点最多3000字，请精简后重试，输入内容已保留。':!shouldGenerate()&&!value?'请先输入想讨论的内容。':'';
   $('assistant-input-error').textContent=error;$('assistant-input-error').hidden=!error;
   $('input').setAttribute('aria-invalid',String(!!error));
   if(error)$('input').focus();return !error;
  }
  function sync(){
   const state=options.getState(),suggest=shouldGenerate();
   $('assistant-modes').hidden=!state.ready;
   $('assistant-mode-suggest').checked=mode==='suggest';$('assistant-mode-chat').checked=mode==='chat';
   for(const id of ['assistant-mode-suggest','assistant-mode-chat'])$(id).disabled=state.busy;
   $('input-label').textContent=!state.ready?'你想做什么项目？':suggest?'想补充什么，或希望重点检查什么？（选填）':'想和规划助手讨论什么？';
   $('assistant-input-hint').textContent=!state.ready?'描述使用者、目标和主要功能，我们会先查找 GitHub 参考。':suggest?'直接写想法或检查重点，最多3000字；留空则检查当前功能表。不会直接修改已保存内容。':'先澄清范围与疑问；讨论后切换“生成修改建议”，再选择要加入功能表的内容。';
   $('input').required=!suggest;
   $('assistant-submit').textContent=state.busy?'正在处理…':!state.ready?'查找参考并开始规划':suggest?'生成修改建议':'发送讨论';
   $('assistant-submit').className='send';$('assistant-submit').disabled=state.busy||state.dirty;
   $('assistant-blocker').hidden=!state.ready||!state.dirty;
   $('assistant-blocker-text').textContent=state.editing?'功能表正在编辑。先保存或取消编辑，再继续。':'功能表有未保存的修改。先保存或放弃预览，再继续。';
   $('status').hidden=state.ready&&mode==='suggest';$('suggestions-status').hidden=!state.ready||mode==='chat';
   const phase=suggestions.phase==='preview'||suggestions.phase==='saved'?'review':suggestions.phase==='choose'?'choose':'input';
   for(const step of ['input','choose','review']){const el=$('assistant-step-'+step);el.setAttribute('data-current',String(step===phase));if(step===phase)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');}
   $('suggestion-preview-bar').hidden=suggestions.phase!=='preview';
   $('suggestion-preview-label').textContent='建议预览 · '+(suggestions.changed||0)+' 个功能有修改，尚未保存';
   $('discard-suggestion-preview').disabled=state.busy||state.editing;
   $('suggestion-preview-hint').textContent=state.editing?'正在编辑预览，先保存或取消编辑。':'确认下方高亮修改后，点击表格上方“保存功能表”；也可继续编辑。';
  }
  for(const [id,value] of [['assistant-mode-suggest','suggest'],['assistant-mode-chat','chat']])$(id).addEventListener('change',()=>{mode=value;$('assistant-input-error').hidden=true;$('input').setAttribute('aria-invalid','false');sync();});
  $('input').addEventListener('input',()=>{persistInput();$('assistant-input-error').hidden=true;$('input').setAttribute('aria-invalid','false');});
  persistInput();sync();
  return {sync,shouldGenerate,validate,persistInput,onSuggestions(value){suggestions=value;sync();},showDiscussion(){mode='chat';sync();}};
 };
})(window);
