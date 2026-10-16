/* Apenas contexto de apresentação; não altera nem encerra a sessão. */
document.addEventListener('DOMContentLoaded',()=>{
 const params=new URLSearchParams(location.search);
 if(params.get('origem')!=='participante')return;
 let u=null;try{u=JSON.parse(localStorage.getItem('fe_user')||'null')}catch(_){}
 // O link vem da área autenticada. Não limpar tokens nem chamar logout.
 const header=document.querySelector('.fe-vitrine-header');if(!header)return;
 document.body.classList.add('fe-manual-participant');
 header.innerHTML='<button id="manualParticipantMenu" type="button" aria-label="Abrir menu" aria-expanded="false">☰</button><span class="manual-participant-greeting">Área do Participante</span><strong class="manual-participant-brand">ForEvento</strong><button class="manual-participant-return" id="manualParticipantLogout" type="button">Sair</button>';
 const logoutButton=document.getElementById('manualParticipantLogout');logoutButton.onclick=async()=>{if(typeof logout==='function'){await logout();return;}try{await fetch('/api/call/encerrarSessao',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({args:[localStorage.getItem('fe_token')||'']})})}finally{['fe_user','fe_token','fe_touch','fe_session_policy'].forEach(k=>localStorage.removeItem(k));location.href='/login'}};
 const aside=document.createElement('aside');aside.className='manual-participant-drawer';aside.innerHTML='<strong>Minha conta</strong><nav><a href="/?page=participante-dashboard#eventos">📅 Eventos disponíveis</a><a href="/?page=participante-dashboard#inscricoes">📋 Minhas inscrições</a><a href="/?page=participante-dashboard#ingressos">🎟️ Meus ingressos</a><a href="/?page=participante-dashboard#certificados">🎓 Meus certificados</a><a href="/?page=perfil">👤 Meu perfil</a><a href="/manual-usuario?origem=participante" aria-current="page">❔ Ajuda</a></nav>';
 const shade=document.createElement('div');shade.className='manual-participant-shade';shade.hidden=true;document.body.append(shade,aside);
 const button=document.getElementById('manualParticipantMenu');const close=()=>{aside.classList.remove('open');shade.hidden=true;button.setAttribute('aria-expanded','false')};button.onclick=()=>{const open=!aside.classList.contains('open');aside.classList.toggle('open',open);shade.hidden=!open;button.setAttribute('aria-expanded',String(open))};shade.onclick=close;document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
 const back=document.querySelector('.fe-back-manual');if(back){back.href='/?page=participante-dashboard#eventos';back.textContent='← Voltar aos eventos'}
});
