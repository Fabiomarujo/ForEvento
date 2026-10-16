/* v17: honor existing theme values; never mutate permissions, routes or menu DOM. */
(function(){'use strict';
function sync(){
 const b=document.body;if(!b||!b.classList.contains('fe-operational'))return;
 const root=document.documentElement;
 const theme=window.feCurrentTheme||window.feTemaAtual||null;
 if(theme&&typeof theme==='object'){
  const valid=v=>typeof v==='string'&&/^#[0-9a-f]{6}$/i.test(v);
  for(const [key,variable] of [['cabecalho','--fe17-header-color'],['textoCabecalho','--fe17-header-text'],['menuLateral','--fe17-sidebar-color'],['textoMenuLateral','--fe17-sidebar-text']])if(valid(theme[key]))root.style.setProperty(variable,theme[key]);
 }
 const toggle=document.getElementById('feSharedToggle');
 if(toggle){toggle.setAttribute('aria-label','Abrir ou recolher menu');toggle.setAttribute('aria-controls','feSharedSidebar')}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',sync);else sync();
window.addEventListener('pageshow',sync);
})();
