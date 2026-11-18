(function(global){
 'use strict';
 // Project-level bar shared by the planning page and the board: same place, same order on both.
 const project=new URLSearchParams(location.search).get('project');
 const scoped=(path,hash)=>path+(project?'?project='+encodeURIComponent(project):'')+(hash||'');
 for(const link of document.querySelectorAll('[data-project-href]'))link.href=scoped(link.getAttribute('data-project-href'),link.getAttribute('data-project-hash'));
 const bar=document.getElementById('project-nav');
 // Sticky page toolbars sit below this bar, so publish its height.
 const measure=()=>document.documentElement.style.setProperty('--project-nav-height',bar.getBoundingClientRect().height+'px');
 if(bar){measure();if(typeof ResizeObserver==='function')new ResizeObserver(measure).observe(bar);}
 global.ProjectNav={
  setName(name){const node=document.getElementById('nav-project-name');if(node&&name)node.textContent=name;}
 };
})(window);
