document.addEventListener('DOMContentLoaded',async()=>{
 const u=user();if(!u){location.replace('/login');return;}
 if(String(u.tipo||'').toUpperCase()!=='PARTICIPANTE'){location.replace('/?page=admin-dashboard');return;}
 document.getElementById('participantGreeting').textContent='Olá, '+(u.nome||'Participante').trim().split(/\s+/)[0];
 document.getElementById('participantWelcome').textContent='Olá, '+(u.nome||'Participante').trim().split(/\s+/)[0]+'!';
 document.getElementById('participantId').textContent='Seu identificador ForEvento: '+(u.id||'');
 document.getElementById('participantLogout').addEventListener('click',()=>logout());
 const sidebar=document.getElementById('participantSidebar'),backdrop=document.getElementById('participantBackdrop'),btn=document.getElementById('participantMenuButton');
 function closeMenu(){sidebar.classList.remove('open');backdrop.hidden=true;btn.setAttribute('aria-expanded','false')}
 btn.addEventListener('click',()=>{const opening=!sidebar.classList.contains('open');sidebar.classList.toggle('open',opening);backdrop.hidden=!opening;btn.setAttribute('aria-expanded',String(opening))});
 backdrop.addEventListener('click',closeMenu);sidebar.querySelectorAll('a').forEach(a=>a.addEventListener('click',closeMenu));
 function entry(target,title,subtitle){const node=document.createElement('div');node.className='participant-entry';const strong=document.createElement('strong');strong.textContent=title;node.append(strong);if(subtitle){const small=document.createElement('small');small.textContent=subtitle;node.append(small)}target.append(node)}
 function empty(target,message){const p=document.createElement('p');p.className='participant-empty';p.textContent=message;target.append(p)}
 // Each detail module opens only when selected, avoiding repeated information on home.
 const sections=['eventos','inscricoes','ingressos','certificados'];
 const home=document.getElementById('participantHomeCards'),back=document.getElementById('participantBack');
 function showSection(name){sections.forEach(id=>document.getElementById(id).hidden=id!==name);home.hidden=!!name;back.hidden=!name;document.querySelector('.participant-welcome').hidden=!!name;document.getElementById('participantTitle').textContent=name?({eventos:'Eventos disponíveis',inscricoes:'Minhas inscrições',ingressos:'Meus ingressos',certificados:'Meus certificados'}[name]):'Minha área';window.scrollTo({top:0,behavior:'instant'});}
 document.querySelectorAll('[data-section]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();showSection(a.dataset.section);history.replaceState(null,'',a.getAttribute('href'));}));
 back.addEventListener('click',()=>{showSection(null);history.replaceState(null,'','/?page=participante-dashboard')});
 if(sections.includes(location.hash.slice(1)))showSection(location.hash.slice(1));

 // Eventos are displayed inside the authenticated participant shell, never by navigating to the public Vitrine.
 const eventBox=document.getElementById('participantEvents');
 const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
 try{
  const evs=await call('obterVitrineEventos');eventBox.replaceChildren();
  if(!Array.isArray(evs)||!evs.length)empty(eventBox,'Nenhum evento publicado no momento.');
  else evs.forEach(ev=>{
   const article=document.createElement('article');article.className='participant-entry participant-event';
   const title=document.createElement('h3');title.textContent=ev.nome||'Evento';article.append(title);
   if(ev.sinopseCurta||ev.resumo){const p=document.createElement('p');p.textContent=ev.sinopseCurta||ev.resumo;article.append(p)}
   const button=document.createElement('button');button.type='button';button.className='participant-back';button.textContent='Ver atividades';article.append(button);
   const details=document.createElement('div');details.hidden=true;article.append(details);
   button.addEventListener('click',async()=>{
    if(!details.hidden){details.hidden=true;button.textContent='Ver atividades';return}
    if(details.dataset.loaded){details.hidden=false;button.textContent='Ocultar atividades';return}
    button.disabled=true;
    try{const activities=await call('obterCronogramaPublico',ev.id);details.replaceChildren();
     if(!Array.isArray(activities)||!activities.length)empty(details,'Cronograma ainda não publicado.');
     else activities.forEach(a=>{const div=document.createElement('div');div.className='participant-entry';const strong=document.createElement('strong');strong.textContent=a.sinopse||a.ministrante||'Atividade';div.append(strong);const small=document.createElement('small');small.textContent=[a.data,a.hora,a.tipo,a.local].filter(Boolean).join(' · ');div.append(small);details.append(div)});
     details.dataset.loaded='1';details.hidden=false;button.textContent='Ocultar atividades';
    }catch(err){details.replaceChildren();empty(details,'Não foi possível carregar as atividades.');details.hidden=false}finally{button.disabled=false}
   });eventBox.append(article)
  })
 }catch(err){eventBox.replaceChildren();empty(eventBox,'Não foi possível consultar os eventos agora.')}

 // Colors are loaded from the local ForEvento database; no online service.
 try{const theme=await fetch('/api/participante/tema').then(r=>r.json());for(const [key,val] of Object.entries(theme||{})){if(/^#[0-9a-f]{6}$/i.test(val))document.documentElement.style.setProperty('--p-'+key,val)}}catch(e){console.warn('Tema padrão mantido',e)}
 const r=document.getElementById('participantRegistrations'),t=document.getElementById('participantTickets'),c=document.getElementById('participantCertificates');
 try{const resp=await fetch('/api/participante/resumo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:localStorage.getItem('fe_token')||''})});if(resp.status===401||resp.status===403){await logout();return}if(!resp.ok)throw Error('Não foi possível carregar os dados');const data=await resp.json();r.replaceChildren();t.replaceChildren();c.replaceChildren();
 const regs=data.inscricoes||[];if(!regs.length)empty(r,'Você ainda não possui inscrições.');else regs.forEach(x=>entry(r,x.activity||'Atividade',`Evento: ${x.event_id||'—'} · Situação: ${x.status||'—'}`));
 document.getElementById('participantRegistrationCount').textContent=regs.length+' inscrição(ões)';
 const confirmed=regs.filter(x=>String(x.status||'').toUpperCase()==='CONFIRMADO');if(!confirmed.length)empty(t,'Nenhum ingresso confirmado encontrado.');else confirmed.forEach(x=>entry(t,x.activity||'Atividade',`Inscrição: ${x.id||'—'} · Confirmada`));
 document.getElementById('participantTicketCount').textContent=confirmed.length+' ingresso(s) confirmado(s)';
 const certs=data.certificados||[];document.getElementById('participantCertificateCount').textContent=certs.length+' certificado(s)';if(!certs.length)empty(c,'Nenhum certificado disponível no momento.');else certs.forEach(x=>entry(c,x.activity||'Atividade',`Situação: ${x.status||'—'} · Idioma: ${x.language||'—'}`));
 }catch(e){[r,t,c].forEach(box=>{box.replaceChildren();empty(box,'Não foi possível consultar seus dados agora. Tente atualizar a página.')});console.error(e)}
});
