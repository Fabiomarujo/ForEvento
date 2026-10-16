/* ForEvento: fonte única de autorização para todas as páginas administrativas. */
(function(){
'use strict';
const rules={
 evento:['eventos_visualizar','eventos_editar','eventos_publicar'],
 'cronograma-lista':['cronograma_visualizar','presenca_lancar','lista_pdf'],
 'vitrine-admin':['vitrine'],financeiro:['financeiro_visualizar','financeiro_config_pix','financeiro_auditoria','financeiro_reembolso'],
 'financeiro-auditoria':['financeiro_auditoria'],reembolso:['financeiro_reembolso'],
 certificados:['cert_consultar','cert_visualizar','cert_gerar','cert_enviar','cert_excluir','cert_configurar'],
 'certificados-modelos':['cert_configurar'], 'certificados-configurar':['cert_configurar'], 'certificados-gerar':['cert_gerar','cert_enviar'],
 graficos:['relatorios_visualizar'],permissoes:['permissoes'],usuarios:['usuarios_visualizar','usuarios_editar','usuarios_bloquear'],
 configurar:['config_aparencia','config_permissoes'],perfil:['perfil']};
const entries=[['📅 EVENTO','evento','/?page=admin-dashboard&tab=evento'],['↳ Cronograma/Lista','cronograma-lista','/?page=cronograma-lista'],['🖼️ VITRINE','vitrine-admin','/?page=vitrine-admin'],['💰 FINANCEIRO','financeiro','/?page=admin-dashboard&tab=financeiro'],['↳ Consulta/Auditoria','financeiro-auditoria','/?page=financeiro-auditoria'],['↳ Reembolso','reembolso','/?page=reembolso'],['🎓 CERTIFICADOS','certificados','/?page=admin-dashboard&tab=certificados'],['↳ Cadastrar Modelos','certificados-modelos','/?page=certificados-modelos'],['↳ Configurar certificados','certificados-configurar','/?page=certificados-configurar'],['↳ Gerar e Enviar','certificados-gerar','/?page=certificados-gerar'],['📊 RELATÓRIOS','graficos','/?page=admin-dashboard&tab=graficos'],['🔑 PERMISSÕES','permissoes','/?page=admin-dashboard&tab=permissoes'],['⚙️ CONFIGURAR','configurar','/?page=configurar'],['👥 USUÁRIOS CADASTRADOS','usuarios','/?page=admin-dashboard&tab=usuarios'],['👤 MEU PERFIL','perfil','/?page=perfil']];
const allowed=(perms,key)=>!!(rules[key]||[]).some(k=>perms[k]===true);
const isMaster=x=>x.categoria==='ADMINISTRADOR_MASTER';
const localMaster=u=>String(u?.categoria||u?.tipo||u?.role||'').toUpperCase()==='ADMINISTRADOR_MASTER';
const operationalRoles=new Set(['EQUIPE_ADMINISTRATIVA','COORDENADOR','MINISTRANTE','MONITOR_EXTENSIONISTA']);
const current=()=>{const q=new URLSearchParams(location.search);return q.get('page')||({'/admin-dashboard':'admin-dashboard','/equipe-dashboard':'admin-dashboard'}[location.pathname])||''};
async function load(){const token=localStorage.getItem('fe_token')||'';const r=await fetch('/api/admin/acesso',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token}),cache:'no-store'});if(!r.ok)throw Error('Sessão expirada ou sem autorização');const data=await r.json();if(!data.sucesso)throw Error(data.mensagem||'Acesso negado');return data}
function permitted(data,key){return isMaster(data)||allowed(data.permissoes,key)}
/* fe-menu-v29: reservar o espaço lateral no primeiro DOM pronto, sem revelar links antes da autorização. */
function reserveNav(){
 if(document.getElementById('feSidebar') || document.getElementById('feSharedSidebar'))return;
 const aside=document.createElement('aside');aside.id='feSharedSidebar';aside.setAttribute('aria-label','Menu operacional');
 aside.setAttribute('aria-busy','true');aside.innerHTML='<div class="fe-menu-v29-wait" role="status">Carregando menu…</div>';
 document.body.prepend(aside);document.body.classList.add('feSharedLayout');
 const header=document.querySelector('header.top');if(header){header.classList.add('fe-unified-header','fe-structural-header')}
}
function addNav(data){
 const dashboard=!!document.getElementById('feSidebar');
 // O Master conserva integralmente o painel fixo, inclusive seu menu original.
 if(dashboard && !operationalRoles.has(data.categoria))return;
 const aside=document.getElementById('feSharedSidebar')||document.createElement('aside');aside.id='feSharedSidebar';aside.setAttribute('aria-label','Menu operacional');aside.removeAttribute('aria-busy');aside.replaceChildren();
 const currentPage=current(), tab=new URLSearchParams(location.search).get('tab')||'evento';
 const groupOf={'cronograma-lista':'evento','financeiro-auditoria':'financeiro','reembolso':'financeiro','certificados-modelos':'certificados','certificados-configurar':'certificados','certificados-gerar':'certificados'};
 const activeKey=currentPage==='admin-dashboard'?tab:currentPage;
 const visible=entries.filter(([,key])=>permitted(data,key));
 for(const [label,key,url] of visible){
   const sub=label.startsWith('↳');
   const a=document.createElement('a');a.href=url;a.textContent=label;
   a.className='feSharedLink'+(sub?' feSharedSubmenu':' feSharedGroup');
   a.dataset.feKey=key;
   if(key===activeKey)a.setAttribute('aria-current','page');
   else if(!sub && groupOf[activeKey]===key)a.classList.add('feSharedParentActive');
   aside.appendChild(a);
 }
 const toggle=document.createElement('button');toggle.type='button';toggle.id='feSharedToggle';toggle.textContent='☰';toggle.setAttribute('aria-label','Recolher ou expandir menu');toggle.setAttribute('aria-controls','feSharedSidebar');
 const collapsed=!isMaster(data)&&sessionStorage.getItem('fe-operational-collapsed')==='1';
 if(collapsed)document.body.classList.add('feSharedCollapsed');
 if(isMaster(data))document.body.classList.remove('feSharedCollapsed');
 function update(){toggle.setAttribute('aria-expanded',String(matchMedia('(max-width:800px)').matches?aside.classList.contains('feSharedOpen'):!document.body.classList.contains('feSharedCollapsed')))}
 toggle.addEventListener('click',()=>{if(isMaster(data)&&matchMedia('(min-width:801px)').matches)return;if(matchMedia('(max-width:800px)').matches){aside.classList.toggle('feSharedOpen')}else{document.body.classList.toggle('feSharedCollapsed');sessionStorage.setItem('fe-operational-collapsed',document.body.classList.contains('feSharedCollapsed')?'1':'0')}update()});
 const header=dashboard?document.querySelector('.navbar'):document.querySelector('header.top');
 if(header){header.classList.add('fe-unified-header')}
 // O botao pertence ao viewport, nao ao header deslocado pelo sidebar.
 document.body.appendChild(toggle);
 document.body.prepend(aside);
 document.body.classList.add('feSharedLayout');
 if(dashboard)document.body.classList.add('feSharedDashboard');
 document.querySelectorAll('.page-nav').forEach(n=>n.remove());
 document.addEventListener('click',e=>{if(matchMedia('(max-width:800px)').matches && aside.classList.contains('feSharedOpen') && !aside.contains(e.target) && !toggle.contains(e.target)){aside.classList.remove('feSharedOpen');update()}});
 update();
}

