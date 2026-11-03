(function(global){
 'use strict';
 global.createPlanningWorkflow=function(options){
  const {request,notice,getPlan,onSave,guide,storageKey}=options;
  const $=id=>document.getElementById(id);
  let research={completed:false,repositories:[]},editing=false,base=null,rows=[],columns=[],fields=[],busy=false;
  function text(tag,value){const node=document.createElement(tag);node.textContent=value;return node;}
  function renderResearch(data){
   research=data;const box=$('research-results');box.replaceChildren();
   if(!data.completed)return;
   $('research-query').value=data.query||'';
   $('research-state').textContent=(data.repositories.length?'找到 '+data.repositories.length+' 个参考项目':'未找到相似项目，可调整关键词重新搜索')+' · '+(data.searched_at?new Date(data.searched_at).toLocaleString('zh-CN'):'');
   for(const repo of data.repositories){
    const card=document.createElement('article');card.className='reference-card';
    const link=text('a',repo.name);link.href=repo.url;link.target='_blank';link.rel='noopener noreferrer';
    card.append(link,text('p',repo.description||'暂无仓库说明'),text('small',(repo.language||'未标注语言')+' · 许可证 '+(repo.license||'未标注')+' · ★ '+repo.stars),text('small',(repo.updated_at?'仓库更新 '+new Date(repo.updated_at).toLocaleDateString('zh-CN')+' · ':'')+(repo.readme_note||'')));box.append(card);
   }
  }
  const loaded=request('/api/research').then(renderResearch).catch(error=>{$('research-state').textContent=error.message;});
  async function search(need){
   $('research-state').textContent='正在提取关键词并检索 GitHub…';
   const query=$('research-query').value.trim();
   try{const data=await request('/api/research',query?{query}:{need});renderResearch(data);return data;}
   catch(error){$('research-state').textContent=error.message;throw error;}
  }
  $('search-references').addEventListener('click',async()=>{
   if(busy)return;options.setBusy(true);
   try{await search($('input').value.trim()||getPlan().content.slice(0,6000));notice('GitHub参考已更新，后续规划会引用这些资料。');}
   catch(error){notice(error.message,true);}finally{options.setBusy(false);}
  });
  function retain(){try{localStorage.setItem(storageKey,JSON.stringify({base,rows,columns}));}catch(error){notice('编辑草稿无法暂存，请及时保存。',true);}}
  function setSelection(id,selected){
   const byId=new Map(rows.map(r=>[r['编号'],r])),seen=new Set(),pending=[id];
   while(pending.length){const key=pending.pop();if(seen.has(key)||!byId.has(key))continue;seen.add(key);byId.get(key)['采用']=selected?'是':'否';rows.filter(r=>r['上级编号']===key).forEach(r=>pending.push(r['编号']));}
   if(selected){let parent=byId.get(id)?.['上级编号'];while(byId.has(parent)&&!seen.has(parent)){seen.add(parent);byId.get(parent)['采用']='是';parent=byId.get(parent)['上级编号'];}}
   for(let i=0;i<rows.length;i++)for(const row of rows){const children=rows.filter(r=>r['上级编号']===row['编号']);if(children.length&&children.every(r=>r['采用']==='否'))row['采用']='否';}
  }
  function renderEditor(){
   const table=$('feature-editor-table');table.replaceChildren();fields=[];
   const head=document.createElement('tr');columns.forEach(c=>head.append(text('th',c)));table.append(head);
   rows.forEach(row=>{const tr=document.createElement('tr');columns.forEach(column=>{
    const td=document.createElement('td');let field;
    if(column==='采用'){
     field=document.createElement('input');field.type='checkbox';field.checked=row[column]!=='否';
     field.setAttribute('aria-label','采用 '+(row['编号']||'新增功能'));
     field.addEventListener('change',()=>{setSelection(row['编号'],field.checked);renderEditor();retain();});
    }else{
     field=document.createElement('textarea');field.rows=3;field.value=row[column]||'';
     field.setAttribute('aria-label',(row['编号']||'新增功能')+' '+column);
     field.addEventListener('input',()=>{row[column]=field.value;retain();});
    }
    fields.push(field);td.append(field);tr.append(td);
   });table.append(tr);});
  }
  $('edit-features').addEventListener('click',async()=>{
   if(busy)return;const plan=getPlan();
   if(!plan.ready){notice('请先生成并保存规划书，再修改功能表。',true);return;}
   options.setBusy(true);
   try{
    const data=await request('/api/plan/features',{content:plan.content});base={content:plan.content,revision:plan.revision};rows=data.rows;columns=data.columns;
    try{const draft=JSON.parse(localStorage.getItem(storageKey)||'null');if(draft&&draft.rows&&draft.base){base=draft.base;rows=draft.rows;columns=draft.columns;notice('已恢复功能表编辑草稿；保存时仍会校验原文件版本。');}}catch(error){}
    editing=true;$('feature-editor').hidden=false;renderEditor();$('feature-editor').scrollIntoView({block:'start'});
   }catch(error){notice(error.message,true);}finally{options.setBusy(false);}
  });
  $('add-feature-row').addEventListener('click',()=>{
   const used=new Set(rows.map(row=>row['编号']));let n=1;while(used.has('F'+String(n).padStart(2,'0')))n++;
   rows.push({'采用':'是','编号':'F'+String(n).padStart(2,'0'),'上级编号':'无'});renderEditor();retain();
  });
  $('cancel-feature-edit').addEventListener('click',()=>{
   if(!confirm('放弃尚未保存的功能表修改？'))return;editing=false;$('feature-editor').hidden=true;localStorage.removeItem(storageKey);options.setBusy(false);
  });
  $('save-feature-edit').addEventListener('click',async()=>{
   if(busy)return;const plan=getPlan();
   if(plan.revision!==base.revision||plan.content!==base.content){notice('规划已经变化，编辑草稿已保留。请复制修改内容，核对最新规划后重新编辑。',true);return;}
   options.setBusy(true);
   try{
    const data=await request('/api/plan/features',{content:base.content,rows});
    try{await onSave(data.content);}catch(error){base.content=data.content;retain();throw error;}
    editing=false;$('feature-editor').hidden=true;localStorage.removeItem(storageKey);notice('功能表已保存，后续对话与 Excel 将使用你的修改。');
   }catch(error){notice(error.message,true);}finally{options.setBusy(false);}
  });
  $('guide-feature').addEventListener('click',()=>{
   if(busy)return;const value=$('new-feature-idea').value.trim();if(!value){notice('请先描述想增加的功能。',true);return;}
   if(editing){notice('请先保存或取消功能表编辑，再进行拆分。',true);return;}
   guide('我希望新增功能：'+value+'。请先引导我明确使用者、边界及验收，用最多两个关键问题逐轮澄清，再建议大功能/小功能/细分功能、所需技术和前期准备。现在先讨论拆分，暂不改动现有功能表。');
  });
  return{
   get editing(){return editing;},
   async ensureResearch(need){await loaded;if(!research.completed)await search(need);},
   setBusy(value){busy=value;for(const id of ['search-references','edit-features','add-feature-row','cancel-feature-edit','save-feature-edit','guide-feature'])$(id).disabled=value;fields.forEach(f=>f.disabled=value);},
   async choose(id,selected){
    if(editing)throw Error('请先完成正在编辑的功能表。');
    return request('/api/plan/features',{content:getPlan().content,selection:{id,selected}});
   }
  };
 };
})(window);
