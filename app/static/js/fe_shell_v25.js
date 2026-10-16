(function(){'use strict';function init(){const h=document.getElementById('feUnifiedHeader');if(!h)return;const b=document.getElementById('feHeaderMenuButton'),g=document.getElementById('feHeaderGreeting'),out=document.getElementById('feHeaderExit');try{const u=JSON.parse(localStorage.getItem('fe_user')||'null');if(u&&(u.nome||u.name))g.textContent='Olá, '+String(u.nome||u.name).trim().split(/\s+/)[0]}catch(e){}
const slot=document.getElementById('feShellSidebarSlot');const move=()=>{const side=document.getElementById('feSharedSidebar');if(side&&slot&&side.parentElement!==slot)slot.appendChild(side)};move();if(!document.getElementById('feSharedSidebar')){const obs=new MutationObserver(()=>{if(document.getElementById('feSharedSidebar')){move();obs.disconnect()}});obs.observe(document.body,{childList:true});}
function syncTheme(){const side=document.getElementById('feSidebar')||document.getElementById('feSharedSidebar');if(!side)return;const s=getComputedStyle(side),bg=s.backgroundColor,fg=s.color;const root=document.documentElement;if(bg&&bg!=='rgba(0, 0, 0, 0)')root.style.setProperty('--fe-cor-menu-lateral',bg);if(fg)root.style.setProperty('--fe-cor-texto-menu-lateral',fg)}
// Use existing toggles to preserve their state and permission checks.
b.addEventListener('click',()=>{if(document.documentElement.classList.contains('feMasterDesktop')&&matchMedia('(min-width:801px)').matches)return;const admin=document.getElementById('feSidebar');if(admin&&typeof window.feToggleSidebar==='function'){window.feToggleSidebar();return}const old=document.getElementById('feSharedToggle');if(old){old.click();return}const side=document.getElementById('feSharedSidebar');if(side)side.classList.toggle('feSharedOpen')});
out.addEventListener('click',()=>{if(typeof window.feLogout==='function')window.feLogout();else if(typeof window.logout==='function')window.logout();else location.href='/login'});
// Shared administrative tools: same actions as dashboard, no duplicated controls.
function addTools(){const side=document.getElementById('feSharedSidebar');if(!side||side.querySelector('.feSharedTools'))return;
// Backup manual disponível exclusivamente em Configurar → Backup e Restauração.
const area=document.createElement('div');area.className='feSharedTools feV24Tools';
const help=document.createElement('a');help.className='feSharedTool feV24Help';help.href='/manual-usuario';help.target='_blank';help.rel='noopener';help.textContent='💡 Manual de Ajuda';area.appendChild(help);side.appendChild(area)}
let tries=0;const timer=setInterval(()=>{addTools();if(document.querySelector('#feSharedSidebar .feSharedTools')||++tries>100)clearInterval(timer)},100);
// Configuração visual gravada no CSS do servidor, não em localStorage.
if(location.search.includes('page=configurar')){
 let n=0;const t=setInterval(async()=>{
 const anchor=document.getElementById('feMenuAppearance')||document.querySelector('section.card');
 if(!anchor){if(++n>80)clearInterval(t);return}
 if(document.getElementById('feV25Appearance')){clearInterval(t);return}
 clearInterval(t);
 const labels={active:'Botão selecionado',activeText:'Texto do botão selecionado',divider:'Divisórias do menu',footer:'Fundo do rodapé',footerText:'Texto do rodapé'};
 const defaults={active:'#2563eb',activeText:'#ffffff',divider:'#ffffff',footer:'#0f172a',footerText:'#ffffff'};
 const panel=document.createElement('section');panel.className='card mt';panel.id='feV25Appearance';
 panel.innerHTML='<h2>Cores dos menus e rodapé</h2><p>As alterações são salvas no CSS do servidor e valem para todos os dispositivos.</p><div class="feV24Settings"></div><button class="btn blue" type="button" id="feV25Save">Salvar cores complementares</button><p id="feV25Message" role="status"></p>';
 anchor.insertAdjacentElement('afterend',panel);
 const fields=panel.querySelector('.feV24Settings');
 function fill(d){fields.replaceChildren();for(const [k,label] of Object.entries(labels)){const l=document.createElement('label');l.textContent=label+' ';const i=document.createElement('input');i.type='color';i.name=k;i.value=d[k]||defaults[k];l.appendChild(i);fields.appendChild(l)}}
 try{const r=await fetch('/api/appearance/settings',{cache:'no-store'});if(!r.ok)throw Error('Falha ao carregar configurações');fill(await r.json())}catch(e){fill(defaults);panel.querySelector('#feV25Message').textContent=e.message}
 panel.querySelector('#feV25Save').onclick=async()=>{const btn=panel.querySelector('#feV25Save'),status=panel.querySelector('#feV25Message');btn.disabled=true;
 try{const colors=Object.fromEntries([...fields.querySelectorAll('input')].map(x=>[x.name,x.value]));const r=await fetch('/api/appearance/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:localStorage.getItem('fe_token')||'',colors})});const d=await r.json();if(!r.ok)throw Error(d.erro||'Falha ao salvar');status.textContent='Cores salvas no servidor. Atualizando aparência...';location.reload()}catch(e){status.textContent=e.message;btn.disabled=false}};
 },100)
}

}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init()})();