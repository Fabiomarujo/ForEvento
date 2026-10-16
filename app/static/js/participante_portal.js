/* Conversão do fluxo do participante do Apps Script: apresentação sem rotas administrativas. */
(()=>{'use strict';
const token=()=>localStorage.getItem('fe_token')||'';
const current=user();if(!current||String(current.tipo||'').toUpperCase()!=='PARTICIPANTE'){location.replace('/login');return;}
const $=id=>document.getElementById(id),state={events:[],regs:[],certs:[],activities:{},payment:null,passaportes:[],participantName:""};
$('greeting').textContent='Olá, '+(current.nome||'Participante').trim().split(/\s+/)[0];
const api=async(path,extra={})=>{const r=await fetch('/api/participante/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token(),...extra})});const j=await r.json();if(r.status===401){location.replace('/login');throw Error('Sessão encerrada.')}if(!r.ok)throw Error(j.erro||'Falha ao consultar servidor');return j};
const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n};
function notify(message,bad=false){const n=$('notice');n.hidden=false;n.textContent=message;n.className='portal-notice '+(bad?'error':'');n.scrollIntoView({block:'nearest'});}
function closeDrawer(){$('drawer').classList.remove('open');$('backdrop').hidden=true;$('menuBtn').setAttribute('aria-expanded','false')}
$('menuBtn').onclick=()=>{const open=!$('drawer').classList.contains('open');$('drawer').classList.toggle('open',open);$('backdrop').hidden=!open;$('menuBtn').setAttribute('aria-expanded',String(open))};$('backdrop').onclick=closeDrawer;
$('exitBtn').onclick=()=>logout();
function show(name){for(const id of ['eventos','inscricoes','ingressos','certificados'])$(id).hidden=id!==name;document.body.classList.toggle('portal-ingressos-view',name==='ingressos');document.body.classList.toggle('portal-certificados-view',name==='certificados');$('pageTitle').textContent=({eventos:'Eventos disponíveis',inscricoes:'Minhas inscrições',ingressos:'Meus ingressos',certificados:'Meus certificados'})[name];$('pageSubtitle').textContent=name==='eventos'?'Escolha um evento e abra suas atividades para se inscrever.':'Acompanhe seus registros no ForEvento.';history.replaceState(null,'','#'+name);closeDrawer();scrollTo(0,0)}
document.querySelectorAll('[data-target]').forEach(b=>b.onclick=()=>show(b.dataset.target));
const fmtMoney=n=>Number(n||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const isPaid=a=>String(a.modeloPreco||'').toUpperCase()==='PAGA'&&Number(a.precoValor)>0;
const dateFormat=s=>{const t=String(s||'');return /^\d{4}-\d{2}-\d{2}$/.test(t)?t.slice(8)+'/'+t.slice(5,7)+'/'+t.slice(0,4):t};
function action(label,handler,cls='portal-primary'){const b=el('button',cls,label);b.type='button';b.onclick=handler;return b}
function modal(id,open){$(id).hidden=!open}document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>modal(b.dataset.close,false));
function showDetails(ev,a){$('detailsTitle').textContent=a.nome;const body=$('detailsBody');body.replaceChildren();[['Evento',ev.nome],['Convidado(a)',a.ministrante],['Tipo',a.tipo],['Data',dateFormat(a.data)],['Horário',a.hora+(a.horaTermino?' às '+a.horaTermino:'')],['Local',a.local],['Modalidade',a.modalidade],['Ementa',a.ementa],['Currículo',a.curriculo],['Sinopse',a.sinopse]].forEach(([k,v])=>{if(v){const p=el('p');const strong=el('strong','',k+': ');p.append(strong,document.createTextNode(v));body.append(p)}});modal('detailsModal',true)}
function payment(p){state.payment=p;const wrap=$('paymentInfo');wrap.replaceChildren();const info=el('p','',fmtMoney(p.valor));const pix=el('p','', 'Chave PIX: '+(p.chavePix||'Não configurada pela organização'));const beneficiary=el('p','', 'Beneficiário: '+(p.beneficiario||'Não informado'));wrap.append(info,pix,beneficiary);$('receiptFile').value='';$('paymentFeedback').textContent='';modal('paymentModal',true)}
async function openPayment(reg,ev,a){try{const cfg=await call('obterConfiguracaoPixPorEvento',ev.id);payment({inscricao:reg.id,valor:a.precoValor,chavePix:cfg.chavePix,beneficiario:cfg.beneficiario})}catch(e){notify(e.message,true)}}
$('sendReceipt').onclick=async()=>{const f=$('receiptFile').files[0];if(!f){$('paymentFeedback').textContent='Selecione um comprovante.';return}if(f.size>5*1024*1024){$('paymentFeedback').textContent='O arquivo deve ter até 5 MB.';return}const b=$('sendReceipt');b.disabled=true;try{const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(f)});const result=await api('comprovante',{inscricao:state.payment.inscricao,nomeArquivo:f.name,base64:encoded});modal('paymentModal',false);notify(result.mensagem);await refresh();}catch(e){$('paymentFeedback').textContent=e.message}finally{b.disabled=false}};
async function enroll(ev,a,op){const message=op==='cancelar'?'Cancelar sua inscrição nesta atividade?':'Confirmar inscrição nesta atividade?';if(!confirm(message))return;try{const result=await api('inscricao',{evento:ev.id,atividade_id:a.id,acao:op});notify(result.mensagem||(op==='cancelar'?'Inscrição cancelada.':'Inscrição realizada.'));if(result.paga)payment({...result.pagamento,inscricao:result.idInscricao});await refresh();if(state.activities[ev.id])await loadActivities(ev,true)}catch(e){notify(e.message,true)}}
function activityCard(ev,a){const card=el('article','portal-activity');const title=action('📌 ['+(a.tipo||'ATIVIDADE')+'] '+a.nome,()=>showDetails(ev,a),'portal-link');card.append(title);card.append(el('p','portal-muted','🎤 '+(a.ministrante||'Convidado não informado')+' · 🕒 '+(a.hora||'Horário não informado')+' · 📍 '+(a.local||'A definir')));card.append(el('p','portal-price',isPaid(a)?fmtMoney(a.precoValor):'Grátis'));const seats=a.online?'Online':a.vagas>0?'Vagas: '+a.vagas+' · Inscritos: '+a.inscritos+' · Disponíveis: '+a.vagasDisponiveis:'Vagas não limitadas';card.append(el('p','portal-muted',seats));const r=a.inscricao;if(r){const status=String(r.status||'').toUpperCase();if(status==='PENDENTE'){card.append(el('p','portal-warning',r.file_name?'📄 Comprovante enviado — aguardando confirmação':'💳 Aguardando comprovante de pagamento'));if(!r.file_name)card.append(action('Continuar pagamento / enviar comprovante',()=>openPayment(r,ev,a),'portal-warning-btn'))}else card.append(el('p','portal-success','✓ INSCRITO'));if(status==='CONFIRMADO'||status==='PENDENTE')card.append(action('Cancelar inscrição',()=>enroll(ev,a,'cancelar'),'portal-danger'));}
else {let closed=false;const d=String(a.data||'').slice(0,10);if(/^\d{4}-\d{2}-\d{2}$/.test(d))closed=d<new Date().toISOString().slice(0,10);const sold=!a.online&&a.vagas>0&&a.vagasDisponiveis<=0;const b=action(closed?'Inscrições encerradas':sold?'Esgotado':'Confirmar inscrição',()=>enroll(ev,a,'inscrever'),closed||sold?'portal-disabled':'portal-primary');b.disabled=closed||sold;card.append(b)}return card}
async function loadActivities(ev,force=false){const box=$('activities-'+ev.id);if(!box)return;if(!force&&!box.hidden){box.hidden=true;return}box.hidden=false;box.replaceChildren(el('p','','Carregando cronograma…'));try{const response=await api('portal',{evento:ev.id});state.activities[ev.id]=response.atividades;box.replaceChildren();if(!response.atividades.length){box.append(el('p','','Nenhuma atividade publicada.'));return}const days=new Map();response.atividades.forEach(a=>{const d=a.data||'Sem data';if(!days.has(d))days.set(d,[]);days.get(d).push(a)});for(const [day,activities] of days){box.append(el('h3','portal-day','📅 Atividades do dia '+dateFormat(day)));activities.forEach(a=>box.append(activityCard(ev,a)))}}catch(e){box.replaceChildren(el('p','portal-error',e.message))}}
function renderEvents(){const list=$('eventsList');list.replaceChildren();if(!state.events.length){list.append(el('p','','Nenhum evento publicado no momento.'));return}state.events.forEach(ev=>{const card=el('article','portal-event');const img=el('div','portal-cover');if(ev.imagem){const pic=el('img');pic.src=ev.imagem;pic.alt='Capa do evento '+ev.nome;pic.loading='lazy';pic.onerror=()=>{pic.remove();img.textContent='Imagem indisponível'};img.append(pic)}else img.textContent='Sem imagem cadastrada';const content=el('div','portal-event-content');content.append(el('h2','',ev.nome),el('p','',ev.resumo||''),el('p','portal-muted','📅 '+(ev.periodo||'Data a definir')+' · 📍 '+(ev.local||'Local a definir')));const details=el('div','portal-activities');details.id='activities-'+ev.id;details.hidden=true;content.append(action('📅 Ver Atividades',()=>loadActivities(ev)));card.append(img,content,details);list.append(card)})}
function renderPassports(tickets){
  const groups=new Map();
  state.passaportes.forEach(r=>{
    if(!groups.has(r.idEvento))groups.set(r.idEvento,{nome:r.nomeEvento,local:r.localEvento,atividades:[]});
    groups.get(r.idEvento).atividades.push(r);
  });
  if(!groups.size){tickets.append(el('p','','Nenhum ingresso ou voucher localizado para este perfil.'));return;}
  for(const group of groups.values()){
    const passport=el('article','ticket-card-passaporte');
    const body=el('div','ticket-corpo-pontilhado');
    body.append(el('h3','ticket-event-title','EVENTO: '+group.nome),el('div','ticket-passport-label','Passaporte:'),
      el('div','ticket-event-location','📍 LOCAL DO EVENTO: '+(group.local||'Local não informado')));
    for(const a of group.atividades){
      body.append(el('div','badge-data-amarela','DIA: '+(a.dataAtividade?dateFormat(a.dataAtividade):'Data não informada')));
      const item=el('div','ticket-atv-item');
      const title=el('div','ticket-atv-title');title.append(el('strong','','[ATIVIDADE] '),document.createTextNode(a.categoria||'Atividade não informada'));item.append(title);
      if(String(a.modalidadeAtividade||'').toLowerCase()==='online'){
        item.append(el('div','ticket-atv-meta','🌐 Modalidade: Online'));
        const url=String(a.enderecoEletronicoAtividade||'').trim();
        const line=el('div','ticket-atv-meta');line.append(document.createTextNode('🔗 Reunião: '));
        if(/^https:\/\/[^\s<>"']+$/i.test(url)){const link=el('a','',url);link.href=url;link.target='_blank';link.rel='noopener noreferrer';line.append(link)}
        else line.append(document.createTextNode('Endereço eletrônico não cadastrado'));
        item.append(line);
      }else item.append(el('div','ticket-atv-meta','📍 Sala / Local: '+(a.salaAtividade||group.local||'Não informado')));
      item.append(el('div','ticket-atv-meta','👤 Responsável: '+(a.ministranteAtividade||'Não informado')),
        el('div','ticket-atv-meta','🕒 Horário: '+(a.horaAtividade||'Não informado')+(a.horaTermino?' às '+a.horaTermino:'')),
        el('div','ticket-atv-voucher','ID Voucher Master: '+a.idInscricao));
      if(a.aguardandoConfirmacao){
        item.append(el('div','ticket-atv-pending',a.comprovanteEnviado?'AGUARDANDO CONFIRMAÇÃO':'PAGAMENTO PENDENTE — COMPROVANTE NÃO ENVIADO'));
      }else if(String(a.statusInscricao).toUpperCase()==='CONFIRMADO'){
        item.append(el('div','ticket-atv-confirmed','INSCRIÇÃO CONFIRMADA'));
      }
      if(!a.dadosCronogramaEncontrados)item.append(el('div','ticket-atv-missing',a.cronogramaAmbiguo?'Mais de um cronograma corresponde a esta inscrição; confira o cadastro da atividade.':'Detalhes da atividade não encontrados no cronograma atual.'));
      body.append(item);
    }
    passport.append(body);tickets.append(passport);
  }
}
function renderLists(){
  const regs=$('registrationList'),tickets=$('ticketList'),certs=$('certificateList');
  [regs,tickets,certs].forEach(x=>x.replaceChildren());
  if(!state.regs.length)regs.append(el('p','','Você ainda não possui inscrições.'));
  state.regs.forEach(r=>{const card=el('article','portal-list-card');
    card.append(el('strong','',r.activity),el('p','','Evento: '+(r.evento||r.event_id)),
      el('p','','Situação: '+(String(r.status).toUpperCase()==='PENDENTE'?'Pendente de confirmação financeira':r.status)+(r.comprovante?' · Comprovante enviado':'')));
    regs.append(card)});
  renderPassports(tickets);
  const certShell=el('div','portal-cert-shell');
  const certCard=el('div','portal-cert-panel');
  certCard.append(el('h2','','Meus Certificados'));
  if(!state.certs.length){certCard.append(el('p','portal-cert-empty','Nenhum certificado liberado pelas autoridades ainda.'));}
  state.certs.forEach(c=>{
    const card=el('article','portal-list-card');
    const eventLine=el('p');eventLine.append(el('strong','','Evento: '),document.createTextNode(c.event_name||c.event_id||'Evento não identificado'));
    const activityLine=el('p');activityLine.append(el('strong','','Atividade: '),document.createTextNode(c.activity||'Atividade não identificada'));
    const certificateLine=el('p');certificateLine.append(el('strong','','Certificado: '));
    if(c.file_url){
      const link=el('a','','Visualizar certificado');
      link.href=String(c.file_url).startsWith('/api/certificados/arquivo/')?c.file_url+'?token='+encodeURIComponent(token()):c.file_url;
      link.target='_blank';link.rel='noopener noreferrer';certificateLine.append(link);
    }else certificateLine.append(document.createTextNode('Indisponível'));
    const closing=el('p','portal-cert-closing','Att,');
    const thanks=el('p','portal-cert-thanks');
    const brand=el('strong','portal-cert-brand');
    brand.append(el('span','portal-cert-brand-for','For'),el('span','portal-cert-brand-evento','Evento'));
    thanks.append(brand,document.createTextNode(' – agradece sua presença.'));
    card.append(eventLine,activityLine,certificateLine,closing,thanks);
    certCard.append(card);
  });
  certShell.append(certCard);certs.append(certShell);
}
async function refresh(){const data=await api('portal');state.events=data.eventos||[];state.regs=data.inscricoes||[];state.certs=data.certificados||[];state.passaportes=data.passaportes||[];state.participantName=(data.usuario||{}).nome||current.nome||"";renderEvents();renderLists()}
(async()=>{try{const theme=await fetch('/api/participante/tema').then(r=>r.json());for(const [key,value] of Object.entries(theme))if(/^#[0-9a-f]{6}$/i.test(value))document.documentElement.style.setProperty('--p-'+key,value)}catch(_){}try{await refresh();show(['eventos','inscricoes','ingressos','certificados'].includes(location.hash.slice(1))?location.hash.slice(1):'eventos')}catch(e){notify(e.message,true)}})();
})();
