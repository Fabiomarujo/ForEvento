"""Distribuição segura de certificados gerados. Não altera a geração nem o banco existente.
SMTP configurado por variáveis de ambiente; nunca expõe credenciais ao navegador.
"""
import os, smtplib, ssl, json, re, stat
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone



def smtp_config_load(base):
    p=Path(base)/'storage'/'private'/'smtp_config.json'
    try:
        data=json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def smtp_config_save(base,data):
    if not isinstance(data,dict):raise ValueError('Dados SMTP inválidos.')
    old=smtp_config_load(base)
    cfg={}
    for key in ('host','sender','username','security'):
        cfg[key]=str(data.get(key,old.get(key,'')) or '').strip()[:255]
    try:cfg['port']=int(data.get('port',old.get('port',587)))
    except (ValueError,TypeError):raise ValueError('Porta SMTP inválida.')
    if not (1<=cfg['port']<=65535):raise ValueError('Porta SMTP fora do intervalo válido.')
    if cfg['security'] not in ('ssl','starttls'):raise ValueError('Escolha SSL ou STARTTLS.')
    if not cfg['host'] or not cfg['sender'] or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',cfg['sender']):
        raise ValueError('Informe servidor SMTP e remetente válido.')
    # Campo vazio conserva a senha existente; nunca retorna senha para o navegador.
    cfg['password']=str(data.get('password') or old.get('password') or '')
    p=Path(base)/'storage'/'private'/'smtp_config.json'
    p.parent.mkdir(parents=True,exist_ok=True)
    try:p.parent.chmod(0o700)
    except OSError:pass
    import tempfile
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.smtp-',text=True)
    try:
        os.chmod(tmp,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(cfg,f,ensure_ascii=False)
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def smtp_effective(base):
    saved=smtp_config_load(base)
    return {
      'host':saved.get('host') or os.environ.get('FOREVENTO_SMTP_HOST',''),
      'sender':saved.get('sender') or os.environ.get('FOREVENTO_SMTP_FROM',''),
      'port':int(saved.get('port') or os.environ.get('FOREVENTO_SMTP_PORT','587')),
      'username':saved.get('username') or os.environ.get('FOREVENTO_SMTP_USER',''),
      'password':saved.get('password') or os.environ.get('FOREVENTO_SMTP_PASSWORD',''),
      'security':saved.get('security') or os.environ.get('FOREVENTO_SMTP_SECURITY','starttls')
    }

def smtp_test(base,recipient):
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient):
        return {'sucesso':False,'mensagem':'Informe um e-mail de teste válido.'}
    cfg=smtp_effective(base)
    if not cfg['host'] or not cfg['sender']:
        return {'sucesso':False,'mensagem':'Configure servidor e remetente SMTP.'}
    msg=EmailMessage();msg['From']=cfg['sender'];msg['To']=recipient;msg['Subject']='ForEvento - teste SMTP'
    msg.set_content('Esta é uma mensagem de teste da configuração SMTP do ForEvento.')
    try:
        if cfg['security']=='ssl':smtp=smtplib.SMTP_SSL(cfg['host'],cfg['port'],timeout=20,context=ssl.create_default_context())
        else:smtp=smtplib.SMTP(cfg['host'],cfg['port'],timeout=20)
        with smtp as client:
            if cfg['security']=='starttls':client.starttls(context=ssl.create_default_context())
            if cfg['username']:client.login(cfg['username'],cfg['password'])
            refused=client.send_message(msg)
            if refused:raise RuntimeError('Destinatário recusado')
        return {'sucesso':True,'mensagem':'Mensagem de teste aceita pelo servidor SMTP. Verifique a caixa de entrada.'}
    except (OSError,smtplib.SMTPException,RuntimeError) as exc:
        return {'sucesso':False,'mensagem':'Falha no teste SMTP: '+type(exc).__name__+'. Confira as configurações.'}

def _record(c, cid, status, reason=''):
    key='cert_delivery:'+cid
    value=json.dumps({'status':status,'at':datetime.now(timezone.utc).isoformat(), 'reason':str(reason)[:350]},ensure_ascii=False)
    c.execute('insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v',(key,value))
    c.commit()


def _preencher_tags_email(c, cert, subject, message):
    """Substitui tags do e-mail sem alterar o gerador ou o banco de dados."""
    user = c.execute('select name from users where id=?', (cert['user_id'],)).fetchone()
    event = c.execute('select name from events where id=?', (cert['event_id'],)).fetchone()
    nome = str(user['name'] or '').strip() if user else ''
    evento = str(event['name'] or '').strip() if event else ''
    atividade = str(cert['activity'] or '').strip()
    codigo = str(cert['validation_code'] or '').strip()
    url = str(cert['url'] or '').strip()
    valores = {
        'nome': nome, 'nome_participante': nome, 'nomealuno': nome,
        'participante': nome, 'nomeevento': evento, 'nome_evento': evento,
        'evento': evento, 'atividade': atividade, 'nomeatividade': atividade,
        'nome_atividade': atividade, 'tituloatividade': atividade,
        'titulo_atividade': atividade, 'codigo': codigo,
        'codigovalidacao': codigo, 'codigo_validacao': codigo,
        'codigo_credencial': codigo, 'urlvalidacao': url,
        'url_validacao': url, 'url': url,
    }
    # Suporta os modelos <<tag>> e as configurações legadas {{TAG}}.
    pattern = re.compile(r'<<\s*([A-Za-z_][A-Za-z_0-9]*)\s*>>|\{\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*\}\}')
    faltantes = set()
    desconhecidas = set()
    def trocar(match):
        chave = (match.group(1) or match.group(2)).casefold()
        if chave not in valores:
            desconhecidas.add(match.group(0))
            return match.group(0)
        valor = valores[chave]
        if not valor:
            faltantes.add(match.group(0))
            return match.group(0)
        return valor
    assunto = pattern.sub(trocar, subject)
    corpo = pattern.sub(trocar, message)
    if faltantes or desconhecidas:
        tags = ', '.join(sorted(faltantes | desconhecidas))
        return None, None, 'Tags do e-mail sem valor ou desconhecidas: ' + tags[:240]
    return assunto, corpo, None