function guard(data){const page=current();if(page==='admin-dashboard'||page==='equipe-dashboard')return;
 if(page&&!permitted(data,page)){document.body.innerHTML='<main style="padding:35px;font-family:Arial"><h2>Acesso não autorizado</h2><p>Esta função não está liberada para sua categoria.</p><a href="/?page=admin-dashboard">Voltar ao painel</a></main>';return false}return true}
function hideUnauthorizedLinks(data){document.querySelectorAll('a[href*="page="],button[onclick*="page="]').forEach(el=>{const text=el.getAttribute('href')||el.getAttribute('onclick')||'';const m=text.match(/[?&]page=([a-z-]+)/);if(m&&!permitted(data,m[1])&&m[1]!=='admin-dashboard'){el.hidden=true;el.style.display='none'}})}
async function start(){
 const page=current();let localUser=null;try{localUser=JSON.parse(localStorage.getItem('fe_user')||'null')}catch(e){};if(!page||page==='participante-dashboard'||['login','cadastro'].includes(page)||(page==='perfil'&&String(localUser?.tipo||localUser?.role||'').toUpperCase()==='PARTICIPANTE'))return;
 /* v35: menu Master fixo no desktop, criado antes da espera pela API; backend continua validando cada rota. */
 /* v36: menu fixo do Master vem do HTML; nao recriar com addNav(). */
 /* v26: nao ocultar a pagina enquanto valida permissoes */
 try{const data=await (window.feAdminAccessPromise=load());window.feEffectiveAdminAccess=data;if(guard(data)===false)return;if(operationalRoles.has(data.categoria))document.body.classList.add('fe-operational');if(!isMaster(data)&&localMaster(localUser)){document.getElementById('feSharedSidebar')?.remove();document.body.classList.remove('feSharedLayout');}if(!isMaster(data)){addNav(data);hideUnauthorizedLinks(data)}else{document.body.classList.remove('feSharedCollapsed','fe-admin-collapsed');}}catch(e){if(document.getElementById('feSidebar'))return;document.body.innerHTML='<main style="padding:35px;font-family:Arial"><h2>Não foi possível validar suas permissões</h2><p>'+String(e.message).replace(/[&<>]/g,'')+'</p><a href="/login">Entrar novamente</a></main>'}finally{/* v27: preservar resultado durante esta página */}
}
document.addEventListener('DOMContentLoaded',function(){const page=current();let u=null;try{u=JSON.parse(localStorage.getItem('fe_user')||'null')}catch(e){};if(page && page!=='participante-dashboard' && !['login','cadastro'].includes(page) && operationalRoles.has(String(u?.categoria||u?.tipo||u?.role||'').toUpperCase()))reserveNav();start()});
window.feAdminMenuRules=rules;
})();
