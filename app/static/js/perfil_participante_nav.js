/* Navegação compartilhada do participante: mantém funções e formulários existentes. */
document.addEventListener('DOMContentLoaded',()=>{
 const current=typeof user==='function'?user():null;
 if(!current||String(current.tipo||'').toUpperCase()!=='PARTICIPANTE')return;
 document.body.classList.add('participant-profile-page','portal-restored','fe-profile-drawer');
 const top=document.querySelector('#hdr');
 if(!top)return;
 const toggle=document.createElement('button');toggle.id='menuBtn';toggle.type='button';toggle.textContent='☰';toggle.setAttribute('aria-label','Abrir menu');toggle.setAttribute('aria-expanded','false');const left=document.createElement('div');left.className='profile-left';const greeting=top.querySelector('.user-name');if(greeting)left.append(greeting);left.prepend(toggle);top.prepend(left);
 const backdrop=document.createElement('div');backdrop.className='portal-backdrop';backdrop.hidden=true;
 const drawer=document.createElement('aside');drawer.className='portal-drawer';drawer.setAttribute('aria-label','Menu do participante');
 drawer.innerHTML='<h3>Minha conta</h3><nav><a href="/?page=participante-dashboard#eventos">📅 Eventos disponíveis</a><a href="/?page=participante-dashboard#inscricoes">📋 Minhas inscrições</a><a href="/?page=participante-dashboard#ingressos">🎟️ Meus ingressos</a><a href="/?page=participante-dashboard#certificados">🎓 Meus certificados</a><a href="/?page=perfil" aria-current="page">👤 Meu perfil</a><a href="/manual-usuario?origem=participante">❔ Ajuda</a></nav>';
 document.body.append(backdrop,drawer);
 const close=()=>{drawer.classList.remove('open');backdrop.hidden=true;toggle.setAttribute('aria-expanded','false')};
 toggle.addEventListener('click',()=>{const open=!drawer.classList.contains('open');drawer.classList.toggle('open',open);backdrop.hidden=!open;toggle.setAttribute('aria-expanded',String(open))});
 backdrop.addEventListener('click',close);document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
});