def enviar_certificado(c, base, cid, options):
    if not re.fullmatch(r'CERT-[A-F0-9]{16}',str(cid)):
        return {'sucesso':False,'mensagem':'Identificador do certificado inválido.'}
    cert=c.execute('select * from certificates where id=?',(cid,)).fetchone()
    if not cert: return {'sucesso':False,'mensagem':'Certificado não encontrado.'}
    if str(cert['status'] or '').upper() not in ('GERADO','ENVIADO'):
        return {'sucesso':False,'mensagem':'É necessário gerar o certificado antes de enviar.'}
    regs=c.execute('select * from registrations where event_id=? and activity=? and (user_id=? or lower(email)=lower(?))',
        (cert['event_id'],cert['activity'],cert['user_id'],cert['email'])).fetchall()
    if len(regs)!=1:
        return {'sucesso':False,'mensagem':'Inscrição não localizada de forma inequívoca.'}
    # Check payment and attendance via same rule as presence/certificate generation.
    from .main import _inscricao_liberada_para_presenca_certificado
    if not _inscricao_liberada_para_presenca_certificado(c,regs[0]):
        return {'sucesso':False,'mensagem':'Pagamento ainda não confirmado.'}
    attendance=c.execute('select status from attendance where event_id=? and activity=? and (user_id=? or lower(email)=lower(?)) order by id desc limit 1',
        (cert['event_id'],cert['activity'],cert['user_id'],cert['email'])).fetchone()
    if not attendance or str(attendance['status'] or '').strip().upper() not in ('PRESENTE','PRESENÇA','PRESENCA','CONFIRMADO','CONFIRMADA'):
        return {'sucesso':False,'mensagem':'Presença não confirmada.'}
    path=Path(base)/'storage'/'certificados'/(cid+'.pdf')
    if not path.is_file():return {'sucesso':False,'mensagem':'PDF não localizado no armazenamento do servidor.'}
    recipient=str(cert['email'] or '').strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient):
        return {'sucesso':False,'mensagem':'E-mail cadastrado inválido.'}
    requested=str(options.get('email') or '').strip()
    if requested and requested.casefold()!=recipient.casefold():
        return {'sucesso':False,'mensagem':'O destinatário deve corresponder ao e-mail cadastrado na inscrição.'}
    cfg_smtp=smtp_effective(base)
    host=cfg_smtp['host'];sender=cfg_smtp['sender']
    if not host or not sender:
        return {'sucesso':False,'mensagem':'Envio não realizado: configure o SMTP em Certificados → Configurar.'}
    port=cfg_smtp['port'];username=cfg_smtp['username'];password=cfg_smtp['password'];mode=cfg_smtp['security']
    if mode not in ('starttls','ssl'):
        return {'sucesso':False,'mensagem':'Segurança SMTP inválida.'}
    saved=c.execute('select v from settings where k=?',('certcfg:'+str(cert['event_id']),)).fetchone()
    try:cfg=json.loads(saved['v']) if saved else {}
    except (ValueError,TypeError):cfg={}
    subject=str(cfg.get('assunto') or options.get('assuntoEmail') or 'Seu certificado está disponível - ForEvento')[:180]
    message=str(cfg.get('mensagem') or options.get('mensagemEmail') or 'Seu certificado está disponível na sua área do participante.')
    subject, message, erro_tags = _preencher_tags_email(c, cert, subject, message)
    if erro_tags:
        return {'sucesso':False,'mensagem':erro_tags}
    if str(cert['status']).upper()=='ENVIADO' and not options.get('reenviar'):
        return {'sucesso':False,'mensagem':'Certificado já enviado. Para reenviar, solicite uma nova tentativa explícita.'}
    mail=EmailMessage()
    mail['From']=sender;mail['To']=recipient;mail['Subject']=subject
    mail.set_content(message+'\n\nAcesse sua área do participante no ForEvento para visualizar o certificado.')
    mail.add_attachment(path.read_bytes(),maintype='application',subtype='pdf',filename='certificado.pdf')
    try:
        if mode=='ssl':smtp=smtplib.SMTP_SSL(host,port,timeout=25,context=ssl.create_default_context())
        else:smtp=smtplib.SMTP(host,port,timeout=25)
        with smtp as client:
            if mode=='starttls':client.starttls(context=ssl.create_default_context())
            if username:client.login(username,password)
            refused=client.send_message(mail)
            if refused:raise RuntimeError('O servidor recusou o destinatário.')
    except Exception as exc:
        _record(c,cid,'ERRO',type(exc).__name__)
        return {'sucesso':False,'mensagem':'Falha no envio SMTP ('+type(exc).__name__+'). Certificado continua GERADO para nova tentativa.'}
    c.execute("update certificates set status='ENVIADO' where id=?",(cid,))
    c.commit();_record(c,cid,'ENVIADO')
    return {'sucesso':True,'mensagem':'E-mail aceito pelo servidor SMTP e certificado liberado na área do participante.'}
