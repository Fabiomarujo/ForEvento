from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from .presenca_pdf import build_pdf
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3, uuid, datetime, json, re, secrets, hashlib, io

BASE=Path(__file__).resolve().parent.parent
DB=BASE/"forevento.db"
app=FastAPI(title="ForEvento - conversão direta do Apps Script")
app.mount("/static",StaticFiles(directory=BASE/"app/static"),name="static")
templates=Jinja2Templates(directory=str(BASE/"app/templates"))

def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=con()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id TEXT PRIMARY KEY,name TEXT,cpf TEXT,phone TEXT,email TEXT UNIQUE,password TEXT,
      role TEXT DEFAULT 'Participante',language TEXT DEFAULT 'pt',access_status TEXT DEFAULT 'Autorizado');
    CREATE TABLE IF NOT EXISTS events(
      id TEXT PRIMARY KEY,image TEXT,name TEXT,summary TEXT,period TEXT,location TEXT,
      capacity INTEGER DEFAULT 0,keyword TEXT DEFAULT 'GERAL',status TEXT DEFAULT 'RASCUNHO');
    CREATE TABLE IF NOT EXISTS schedules(
      id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,synopsis TEXT,date TEXT,time TEXT,
      type TEXT,location TEXT,image TEXT,speaker TEXT,capacity INTEGER,synopsis_activity TEXT,
      workload TEXT,price_model TEXT,price REAL,curriculum TEXT,syllabus TEXT);
    CREATE TABLE IF NOT EXISTS registrations(
      id TEXT PRIMARY KEY,user_id TEXT,email TEXT,event_id TEXT,activity TEXT,type TEXT,
      status TEXT DEFAULT 'CONFIRMADO',created_at TEXT);
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,activity TEXT,user_id TEXT,email TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS pix_config(
      event_id TEXT PRIMARY KEY,pix_key TEXT,receiver TEXT,provider TEXT,environment TEXT,deadline INTEGER DEFAULT 20);
    CREATE TABLE IF NOT EXISTS receipts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,registration_id TEXT,event_id TEXT,email TEXT,activity TEXT,
      value REAL,file_name TEXT,file_data TEXT,status TEXT DEFAULT 'PENDENTE',sent_at TEXT);
    CREATE TABLE IF NOT EXISTS certificates(
      id TEXT PRIMARY KEY,event_id TEXT,user_id TEXT,email TEXT,activity TEXT,status TEXT DEFAULT 'PENDENTE',
      validation_code TEXT,url TEXT,file_url TEXT,signature_type TEXT,language TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,last_activity TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS role_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,requested_role TEXT NOT NULL,event_id TEXT DEFAULT '',reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDENTE',created_at TEXT NOT NULL,decided_at TEXT DEFAULT '',decided_by TEXT DEFAULT '',decision_note TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS password_resets(token TEXT PRIMARY KEY,user_id TEXT,expires_at TEXT,used INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS carts(id TEXT PRIMARY KEY,user_id TEXT,event_id TEXT,status TEXT DEFAULT 'ABERTO',created_at TEXT,expires_at TEXT);
    CREATE TABLE IF NOT EXISTS cart_items(id INTEGER PRIMARY KEY AUTOINCREMENT,cart_id TEXT,event_id TEXT,activity TEXT,value REAL,status TEXT DEFAULT 'RESERVADO');
    CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,user_id TEXT,event_id TEXT,method TEXT,status TEXT,txid TEXT,total REAL,proof_name TEXT,proof_data TEXT,paid_at TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS refunds(id TEXT PRIMARY KEY,payment_id TEXT,user_id TEXT,event_id TEXT,activity TEXT,value REAL,proof_name TEXT,proof_data TEXT,note TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS role_permissions(role TEXT,permission TEXT,enabled INTEGER DEFAULT 0,PRIMARY KEY(role,permission));
    CREATE TABLE IF NOT EXISTS user_permissions(user_id TEXT,permission TEXT,enabled INTEGER DEFAULT 0,PRIMARY KEY(user_id,permission));
    CREATE TABLE IF NOT EXISTS user_id_sequence(id INTEGER PRIMARY KEY CHECK(id=1), last_number INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS certificate_models(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,filename TEXT,language TEXT,signature_type TEXT,file_path TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS showcase_banners(id TEXT PRIMARY KEY,name TEXT,image TEXT,title TEXT,synopsis TEXT,banner_type TEXT DEFAULT 'DIVULGACAO',event_id TEXT,status TEXT DEFAULT 'ATIVO',display_order INTEGER DEFAULT 0,created_at TEXT);
    """)
    # migrações aditivas: nunca exigir apagar o banco
    def addcol(table,col,decl):
        cols={x[1] for x in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols: c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    addcol("showcase_banners","publish_date","TEXT DEFAULT ''")
    addcol("showcase_banners","end_date","TEXT DEFAULT ''")
    addcol("events","short_synopsis","TEXT DEFAULT ''")
    addcol("events","specific_vacancies","INTEGER DEFAULT 0")
    addcol("events","electronic_address","TEXT DEFAULT ''")
    addcol("schedules","end_time","TEXT DEFAULT ''")
    addcol("schedules","electronic_address","TEXT DEFAULT ''")
    addcol("schedules","modality","TEXT DEFAULT 'Presencial'")
    addcol("schedules","titulo","TEXT DEFAULT ''")  # migração aditiva, sem apagar registros
    addcol("users","password_hash","TEXT DEFAULT ''")
    # Identidade pública permanente EVT-#####L. O Master usa sempre EVT-00000A.
    master=c.execute("select * from users where role='ADMINISTRADOR_MASTER' or lower(email)='admin@forevento.local' order by case when id='EVT-00000A' then 0 else 1 end limit 1").fetchone()
    if master and master["id"]!='EVT-00000A':
        old=master["id"]
        if not c.execute("select 1 from users where id='EVT-00000A'").fetchone():
            c.execute("update users set id='EVT-00000A' where id=?",(old,))
            for t in ('registrations','attendance','certificates','carts','payments','refunds','sessions','password_resets','user_permissions'):
                try:c.execute(f"update {t} set user_id='EVT-00000A' where user_id=?",(old,))
                except sqlite3.OperationalError:pass
    c.execute("update users set role='MINISTRANTE' where upper(role) in ('MINISTRANTE / EXTENSIONISTA','MINISTRANTE/EXTENSIONISTA')")
    c.execute("update users set role='MONITOR_EXTENSIONISTA' where upper(role) in ('MONITOR','MONITOR / EXTENSIONISTA','MONITOR/EXTENSIONISTA')")
    c.execute("""INSERT OR IGNORE INTO users(id,name,cpf,phone,email,password,role,language,access_status)
                 VALUES('EVT-00000A','Administrador','','','ligaforcode@gmail.com','1234','ADMINISTRADOR_MASTER','pt','Autorizado')""")
    c.execute("update users set role='ADMINISTRADOR_MASTER', email=CASE WHEN lower(email)='admin@forevento.local' THEN 'ligaforcode@gmail.com' ELSE email END, password=CASE WHEN password='Admin@123' OR password IS NULL OR password='' THEN '1234' ELSE password END where id='EVT-00000A'")
    defaults={
      "EQUIPE_ADMINISTRATIVA":["eventos_visualizar","eventos_editar","cronograma_visualizar","presenca_lancar","lista_pdf","financeiro_visualizar","financeiro_auditoria","cert_consultar","cert_visualizar","relatorios_visualizar","usuarios_visualizar","usuarios_editar","usuarios_bloquear","perfil","vitrine"],
      "MINISTRANTE":["cronograma_visualizar","presenca_lancar","lista_pdf","perfil"],
      "MONITOR_EXTENSIONISTA":["cronograma_visualizar","presenca_lancar","lista_pdf","perfil"],
      "COORDENADOR":["eventos_visualizar","eventos_editar","eventos_publicar","cronograma_visualizar","presenca_lancar","lista_pdf","financeiro_visualizar","financeiro_auditoria","cert_consultar","cert_visualizar","relatorios_visualizar","usuarios_visualizar","usuarios_editar","usuarios_bloquear","perfil"]
    }
    for role,perms in defaults.items():
        for perm in perms:c.execute("insert or ignore into role_permissions(role,permission,enabled) values(?,?,1)",(role,perm))
    c.commit(); c.close()
# Backup exclusivamente manual: nenhuma cópia é iniciada automaticamente.
from .backup_db import backup as _backup_db, status as _backup_status
import logging
from . import backup_manager as _bm
_bm.apply_pending_on_startup()
init_db()
_bm.start_scheduler()

def rowdict(r): return dict(r) if r else None
def password_hash(v): return hashlib.sha256(str(v or "").encode("utf-8")).hexdigest()
def password_ok(stored, supplied):
    stored=str(stored or ""); supplied=str(supplied or "")
    return stored==supplied or stored==password_hash(supplied)
def now(): return datetime.datetime.now().isoformat(timespec="seconds")
def event_code(c):
    y=datetime.datetime.now().year
    rows=c.execute("select id from events where id like ?",(f"EVT-{y}-%",)).fetchall()
    nums=[]
    for r in rows:
        m=re.search(r'(\d+)$',r["id"]); nums.append(int(m.group(1)) if m else 0)
    return f"EVT-{y}-{max(nums+[0])+1:03d}"

@app.get("/",response_class=HTMLResponse)
def home(request:Request, page:str="", pagina:str="", codigo:str="", tab:str=""):
    target=(pagina or page or "").strip()
    names={
      "admin-dashboard":"admin.html","equipe-dashboard":"admin.html",
      "assinatura-autoridade":"autoridade_assinatura.html","validar-certificado":"validar_certificado.html",
      "cronograma-lista":"cronograma_lista.html","configurar":"configurar.html","configurar-permissoes":"configurar_permissoes.html","backup-restauracao":"backup_restauracao.html",
      "financeiro-auditoria":"financeiro_auditoria.html","reembolso":"reembolso.html",
      "participante-dashboard":"participante_dashboard.html","login":"login.html","cadastro":"cadastro.html","esqueci-senha":"esqueci_senha.html","perfil":"perfil.html","vitrine-admin":"vitrine_admin.html","certificados-modelos":"certificados.html","certificados-configurar":"certificados.html","certificados-gerar":"certificados.html"
    }
    name=names.get(target,"vitrine.html")
    return templates.TemplateResponse(request=request,name=name,context={"base_url":str(request.base_url).rstrip("/"),"codigoInicial":codigo,"cert_section":target,"admin_tab":tab,"config_section":target})

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request): return templates.TemplateResponse(request=request,name="login.html",context={"base_url":str(request.base_url).rstrip("/")})
@app.get("/cadastro",response_class=HTMLResponse)
def cadastro_page(request:Request): return templates.TemplateResponse(request=request,name="cadastro.html",context={"base_url":str(request.base_url).rstrip("/")})
@app.get("/esqueci-senha",response_class=HTMLResponse)
def esqueci_page(request:Request): return templates.TemplateResponse(request=request,name="esqueci_senha.html",context={"base_url":str(request.base_url).rstrip("/")})

@app.get("/admin-dashboard",response_class=HTMLResponse)
def admin(request:Request):
    return templates.TemplateResponse(request=request,name="admin.html",context={"base_url":str(request.base_url).rstrip("/")})

@app.get("/equipe-dashboard",response_class=HTMLResponse)
def equipe(request:Request):
    return templates.TemplateResponse(request=request,name="admin.html",context={"base_url":str(request.base_url).rstrip("/")})

@app.get("/assinatura-autoridade",response_class=HTMLResponse)
def assinatura(request:Request):
    return templates.TemplateResponse(request=request,name="autoridade_assinatura.html",context={"base_url":str(request.base_url).rstrip("/")})

@app.get("/validar-certificado",response_class=HTMLResponse)
def validar(request:Request,codigo:str=""):
    return templates.TemplateResponse(request=request,name="validar_certificado.html",context={"base_url":str(request.base_url).rstrip("/"),"codigoInicial":codigo})

@app.get("/manual-usuario",response_class=HTMLResponse)
def manual(request:Request):
    return templates.TemplateResponse(request=request,name="manual_usuario.html",context={"base_url":str(request.base_url).rstrip("/")})

def realizarLogin(args):
    email,senha,tipo=(args+[None,None,None])[:3]
    c=con(); r=c.execute("select * from users where lower(email)=lower(?)",(str(email or "").strip(),)).fetchone()
    if not r or not password_ok(r["password"],str(senha or "").strip()):
        c.close(); return {"sucesso":False,"mensagem":"❌ E-mail ou senha incorretos."}
    st=(r["access_status"] or "Autorizado").upper()
    if st=="PENDENTE": c.close(); return {"sucesso":False,"mensagem":"🔒 Conta aguardando liberação."}
    if st=="DESATIVADO": c.close(); return {"sucesso":False,"mensagem":"🛑 Conta desativada."}
    token=secrets.token_urlsafe(32)
    c.execute("insert into sessions(token,user_id,last_activity,created_at) values(?,?,?,?)",(token,r["id"],now(),now())); c.commit(); c.close()
    role=r["role"] or "Participante"
    destino="participante-dashboard" if role.upper()=="PARTICIPANTE" else "admin-dashboard"
    return {"sucesso":True,"id":r["id"],"nome":r["name"],"email":r["email"],"tipo":role,"idioma":r["language"],"token":token,"destino":destino,"mensagem":"🎉 Autenticação bem-sucedida!"}

def next_user_public_id(c,name):
    """Gera EVT-#####L uma única vez; nunca recalcula a letra após alteração do nome."""
    row=c.execute("select last_number from user_id_sequence where id=1").fetchone()
    if not row:
        nums=[]
        for r in c.execute("select id from users where id glob 'EVT-[0-9][0-9][0-9][0-9][0-9]*'").fetchall():
            m=re.match(r'^EVT-(\d{5})',r['id'] or '')
            if m: nums.append(int(m.group(1)))
        last=max(nums+[0]); c.execute("insert into user_id_sequence(id,last_number) values(1,?)",(last,))
    else:last=int(row['last_number'])
    n=last+1
    if n>99999: raise ValueError('Limite de 99.999 IDs públicos atingido.')
    c.execute("update user_id_sequence set last_number=? where id=1",(n,))
    clean=(str(name or '').strip() or 'X')
    import unicodedata
    first=unicodedata.normalize('NFKD',clean[0]).encode('ascii','ignore').decode('ascii').upper() or 'X'
    first=re.sub(r'[^A-Z]','X',first[:1])
    return f"EVT-{n:05d}{first}"

def cpf_valid(value):
    digits=re.sub(r'\D','',str(value or ''))
    if len(digits)!=11 or len(set(digits))==1:return False
    for n in (9,10):
        check=(sum(int(digits[i])*(n+1-i) for i in range(n))*10)%11
        if check==10:check=0
        if check!=int(digits[n]):return False
    return True

def cadastrarUsuario(args):
    d=(args or [{}])[0] or {}
    idioma=str(d.get("idioma") or "pt").lower()
    if idioma not in ("pt","en","es","fr","it","zh"): idioma="pt"
    nome=str(d.get("nome") or "").strip().upper()
    email=str(d.get("email") or "").strip().lower()
    senha=str(d.get("senha") or "")
    telefone=str(d.get("telefone") or "").strip()
    if d.get("confirmarSenha") is not None and senha!=d.get("confirmarSenha"):return {"sucesso":False,"mensagem":"As senhas não coincidem."}
    cpf=re.sub(r"\D", "", str(d.get("cpf") or ""))
    if not nome or not email or not telefone or not senha:return {"sucesso":False,"mensagem":"Preencha os campos obrigatórios."}
    if idioma=="pt" and not cpf:return {"sucesso":False,"mensagem":"CPF obrigatório para o idioma português."}
    if cpf and not cpf_valid(cpf):return {"sucesso":False,"mensagem":"Informe um CPF válido."}
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):return {"sucesso":False,"mensagem":"E-mail inválido."}
    if len(senha)<4:return {"sucesso":False,"mensagem":"Senha deve ter pelo menos 4 caracteres."}
    phone_digits=re.sub(r"\D","",telefone)
    if not (8<=len(phone_digits)<=16):return {"sucesso":False,"mensagem":"Telefone inválido."}
    c=con()
    try:
        if cpf and c.execute("select 1 from users where replace(replace(replace(cpf,'.',''),'-',''),' ','')=?",(cpf,)).fetchone():
            return {"sucesso":False,"mensagem":"CPF já cadastrado."}
        uid=next_user_public_id(c,nome)
        c.execute("insert into users(id,name,cpf,phone,email,password,role,language,access_status) values(?,?,?,?,?,?,?,?,?)",
        (uid,nome,cpf,telefone,email,password_hash(senha),"Participante",idioma,"Autorizado"))
        c.commit(); return {"sucesso":True,"mensagem":"Cadastro realizado com sucesso!","id":uid}
    except sqlite3.IntegrityError:return {"sucesso":False,"mensagem":"E-mail já cadastrado."}
    finally:c.close()

def recuperarSenhaCasada(args):
    email=str((args or [""])[0]).strip(); c=con(); r=c.execute("select id,email from users where lower(email)=lower(?)",(email,)).fetchone()
    if not r: c.close(); return {"sucesso":False,"mensagem":"Email não está cadastrado. Volte para a tela de login e realize o cadastro."}
    token=secrets.token_urlsafe(24); exp=(datetime.datetime.now()+datetime.timedelta(minutes=30)).isoformat(timespec="seconds")
    c.execute("insert into password_resets(token,user_id,expires_at,used) values(?,?,?,0)",(token,r["id"],exp)); c.commit(); c.close()
    return {"sucesso":True,"mensagem":"Solicitação de redefinição criada. Em produção o link será enviado por e-mail.","tokenTesteLocal":token}

def redefinirSenha(args):
    d=(args or [{}])[0] or {}; token=d.get("token",""); nova=d.get("novaSenha","")
    if len(nova)<4:return {"sucesso":False,"mensagem":"A nova senha deve ter pelo menos 4 caracteres."}
    c=con(); r=c.execute("select * from password_resets where token=? and used=0",(token,)).fetchone()
    if not r or r["expires_at"]<now(): c.close(); return {"sucesso":False,"mensagem":"Link inválido ou expirado."}
    c.execute("update users set password=? where id=?",(password_hash(nova),r["user_id"])); c.execute("update password_resets set used=1 where token=?",(token,));c.commit();c.close()
    return {"sucesso":True,"mensagem":"Senha redefinida com sucesso."}

def obterSeguranca(args):
    c=con(); r=c.execute("select v from settings where k='session_policy'").fetchone(); c.close()
    default={"administrativo":30,"participante":10,"aviso":True}
    if r:
        try: default.update(json.loads(r['v']))
        except (ValueError,TypeError): pass
    return default

def salvarSeguranca(args):
    d=(args or [{}])[0] or {}
    token=str(d.get('token',''))
    c=con()
    who=c.execute("select u.role from sessions s join users u on u.id=s.user_id where s.token=?",(token,)).fetchone()
    if not who or str(who['role']).strip().lower().replace(' ','_') not in ('administrador_master','admin_master','administrador','admin'):
        c.close();return {'sucesso':False,'mensagem':'Somente o Administrador Master pode alterar a segurança.'}
    try:
        a=int(d.get('administrativo')); b=int(d.get('participante'))
        if not 5<=a<=240 or not 5<=b<=240:raise ValueError()
    except (ValueError,TypeError):
        c.close();return {'sucesso':False,'mensagem':'Informe um tempo entre 5 e 240 minutos.'}
    policy={'administrativo':a,'participante':b,'aviso':bool(d.get('aviso',True))}
    c.execute("insert into settings(k,v) values('session_policy',?) on conflict(k) do update set v=excluded.v",(json.dumps(policy),))
    c.commit();c.close();return {'sucesso':True,'mensagem':'Tempos de inatividade salvos.'}

def validarSessao(args):
    token=str((args or [""])[0]); c=con(); r=c.execute("select s.*,u.name,u.email,u.role,u.language from sessions s join users u on u.id=s.user_id where token=?",(token,)).fetchone()
    if not r:c.close();return {"sucesso":False}
    last=datetime.datetime.fromisoformat(r["last_activity"])
    policy=obterSeguranca([])
    role=str(r["role"] or "").lower()
    limit=policy["participante"] if role in ("participante","participant") else policy["administrativo"]
    if datetime.datetime.now()-last>datetime.timedelta(minutes=limit):
        c.execute("delete from sessions where token=?",(token,));c.commit();c.close();return {"sucesso":False,"expirada":True}
    c.execute("update sessions set last_activity=? where token=?",(now(),token));c.commit();c.close()
    return {"sucesso":True,"id":r["user_id"],"nome":r["name"],"email":r["email"],"tipo":r["role"],"idioma":r["language"]}

def encerrarSessao(args):
    token=str((args or [""])[0]);c=con();c.execute("delete from sessions where token=?",(token,));c.commit();c.close();return {"sucesso":True}

def listarEventos(args):
    publico=bool(args and str(args[0]).lower() in ("publico","true","1"))
    c=con(); rs=c.execute("select * from events "+("where upper(status)='PUBLICADO' " if publico else "")+"order by name").fetchall()
    out=[]
    for r in rs:
        inscritos=c.execute("select count(*) n from registrations where event_id=? and upper(status)='CONFIRMADO'",(r["id"],)).fetchone()["n"]
        out.append({"id":r["id"],"imagem":r["image"],"nome":r["name"],"resumo":r["summary"],"sinopseCurta":r["short_synopsis"],
        "periodo":r["period"],"local":r["location"],"vagas":r["capacity"],"vagasDisponiveis":max(0,int(r["capacity"] or 0)-inscritos),
        "vagasEspecificas":r["specific_vacancies"],"enderecoEletronico":r["electronic_address"],"palavraChave":r["keyword"],"status":r["status"]})
    c.close(); return out

def criarEvento(args):
    """Salvar evento e atividades preservando IDs e vínculos históricos.

    Transação única: falha em qualquer atividade desfaz todo o salvamento.
    """
    d=(args or [{}])[0] or {}
    if not str(d.get("nome") or "").strip():
        return {"sucesso":False,"mensagem":"Informe o nome do evento."}
    atvs=d.get("atividades")
    if atvs is None or not isinstance(atvs,list):
        return {"sucesso":False,"mensagem":"A lista de atividades não foi carregada. Atualize a tela e tente novamente."}
    try:
        vagas=int(d.get("vagas") or 0)
        if vagas<0:raise ValueError("Vagas negativas")
        for a in atvs:
            if not isinstance(a,dict):raise ValueError("Atividade inválida")
            if not str(a.get("titulo") or "").strip() and not a.get("id"):
                raise ValueError("Informe o título das novas atividades.")
            if int(a.get("vagas") or 0)<0:raise ValueError("Vagas da atividade inválidas")
        c=con()
        try:
            c.execute('BEGIN IMMEDIATE')
            old=str(d.get("id") or "")
            exists=c.execute('select id,status from events where id=?',(old,)).fetchone() if old else None
            if old and not exists:
                raise ValueError("O evento original não foi encontrado. Atualize a página antes de salvar.")
            status=str(d.get("status") or "PUBLICADO").upper()
            if status not in ('PUBLICADO','RASCUNHO'):
                raise ValueError("Status de evento inválido")
            eid=(event_code(c) if status=='PUBLICADO' else 'RASC-'+str(uuid.uuid4())) if not exists else old
            # Não trocar ID de evento publicado em edição: vínculos devem permanecer estáveis.
            vals=(eid,d.get("imagem", ""),str(d.get("nome", "")).upper(),d.get("resumo", ""),d.get("periodo", ""),str(d.get("local", "")).upper(),vagas,str(d.get("palavraChave") or "GERAL").upper(),status)
            c.execute("""insert into events(id,image,name,summary,period,location,capacity,keyword,status) values(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET image=excluded.image,name=excluded.name,summary=excluded.summary,
              period=excluded.period,location=excluded.location,capacity=excluded.capacity,keyword=excluded.keyword,status=excluded.status""",vals)
            c.execute("update events set short_synopsis=?,specific_vacancies=?,electronic_address=? where id=?",
              (d.get("sinopseCurta", ""),int(d.get("vagasEspecificas") or 0),d.get("enderecoEletronico", ""),eid))
            existing={int(r['id']):r for r in c.execute('select * from schedules where event_id=?',(eid,)).fetchall()}
            retained=set()
            for a in atvs:
                sid=a.get('id')
                sid=int(sid) if sid not in (None,'') else None
                if sid is not None and sid not in existing:
                    raise ValueError('A atividade original não foi encontrada. Atualize a tela e tente novamente.')
                if sid in retained:raise ValueError('Atividade duplicada no formulário.')
                if sid is not None:retained.add(sid)
                titulo=str(a.get('titulo') or '').strip()
                if not titulo and sid is not None:titulo=str(existing[sid]['titulo'] or '')
                vals_a=(d.get('sinopseCronograma',''),a.get('data',''),a.get('hora',''),str(a.get('tipo','')).upper(),str(a.get('local','')).upper(),a.get('img',''),str(a.get('ministrante','')).upper(),int(a.get('vagas') or 0),a.get('sinopse',''),a.get('cargaHoraria','0h'),a.get('modeloPreco','Gratis'),float(a.get('precoValor') or 0),a.get('curriculo',''),a.get('ementa',''),a.get('horaTermino','') or a.get('endTime',''),a.get('enderecoEletronico',''),titulo,a.get('modalidade','Presencial'))
                if sid is None:
                    c.execute("""insert into schedules(event_id,synopsis,date,time,type,location,image,speaker,capacity,synopsis_activity,workload,price_model,price,curriculum,syllabus,end_time,electronic_address,titulo,modality) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(eid,)+vals_a)
                else:
                    # Vínculos históricos usam o nome legado, não o novo título.
                    previous=existing[sid]
                    legacy_old=previous['synopsis_activity'] or previous['syllabus'] or previous['speaker'] or ''
                    has_links=any(c.execute(f"select 1 from {t} where event_id=? and activity=? limit 1",(eid,legacy_old)).fetchone() for t in ('registrations','attendance','certificates'))
                    if has_links and (a.get('sinopse','')!=previous['synopsis_activity'] or str(a.get('ministrante','')).upper()!=str(previous['speaker'] or '')):
                        raise ValueError('Esta atividade possui inscrições, presenças ou certificados. Não altere a sinopse ou o responsável vinculados aos registros existentes.')
                    c.execute("""update schedules set synopsis=?,date=?,time=?,type=?,location=?,image=?,speaker=?,capacity=?,synopsis_activity=?,workload=?,price_model=?,price=?,curriculum=?,syllabus=?,end_time=?,electronic_address=?,titulo=?,modality=? where id=? and event_id=?""",vals_a+(sid,eid))
            removed=set(existing)-retained
            for sid in removed:
                previous=existing[sid]
                legacy=previous['synopsis_activity'] or previous['syllabus'] or previous['speaker'] or ''
                linked=any(c.execute(f"select 1 from {t} where event_id=? and activity=? limit 1",(eid,legacy)).fetchone() for t in ('registrations','attendance','certificates'))
                if linked:raise ValueError('Não é possível excluir uma atividade que possui inscrições, presenças ou certificados.')
                c.execute('delete from schedules where id=? and event_id=?',(sid,eid))
            c.commit()
            return {"sucesso":True,"mensagem":"Evento salvo com sucesso.","id":eid,"idEvento":eid}
        except Exception:
            c.rollback()
            raise
        finally:c.close()
    except (ValueError,TypeError,sqlite3.Error) as exc:
        return {"sucesso":False,"mensagem":str(exc)}

def buscarCronogramaEvento(args):
    eid=str((args or [""])[0]); c=con()
    rs=c.execute("select * from schedules where event_id=? order by id",(eid,)).fetchall()
    result=[]
    for r in rs:
        activity_name=r["synopsis_activity"] or r["syllabus"] or r["speaker"] or ""
        # Contar inscrições vinculadas à atividade, sem somar inscrições canceladas.
        filled=c.execute("""select count(*) from registrations
            where event_id=? and activity=? and upper(coalesce(status,''))
            not in ('CANCELADO','CANCELADA','CANCELED','CANCELLED')""",
            (eid,activity_name)).fetchone()[0]
        cap=int(r["capacity"] or 0)
        # Usa a modalidade persistida no cadastro. Um link eletrônico também é
        # indício explícito de modalidade online, mas capacidade zero sozinha NÃO é.
        modalidade=re.sub(r'\\s+', ' ', str(r["modality"] or "").strip().casefold().replace('-', ' '))
        online=modalidade in ('online','on line','virtual','remoto','remota','ead','a distância','à distância') or bool(str(r["electronic_address"] or "").strip())
        unlimited=online and cap<=0
        result.append({"id":r["id"],"idEvento":r["event_id"],"sinopseCronograma":r["synopsis"],"data":r["date"],"hora":r["time"],"tipo":r["type"],"local":r["location"],"img":r["image"],"ministrante":r["speaker"],"vagas":r["capacity"],"sinopse":r["synopsis_activity"],"titulo":r["titulo"],"cargaHoraria":r["workload"],"modeloPreco":r["price_model"],"precoValor":r["price"],"curriculo":r["curriculum"],"ementa":r["syllabus"],"enderecoEletronico":r["electronic_address"],"horaTermino":r["end_time"],"modalidade":r["modality"],"vagasPreenchidas":filled,"vagasDisponiveis":None if unlimited else max(0,cap-filled),"vagasIlimitadas":unlimited,"vagasExibicao":"Online" if unlimited else cap,"vagasDisponiveisExibicao":"Sem limite" if unlimited else max(0,cap-filled)})
    c.close()
    return result

def buscarDadosEventoUnitario(args):
    eid=str((args or [""])[0]); c=con(); r=c.execute("select * from events where id=?",(eid,)).fetchone(); c.close()
    if not r:return None
    d={"id":r["id"],"imagem":r["image"],"nome":r["name"],"resumo":r["summary"],"periodo":r["period"],"data":r["period"],"local":r["location"],"vagas":r["capacity"],"palavraChave":r["keyword"],"status":r["status"],"sinopseCurta":r["short_synopsis"],"vagasEspecificas":r["specific_vacancies"],"enderecoEletronico":r["electronic_address"]}
    d["atividades"]=buscarCronogramaEvento([eid]); return d

def status_event(args,status):
    eid=str((args or [""])[0] if not isinstance((args or [""])[0],dict) else (args or [{}])[0].get("idEvento") or (args or [{}])[0].get("id"))
    c=con(); c.execute("update events set status=? where id=?",(status,eid)); c.commit(); c.close()
    return {"sucesso":True,"mensagem":"Status atualizado.","id":eid}

def publicarEventoPorId(args):
    eid=str((args or [""])[0]); c=con(); r=c.execute("select * from events where id=?",(eid,)).fetchone()
    if not r: c.close(); return {"sucesso":False,"mensagem":"Evento não encontrado."}
    new=event_code(c) if eid.startswith("RASC-") else eid
    if new!=eid:
        c.execute("update events set id=?,status='PUBLICADO' where id=?",(new,eid)); c.execute("update schedules set event_id=? where event_id=?",(new,eid)); c.execute("update registrations set event_id=? where event_id=?",(new,eid))
    else:c.execute("update events set status='PUBLICADO' where id=?",(eid,))
    c.commit(); c.close(); return {"sucesso":True,"mensagem":"Evento publicado.","id":new,"idEvento":new}

def excluirEventoRascunho(args):
    eid=str((args or [""])[0]); c=con(); r=c.execute("select status from events where id=?",(eid,)).fetchone()
    if not r or str(r["status"]).upper()=="PUBLICADO":c.close();return {"sucesso":False,"mensagem":"Somente rascunhos podem ser excluídos."}
    c.execute("delete from schedules where event_id=?",(eid,));c.execute("delete from events where id=?",(eid,));c.commit();c.close();return {"sucesso":True,"mensagem":"Rascunho excluído."}

def obterListaUsuariosParaSegurancaMaster(args):
    c=con();rs=c.execute("select * from users order by name").fetchall();c.close()
    return [{"id":r["id"],"nome":r["name"],"cpf":r["cpf"],"telefone":r["phone"],"email":r["email"],"tipo":r["role"],"perfil":r["role"],"idioma":r["language"],"statusAcesso":r["access_status"],"senha":""} for r in rs]

def atualizarStatusAcessoUsuarioPorAdmin(args):
    d=(args or [{}])[0] or {}; c=con(); c.execute("update users set access_status=? where id=?",(d.get("status") or d.get("statusAcesso"),d.get("id") or d.get("idUsuario")));c.commit();c.close();return {"sucesso":True,"mensagem":"Status de acesso atualizado."}

def salvarUsuarioCadastradoAdmin(args):
    d=(args or [{}])[0] or {}; c=con(); uid=d.get("id") or next_user_public_id(c,d.get("nome",""))
    old=c.execute("select * from users where id=?",(uid,)).fetchone()
    role='ADMINISTRADOR_MASTER' if uid=='EVT-00000A' else d.get("tipo","Participante")
    pwd=(old["password"] if old else password_hash(d.get("senha", "")))
    c.execute("""insert into users(id,name,cpf,phone,email,password,role,language,access_status) values(?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name,cpf=excluded.cpf,phone=excluded.phone,email=excluded.email,role=excluded.role,language=excluded.language,access_status=excluded.access_status""",
    (uid,d.get("nome",""),d.get("cpf",""),d.get("telefone",""),d.get("email",""),pwd,role,d.get("idioma","pt"),d.get("statusAcesso","Autorizado")))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Usuário salvo.","id":uid}

def redefinirSenhaUsuarioAdmin(args):
    d=(args or [{}])[0] or {}; uid=str(d.get('idUsuario') or d.get('id') or ''); nova=str(d.get('novaSenha') or ''); conf=str(d.get('confirmarSenha') or '')
    if len(nova)<4:return {"sucesso":False,"mensagem":"A senha deve ter pelo menos 4 caracteres."}
    if nova!=conf:return {"sucesso":False,"mensagem":"As senhas não coincidem."}
    c=con(); u=c.execute("select id from users where id=?",(uid,)).fetchone()
    if not u:c.close();return {"sucesso":False,"mensagem":"Usuário não encontrado."}
    c.execute("update users set password=? where id=?",(password_hash(nova),uid));c.commit();c.close();return {"sucesso":True,"mensagem":"Senha redefinida com sucesso."}

def excluirUsuarioCadastradoAdmin(args):
    uid=str((args or [""])[0]);c=con();c.execute("delete from users where id=? and role!='ADMINISTRADOR_MASTER'",(uid,));c.commit();c.close();return {"sucesso":True,"mensagem":"Usuário excluído."}

def obterConfiguracaoPixPorEvento(args):
    eid=str((args or [""])[0]);c=con();r=c.execute("select * from pix_config where event_id=?",(eid,)).fetchone();c.close()
    
    if not r:return {"event_id":eid,"chavePix":"","beneficiario":"","provedor":"","ambiente":"","prazo":20,"configurado":False}
    d=dict(r);return {**d,"chavePix":d.get("pix_key", ""),"beneficiario":d.get("receiver", ""),"provedor":d.get("provider", ""),"ambiente":d.get("environment", ""),"prazo":d.get("deadline",20),"configurado":bool(d.get("pix_key") or d.get("provider"))}

def salvarConfiguracaoPixPorEvento(args):
    d=(args or [{}])[0] or {}; eid=d.get("idEvento") or d.get("event_id") or "";c=con()
    c.execute("""insert into pix_config values(?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET pix_key=excluded.pix_key,receiver=excluded.receiver,provider=excluded.provider,environment=excluded.environment,deadline=excluded.deadline""",
    (eid,d.get("chavePix") or d.get("pix_key",""),d.get("beneficiario") or d.get("nomeRecebedor") or d.get("receiver",""),d.get("provedor") or d.get("provider",""),d.get("ambiente") or d.get("environment",""),int(d.get("prazo") or d.get("deadline") or 20)))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Configuração PIX salva."}

def inscreverNoEvento(args):
    d=(args or [{}])[0] or {}; rid="INS-"+uuid.uuid4().hex[:10].upper();c=con()
    c.execute("insert into registrations values(?,?,?,?,?,?,?,?)",(rid,d.get("idUsuario",""),d.get("email",""),d.get("idEvento",""),d.get("subAtividadeAlvo") or d.get("atividade") or "",d.get("tipo",""),"CONFIRMADO",now()));c.commit();c.close()
    return {"sucesso":True,"mensagem":"Inscrição realizada com sucesso.","idInscricao":rid}

def cancelarInscricao(args):
    d=(args or [{}])[0] or {};c=con()
    c.execute("delete from registrations where event_id=? and email=? and activity=?",(d.get("idEvento",""),d.get("email",""),d.get("subAtividadeAlvo","")));c.commit();c.close();return {"sucesso":True,"mensagem":"Inscrição cancelada."}

def enviarComprovantePagamento(args):
    d=(args or [{}])[0] or {};c=con()
    c.execute("insert into receipts(registration_id,event_id,email,activity,value,file_name,file_data,status,sent_at) values(?,?,?,?,?,?,?,?,?)",
              (d.get("idInscricao",""),d.get("idEvento",""),d.get("email",""),d.get("nomeAtividade",""),float(d.get("valor") or 0),d.get("nomeArquivo",""),d.get("base64",""),"PENDENTE",now()))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Comprovante enviado. Aguardando confirmação."}

def confirmarPagamentoEvento(args):
    d=(args or [{}])[0] if args and isinstance(args[0],dict) else {}; rid=d.get("idInscricao") or (args[0] if args else "")
    c=con();c.execute("update receipts set status='CONFIRMADO' where registration_id=?",(rid,));c.execute("update registrations set status='CONFIRMADO' where id=?",(rid,));c.commit();c.close();return {"sucesso":True,"mensagem":"Pagamento confirmado."}

def _inscricao_liberada_para_presenca_certificado(c, inscricao):
    """Regra compartilhada: atividade paga exige comprovante CONFIRMADO.

    Não altera registros. Para atividades gratuitas, preserva a inscrição.
    Se o cadastro da atividade não puder ser identificado, uma inscrição
    explicitamente PENDENTE não é liberada por engano.
    """
    eid = inscricao["event_id"]
    atividade = str(inscricao["activity"] or "").strip()
    agenda = c.execute(
        "select synopsis_activity, price_model, price from schedules where event_id=?",
        (eid,)
    ).fetchall()
    correspondentes = [a for a in agenda
                       if str(a["synopsis_activity"] or "").strip() == atividade]
    if len(correspondentes) != 1:
        return str(inscricao["status"] or "").upper() == "CONFIRMADO"
    a = correspondentes[0]
    modelo = str(a["price_model"] or "").strip().upper()
    paga = modelo in ("PAGA", "PAGO", "PAGA POR ATIVIDADE", "PAGO POR ATIVIDADE") or float(a["price"] or 0) > 0
    if not paga:
        return True
    comprovante = c.execute(
        """select 1 from receipts where registration_id=?
           and event_id=? and upper(trim(status))='CONFIRMADO' limit 1""",
        (inscricao["id"], eid)
    ).fetchone()
    return comprovante is not None


def listarParticipantesPorAtividade(args):
    eid=str((args or [""])[0]); activity=str((args+["",""])[1]); c=con()
    rs=c.execute("select r.*,u.name from registrations r left join users u on u.id=r.user_id where r.event_id=? and (?='' or r.activity=?)",(eid,activity,activity)).fetchall()
    rs=[r for r in rs if _inscricao_liberada_para_presenca_certificado(c,r)];c.close()
    out=[]
    for r in rs:
        a=c2=None
        cc=con(); a=cc.execute("select status from attendance where event_id=? and activity=? and (user_id=? or lower(email)=lower(?)) order by id desc limit 1",(eid,r["activity"],r["user_id"],r["email"])).fetchone(); cc.close()
        out.append({"idUsuario":r["user_id"],"nome":r["name"] or r["email"],"email":r["email"],"atividade":r["activity"],"status":a["status"] if a else "FALTA"})
    return sorted(out,key=lambda x:(x["nome"] or "").casefold())

def mudarStatusPresencaPorMembro(args):
    d=(args or [{}])[0] or {};c=con()
    c.execute("insert into attendance(event_id,activity,user_id,email,status) values(?,?,?,?,?)",(d.get("idEvento",""),d.get("atividade",""),d.get("idUsuario",""),d.get("email",""),d.get("status","PRESENTE")));c.commit();c.close()
    return {"sucesso":True,"mensagem":"Presença atualizada."}

def obterIdiomasAtivos(args):
    return [{"codigo":"pt","nome":"Português"},{"codigo":"en","nome":"English"},{"codigo":"es","nome":"Español"},{"codigo":"fr","nome":"Français"},{"codigo":"it","nome":"Italiano"},{"codigo":"zh","nome":"中文"}]


def buscarPerfilUsuarioPorId(args):
    uid=str((args or [""])[0]); c=con(); r=c.execute("select * from users where id=?",(uid,)).fetchone(); c.close()
    if not r:return {"sucesso":False,"mensagem":"Usuário não encontrado."}
    return {"sucesso":True,"id":r["id"],"nome":r["name"],"cpf":r["cpf"],"telefone":r["phone"],"email":r["email"],"tipo":r["role"],"idioma":r["language"],"statusAcesso":r["access_status"]}

def atualizarPerfilUsuarioPorId(args):
    d=(args or [{}])[0] or {}; uid=d.get("id") or d.get("idUsuario"); c=con()
    c.execute("""update users set name=coalesce(nullif(?,''),name),cpf=coalesce(nullif(?,''),cpf),
    phone=coalesce(nullif(?,''),phone),email=coalesce(nullif(?,''),email),
    language=coalesce(nullif(?,''),language) where id=?""",
    (d.get("nome",""),d.get("cpf",""),d.get("telefone",""),d.get("email",""),d.get("idioma",""),uid))
    c.commit(); c.close(); return {"sucesso":True,"mensagem":"Perfil atualizado com sucesso."}

def buscarInscricoesEComprovantes(args):
    email=str((args or [""])[0]); c=con()
    rs=c.execute("""select r.*,e.name event_name,rc.status receipt_status,rc.file_name,rc.value
    from registrations r left join events e on e.id=r.event_id
    left join receipts rc on rc.registration_id=r.id where lower(r.email)=lower(?) order by r.created_at desc""",(email,)).fetchall(); c.close()
    return [{"idInscricao":r["id"],"idEvento":r["event_id"],"evento":r["event_name"],"atividade":r["activity"],
             "status":r["status"],"statusPagamento":r["receipt_status"] or "","comprovante":r["file_name"] or "",
             "valor":r["value"] or 0} for r in rs]

def buscarCertificadosAluno(args):
    email=str((args or [""])[0]); uid=str((args+["",""])[1]); c=con()
    rs=c.execute("""select c.*,e.name event_name from certificates c left join events e on e.id=c.event_id
    where (lower(c.email)=lower(?) and ?<>'') or (c.user_id=? and ?<>'') order by c.created_at desc""",
    (email,email,uid,uid)).fetchall(); c.close()
    return [{"id":r["id"],"idEvento":r["event_id"],"evento":r["event_name"],"atividade":r["activity"],
             "status":r["status"],"codigo":r["validation_code"],"url":r["url"],"urlPdf":r["file_url"],
             "tipoAssinatura":r["signature_type"],"idioma":r["language"]} for r in rs]

def obterFinanceiroPorEvento(args):
    eid=str((args or [""])[0]); c=con()
    pending=c.execute("""select rc.*,u.name from receipts rc left join registrations r on r.id=rc.registration_id left join users u on u.id=r.user_id where rc.event_id=? and upper(rc.status)='PENDENTE'""",(eid,)).fetchall()
    paid=c.execute("""select rc.*,u.name from receipts rc left join registrations r on r.id=rc.registration_id left join users u on u.id=r.user_id where rc.event_id=? and upper(rc.status)='CONFIRMADO'""",(eid,)).fetchall()
    atvs=c.execute("select * from schedules where event_id=? order by date,time,id",(eid,)).fetchall()
    regs=c.execute("select * from registrations where event_id=?",(eid,)).fetchall(); c.close()
    conv=lambda r:{"idInscricao":r["registration_id"],"nome":r["name"] or r["email"],"email":r["email"],"atividade":r["activity"],"valor":r["value"],"nomeArquivo":r["file_name"],"comprovante":r["file_data"] or "","status":r["status"],"dataEnvio":r["sent_at"],"valorPago":r["value"],"data":r["sent_at"]}
    total=sum(float(x["value"] or 0) for x in paid)
    linhas=[]; total_gratis=0; total_pagos=0
    for a in atvs:
        nome=(a["synopsis_activity"] or a["type"] or "Atividade")
        modelo=str(a["price_model"] or "").lower().replace("á","a")
        regs_atv=[r for r in regs if str(r["activity"] or "").strip()==str(nome).strip()]
        if modelo in ("gratis","gratuito","free"):
            qtd_gratis=len(regs_atv); qtd_pagos=0
        else:
            qtd_gratis=0
            emails_confirmados={str(x["email"] or "").lower().strip() for x in paid if str(x["activity"] or "").strip()==str(nome).strip()}
            ids_confirmados={str(x["registration_id"] or "") for x in paid if str(x["activity"] or "").strip()==str(nome).strip()}
            qtd_pagos=sum(1 for r in regs_atv if str(r["id"] or "") in ids_confirmados or str(r["email"] or "").lower().strip() in emails_confirmados)
        total_gratis+=1 if modelo in ("gratis","gratuito","free") else 0; total_pagos+=0 if modelo in ("gratis","gratuito","free") else 1
        linhas.append({"atividade":nome,"gratis":qtd_gratis,"pagos":qtd_pagos})
    return {"sucesso":True,"resumo":{"gratuitos":total_gratis,"pagos":total_pagos,"valorRecebido":total},"balancoAtividades":linhas,"pendentes":[conv(x) for x in pending],"pagamentosEfetuados":[conv(x) for x in paid],"totalRecebido":total}

def obterEstatisticasEvento(args):
    eid=str((args or [""])[0]); c=con(); ev=c.execute("select * from events where id=?",(eid,)).fetchone()
    if not ev:c.close();return {"sucesso":False,"mensagem":"Evento não encontrado."}
    regs=c.execute("select * from registrations where event_id=?",(eid,)).fetchall(); atvs=c.execute("select * from schedules where event_id=?",(eid,)).fetchall()
    att=c.execute("select * from attendance where event_id=?",(eid,)).fetchall(); certs=c.execute("select * from certificates where event_id=?",(eid,)).fetchall(); pays=c.execute("select * from payments where event_id=?",(eid,)).fetchall(); rec=c.execute("select * from receipts where event_id=?",(eid,)).fetchall(); usuarios=c.execute("select id,email,language from users").fetchall(); c.close()
    uniq=len(set((r["user_id"] or r["email"]) for r in regs)); presentes=sum(1 for x in att if str(x['status'] or '').upper() in ('PRESENTE','PRESENCA','PRESENÇA')); confirmados=[x for x in pays if str(x['status'] or '').upper() in ('CONFIRMADO','PAGO','PAID')]; total=sum(float(x['total'] or 0) for x in confirmados)+sum(float(x['value'] or 0) for x in rec if str(x['status'] or '').upper()=='CONFIRMADO')
    resumo={"inscritos":uniq,"inscricoes":len(regs),"atividades":len(atvs),"vagas":sum(int(a['capacity'] or 0) for a in atvs),"presencas":presentes,"ausencias":max(0,len(regs)-presentes),"certificados":len(certs),"pagamentos":len(confirmados)+sum(1 for x in rec if str(x["status"] or "").upper()=="CONFIRMADO"),"totalRecebido":total}
    ga=[]
    for a in atvs:
        nome_atividade=a['synopsis_activity'] or a['type'] or 'Atividade'
        inscritos_atividade=[r for r in regs if str(r['activity'] or '').strip()==str(nome_atividade).strip()]
        # O último registro de presença de cada pessoa/atividade prevalece.
        ultimos={}
        for t in att:
            if str(t['activity'] or '').strip()!=str(nome_atividade).strip(): continue
            chave=(str(t['user_id'] or '').strip() or str(t['email'] or '').strip().lower())
            if chave: ultimos[chave]=str(t['status'] or '').strip().upper()
        presencas_atividade=0; ausencias_atividade=0
        for r in inscritos_atividade:
            chave=str(r['user_id'] or '').strip() or str(r['email'] or '').strip().lower()
            estado=ultimos.get(chave, '')
            if estado in ('PRESENTE','PRESENCA','PRESENÇA'): presencas_atividade+=1
            elif estado in ('AUSENTE','AUSENCIA','AUSÊNCIA'): ausencias_atividade+=1
        n=len(inscritos_atividade); cap=int(a['capacity'] or 0)
        ga.append({"atividade":nome_atividade,"inscritos":n,"vagas":cap,"presencas":presencas_atividade,"ausencias":ausencias_atividade,"semLimite":str(a["modality"] or "").strip().lower() in ("online","on-line","virtual"),"ocupacao":round((n/cap*100) if cap else 0,1)})
    # Contagem de pessoas distintas por idioma no evento (não por inscrições).
    idiomas_codigos=("pt","en","es","fr","it","zh")
    idiomas_contagem={codigo:set() for codigo in idiomas_codigos}
    por_id={str(u["id"]):u for u in usuarios}
    por_email={str(u["email"] or "").strip().lower():u for u in usuarios}
    for r in regs:
        uid=str(r["user_id"] or "").strip()
        email=str(r["email"] or "").strip().lower()
        u=por_id.get(uid) or por_email.get(email)
        lingua=str(u["language"] or "pt").strip().lower().replace("_","-").split("-")[0] if u else "pt"
        if lingua not in idiomas_contagem: lingua="pt"
        identidade=uid or email
        if identidade: idiomas_contagem[lingua].add(str(u["id"]) if u else identidade)
    idiomas=[{"codigo":codigo,"valor":len(idiomas_contagem[codigo])} for codigo in idiomas_codigos]
    gerados=sum(1 for x in certs if str(x["status"] or "").upper() in ("GERADO","ENVIADO"))
    enviados=sum(1 for x in certs if str(x["status"] or "").upper()=="ENVIADO")
    erros=sum(1 for x in certs if str(x["status"] or "").upper() in ("ERRO","ERROS","ERROR","FALHA","FALHOU"))
    return {"sucesso":True,"evento":{"id":ev['id'],"nome":ev['name'],"status":ev['status']},"resumo":resumo,"graficos":{"presenca":[{"label":"Presenças","valor":presentes},{"label":"Ausências","valor":max(0,len(regs)-presentes)}],"pagamento":[{"label":"Gratuitas","valor":sum(1 for a in atvs if str(a["price_model"] or "").strip().lower() in ("gratis","grátis","gratuito","free"))},{"label":"Pagas","valor":sum(1 for a in atvs if str(a["price_model"] or "").strip().lower() not in ("gratis","grátis","gratuito","free"))}],"certificados":[{"label":"Gerados, não enviados","valor":sum(1 for x in certs if str(x["status"] or "").upper()=="GERADO")},{"label":"Enviados","valor":sum(1 for x in certs if str(x["status"] or "").upper()=="ENVIADO")}],"atividades":ga,"idiomas":idiomas,"certificados_colunas":[{"label":"Inscrições em atividades","valor":len(regs)},{"label":"Certificados gerados","valor":gerados},{"label":"Certificados enviados","valor":enviados},{"label":"Certificados com erros","valor":erros}]}}

def obterConfiguracaoCertificadoPorEvento(args):
    """Fonte única de assunto/mensagem por evento para ambas as interfaces."""
    eid=str((args or [""])[0]).strip()
    if not eid:
        return {"sucesso":False,"mensagem":"Selecione um evento."}
    c=con()
    try:
        r=c.execute("select v from settings where k=?",(f"certcfg:{eid}",)).fetchone()
    finally:
        c.close()
    try:
        data=json.loads(r["v"]) if r else {}
    except (ValueError,TypeError):
        data={}
    if not isinstance(data,dict): data={}
    return {"idEvento":eid,"tipoAssinatura":"AUTOMATICA","assunto":"","mensagem":"",**data,"sucesso":True}

def salvarConfiguracaoCertificadoEvento(args):
    """Atualiza apenas campos enviados; nunca apaga o texto ao salvar modelo/assinatura."""
    d=dict((args or [{}])[0] or {})
    eid=str(d.get("idEvento") or "").strip()
    if not eid:
        return {"sucesso":False,"mensagem":"Selecione um evento."}
    d.pop("modeloId",None)
    d.pop("modeloNome",None)
    c=con()
    try:
        row=c.execute("select v from settings where k=?",(f"certcfg:{eid}",)).fetchone()
        try: old=json.loads(row["v"]) if row else {}
        except (ValueError,TypeError): old={}
        if not isinstance(old,dict): old={}
        # Compatibilidade com campos antigos usados no painel administrativo.
        if "assunto" not in d and "assuntoEmail" in d: d["assunto"]=d["assuntoEmail"]
        if "mensagem" not in d and "mensagemEmail" in d: d["mensagem"]=d["mensagemEmail"]
        old.update(d)
        old["idEvento"]=eid
        c.execute("insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v",(f"certcfg:{eid}",json.dumps(old,ensure_ascii=False)))
        c.commit()
    finally:
        c.close()
    return {"sucesso":True,"mensagem":"Configuração de e-mail e certificado salva para o evento."}

def obterPainelCertificadosPorEvento(args):
    """Contrato da Central administrativa: evento, resumo e participantes.

    Consulta somente os registros existentes; não altera presença ou certificados.
    """
    eid=str((args or [""])[0]).strip()
    c=con()
    try:
        ev=c.execute("select id,name,status from events where id=?",(eid,)).fetchone()
        if not ev:
            return {"sucesso":False,"mensagem":"Evento não encontrado.","participantes":[]}
        rs=c.execute("""select r.id rid,r.user_id,r.email,r.activity,u.name,
          (select status from attendance a where a.event_id=r.event_id and a.activity=r.activity
           and (a.user_id=r.user_id or lower(a.email)=lower(r.email))
           order by a.id desc limit 1) presence,
          cert.id cid,cert.status cstatus,cert.validation_code,cert.url,cert.file_url,cert.signature_type
          from registrations r left join users u on u.id=r.user_id
          left join certificates cert on cert.id=(select c2.id from certificates c2
            where c2.event_id=r.event_id and c2.activity=r.activity
            and (c2.user_id=r.user_id or lower(c2.email)=lower(r.email))
            order by c2.created_at desc limit 1)
          where r.event_id=? order by u.name,r.email,r.activity""",(eid,)).fetchall()
    finally:
        c.close()
    # A mesma regra de liberação da lista de presença vale para certificados.
    c=con()
    try:
        liberados={r["id"] for r in c.execute(
            "select * from registrations where event_id=?", (eid,)
        ).fetchall() if _inscricao_liberada_para_presenca_certificado(c,r)}
    finally:
        c.close()
    participantes=[]
    for r in rs:
        if r["rid"] not in liberados:
            continue
        pres=str(r['presence'] or '').strip().upper()
        elegivel=pres in ('PRESENTE','PRESENÇA','PRESENCA','CONFIRMADO','CONFIRMADA')
        gerado=bool(r['cid'])
        status=str(r['cstatus'] or 'PENDENTE').upper()
        participantes.append({
            'idInscricao':r['rid'],'idUsuario':r['user_id'],
            'nomeAluno':r['name'] or r['email'] or 'Participante',
            'emailAluno':r['email'] or '', 'atividade':r['activity'] or '',
            'categoria':'Participante','presenca':pres,'elegivelCertificado':elegivel,
            'possuiCertificado':gerado,'idCertificado':r['cid'] or '',
            'tipoAssinatura':r['signature_type'] or 'PENDENTE',
            'statusCertificado':status,'statusEnvio':'ENVIADO' if status=='ENVIADO' else 'PENDENTE',
            'urlPdf':r['file_url'] or '', 'url':r['url'] or '',
            'codigo':r['validation_code'] or '',
            'publicadoPortal':'SIM' if gerado and r['file_url'] else 'NÃO',
            'qrCodeUrl':r['url'] or ''
        })
    # A tabela settings guarda apenas metadados de entrega, não senhas SMTP.
    c=con()
    try:
        delivery_status={}
        signed_ids=set()
        for signed in c.execute("select k,v from settings where k like 'cert_signed:%'"):
            if signed['v']=='1':signed_ids.add(signed['k'].split(':',1)[1])
        for row in c.execute("select k,v from settings where k like 'cert_delivery:%'"):
            try: delivery_status[row['k'].split(':',1)[1]]=json.loads(row['v']).get('status','')
            except (ValueError,TypeError): pass
    finally:c.close()
    total=len(participantes)
    presentes=sum(bool(x['elegivelCertificado']) for x in participantes)
    gerados=sum(bool(x['possuiCertificado']) for x in participantes)
    enviados=sum(x['statusEnvio']=='ENVIADO' for x in participantes)
    resumo={'totalInscritos':total,'presencaConfirmada':presentes,
      'elegiveisCertificado':presentes,'certificadosGerados':gerados,
      'aguardandoAssinatura':sum(
          x['elegivelCertificado'] and not (
              x['idCertificado'] in signed_ids or (x['possuiCertificado'] and x['tipoAssinatura'].strip().upper() in ('AUTOMATICA','AUTOMÁTICA')
              and x['urlPdf'])
          ) for x in participantes),
      'enviados':enviados,'errosEnvio':sum(1 for x in participantes if x['idCertificado'] and delivery_status.get(x['idCertificado'])=='ERRO')}
    return {'sucesso':True,'evento':{'id':ev['id'],'nome':ev['name'],'status':ev['status']},
      'resumo':resumo,'participantes':participantes,'avisosCertificados':[]}

def processarEntradaQRCodeMembro(args):
    rid=str((args or [""])[0]); c=con(); r=c.execute("select * from registrations where id=?",(rid,)).fetchone()
    if not r:c.close();return {"sucesso":False,"mensagem":"Inscrição não encontrada."}
    c.execute("insert into attendance(event_id,activity,user_id,email,status) values(?,?,?,?,?)",(r["event_id"],r["activity"],r["user_id"],r["email"],"PRESENTE"))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Presença registrada.","idInscricao":rid}

def obterListaCertificadosParaAuditoria(args):
    c=con();rs=c.execute("""select c.*,u.name,e.name event_name from certificates c left join users u on u.id=c.user_id left join events e on e.id=c.event_id order by c.created_at desc""").fetchall();c.close()
    return [{"id":r["id"],"nome":r["name"] or r["email"],"email":r["email"],"evento":r["event_name"],"atividade":r["activity"],"status":r["status"],"codigo":r["validation_code"],"url":r["url"],"urlPdf":r["file_url"]} for r in rs]

def atualizarDocumentoAssinado(args):
    d=(args or [{}])[0] or {}; cid=d.get("idCertificado") or d.get("id"); url=d.get("url") or d.get("urlPdf") or ""
    c=con();c.execute("update certificates set file_url=?,status=CASE WHEN status='ENVIADO' THEN 'ENVIADO' ELSE 'GERADO' END where id=?",(url,cid))
    if cid and url:
        c.execute("insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v",('cert_signed:'+str(cid),'1'))
    c.commit();c.close()
    return {"sucesso":True,"mensagem":"Documento assinado atualizado."}

def mudarStatusPublicacaoEventoCompat(args):
    # O HTML antigo pode chamar com (idEvento, status) ou objeto.
    if args and isinstance(args[0],dict):
        d=args[0]; eid=d.get("idEvento") or d.get("id"); st=d.get("status") or "PUBLICADO"
    else:
        eid=str((args or [""])[0]); st=str((args+["","PUBLICADO"])[1] or "PUBLICADO")
    return status_event([eid],st)


# Compatibilidade: funções ainda não portadas integralmente retornam estruturas neutras
# para manter a interface navegável durante a conversão direta.
# Armazenamento persistente: configure FOREVENTO_MODELOS_DIR no host.
# Modelos legados da raiz são importados sem mover ou apagar os originais.
def _modelos_dir():
    import os
    path=Path(os.environ.get("FOREVENTO_MODELOS_DIR") or str(BASE/"modelos_cert")).expanduser().resolve()
    path.mkdir(parents=True,exist_ok=True)
    return path

def _modelo_meta(nome):
    m=re.match(r"^([A-Za-z]{2})_.+_([am])\.(pptx|pdf|png|jpg|jpeg)$",nome,re.I)
    return (m.group(1).lower(),"AUTOMATICA" if m.group(2).lower()=="a" else "MANUAL") if m else None

def _sincronizar_modelos():
    import shutil
    pasta=_modelos_dir(); legado=BASE/"modelo_cert"
    if legado.is_dir() and legado.resolve()!=pasta:
        for origem in legado.iterdir():
            if origem.is_file() and _modelo_meta(origem.name) and not (pasta/origem.name).exists():
                shutil.copy2(origem,pasta/origem.name)
    c=con()
    for arquivo in pasta.iterdir():
        if not arquivo.is_file():continue
        meta=_modelo_meta(arquivo.name)
        if not meta:continue
        existing=c.execute("select id from certificate_models where filename=?",(arquivo.name,)).fetchone()
        if existing:
            c.execute("update certificate_models set file_path=?,language=?,signature_type=? where id=?",(str(arquivo),*meta,existing['id']))
        else:
            c.execute("insert into certificate_models(event_id,filename,language,signature_type,file_path,created_at) values('',?,?,?,?,?)",(arquivo.name,*meta,str(arquivo),now()))
    c.commit();c.close()

def listarModelosCertificados(args):
    _sincronizar_modelos()
    c=con();rs=c.execute("select * from certificate_models order by language,signature_type,filename").fetchall();c.close()
    return [dict(r) for r in rs if Path(r['file_path']).is_file() and Path(r['file_path']).suffix.lower() in ('.pdf','.pptx')]

def _miniatura_certificado(path):
    """Prévia visual opcional; nenhuma modificação no arquivo original."""
    import base64, io, shutil, subprocess, tempfile
    from PIL import Image
    p=Path(path)
    try:
        if p.suffix.lower() in ('.png','.jpg','.jpeg'):
            with Image.open(p) as im:
                im.thumbnail((900,550))
                out=io.BytesIO();im.convert('RGB').save(out,format='PNG')
                return base64.b64encode(out.getvalue()).decode(), 'image/png'
        pdf=p
        if p.suffix.lower()=='.pptx':
            exe=shutil.which('libreoffice') or shutil.which('soffice')
            if not exe:return '', ''
            with tempfile.TemporaryDirectory() as td:
                subprocess.run([exe,'-env:UserInstallation=file://'+td+'/lo_profile',
                    '--headless','--convert-to','pdf','--outdir',td,str(p)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35,check=True)
                pdf=Path(td)/(p.stem+'.pdf')
                if not pdf.is_file():return '', ''
                import fitz
                doc=fitz.open(str(pdf))
                data=doc[0].get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False).tobytes('png')
                doc.close()
                return base64.b64encode(data).decode(),'image/png'
        if pdf.suffix.lower()=='.pdf':
            import fitz
            doc=fitz.open(str(pdf))
            data=doc[0].get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False).tobytes('png')
            doc.close()
            return base64.b64encode(data).decode(),'image/png'
    except Exception:
        pass
    return '', ''

def obterModelosCertificadosDrive(args):
    # Nome legado mantido apenas para compatibilidade de chamadas antigas; não consulta o Drive.
    modelos=listarModelosCertificados([])
    itens=[]
    for m in modelos:
        preview,mime=_miniatura_certificado(m['file_path'])
        itens.append({"id":str(m['id']),"nome":m['filename'],"codigoIdioma":m['language'],
            "tipoAssinatura":m['signature_type'],"previewBase64":preview,"previewMimeType":mime or "image/png"})
    return {"modelos":itens}

def obterTagsModeloCertificado(args):
    import zipfile,xml.etree.ElementTree as ET
    ident=str((args or [''])[0]); modelos=listarModelosCertificados([])
    m=next((x for x in modelos if str(x['id'])==ident),None)
    if not m:return {"tags":[],"mensagem":"Modelo não encontrado."}
    path=Path(m['file_path']); content=''
    if path.suffix.lower()=='.pptx':
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if re.match(r'ppt/slides/slide\d+\.xml$',name):
                    root=ET.fromstring(z.read(name));content+=' '.join((e.text or '') for e in root.iter() if e.tag.endswith('}t'))+' '
    elif path.suffix.lower()=='.pdf':
        try:
            from pypdf import PdfReader
            content=' '.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
        except ImportError:pass
    tags=list(dict.fromkeys(re.findall(r'<<\s*([^<>]+?)\s*>>|{{\s*([^{}]+?)\s*}}',content)))
    return {"tags":[(a or b).strip() for a,b in tags],"mensagem":"Tags lidas do arquivo armazenado no servidor."}

def salvarModeloCertificado(args):
    import base64,binascii
    d=(args or [{}])[0] or {};nome=Path(str(d.get('nomeArquivo') or '')).name
    meta=_modelo_meta(nome)
    if not meta or Path(nome).suffix.lower() not in ('.pdf','.pptx'):
        return {"sucesso":False,"mensagem":"Cadastre PDF ou PPTX com nome pt_nome_a.pdf ou pt_nome_a.pptx (sufixo _m para manual)."}
    raw=str(d.get('base64') or '').split(',',1)[-1]
    try:data=base64.b64decode(raw,validate=True)
    except (ValueError,binascii.Error):return {"sucesso":False,"mensagem":"Arquivo inválido."}
    if not data or len(data)>20*1024*1024:return {"sucesso":False,"mensagem":"Arquivo vazio ou maior que 20 MB."}
    _sincronizar_modelos()
    c=con()
    clash=c.execute("select filename from certificate_models where lower(language)=? and signature_type=?",meta).fetchone()
    c.close()
    if clash:return {"sucesso":False,"mensagem":"Já existe modelo para esse idioma e assinatura: "+clash['filename']+". Use Substituir na tabela."}
    pasta=_modelos_dir();path=pasta/nome
    if path.exists():return {"sucesso":False,"mensagem":"Já existe um modelo com esse nome. Exclua o anterior apenas se não estiver vinculado a eventos."}
    path.write_bytes(data)
    _sincronizar_modelos()
    return {"sucesso":True,"mensagem":"Modelo cadastrado no armazenamento do servidor.","arquivo":nome}

def substituirModeloCertificado(args):
    import base64,binascii,os,tempfile
    d=(args or [{}])[0] or {}
    try: mid=int(d.get('id'))
    except (ValueError,TypeError):return {'sucesso':False,'mensagem':'Modelo inválido.'}
    nome=Path(str(d.get('nomeArquivo') or '')).name
    meta=_modelo_meta(nome)
    if not meta or Path(nome).suffix.lower() not in ('.pdf','.pptx'):
        return {'sucesso':False,'mensagem':'Para substituir, selecione PDF ou PPTX com idioma e sufixo _a ou _m.'}
    try: data=base64.b64decode(str(d.get('base64') or '').split(',',1)[-1],validate=True)
    except (ValueError,binascii.Error):return {'sucesso':False,'mensagem':'Arquivo inválido.'}
    if not data or len(data)>20*1024*1024:return {'sucesso':False,'mensagem':'Arquivo vazio ou maior que 20 MB.'}
    c=con()
    try:
        row=c.execute('select * from certificate_models where id=?',(mid,)).fetchone()
        if not row:return {'sucesso':False,'mensagem':'Modelo não encontrado.'}
        # Substituição mantém a mesma identidade de idioma e assinatura.
        if meta!=(row['language'],row['signature_type']):
            return {'sucesso':False,'mensagem':'Para substituir, mantenha o mesmo idioma e tipo de assinatura.'}
        pasta=_modelos_dir()
        old=Path(row['file_path']).resolve();target=(pasta/nome).resolve()
        if old.parent!=pasta or target.parent!=pasta:return {'sucesso':False,'mensagem':'Caminho não permitido.'}
        if target!=old and target.exists():return {'sucesso':False,'mensagem':'Já existe outro arquivo com esse nome.'}
        # Gravação atômica do novo arquivo. O antigo é preservado se a gravação falhar.
        fd,tmp=tempfile.mkstemp(prefix='.cert_model_',dir=pasta)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        c.execute('update certificate_models set filename=?,file_path=? where id=?',(nome,str(target),mid))
        c.commit()
        # Preservar arquivo anterior: não remover modelos legados automaticamente.
        return {'sucesso':True,'mensagem':'Modelo substituído. Certificados já emitidos foram preservados.'}
    finally:c.close()

def excluirModeloCertificado(args):
    try:mid=int((args or [0])[0])
    except (ValueError,TypeError):return {"sucesso":False,"mensagem":"Identificador inválido."}
    c=con();r=c.execute("select * from certificate_models where id=?",(mid,)).fetchone()
    if not r:c.close();return {"sucesso":False,"mensagem":"Modelo não encontrado."}
    path=Path(r['file_path'])
    if path.resolve().parent!=_modelos_dir():c.close();return {"sucesso":False,"mensagem":"Arquivo fora da pasta gerenciada; exclusão bloqueada."}
    try:path.unlink(missing_ok=True)
    except OSError as exc:c.close();return {"sucesso":False,"mensagem":str(exc)}
    c.execute("delete from certificate_models where id=?",(mid,));c.commit();c.close()
    return {"sucesso":True,"mensagem":"Modelo excluído."}

def validarCredencialForEventoPublica(args):
    code=str((args or [''])[0] or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9_-]{5,100}',code):
        return {'sucesso':False,'mensagem':'Código inválido.'}
    c=con()
    try:
        r=c.execute("""select cert.validation_code,cert.status,cert.created_at,
           cert.activity,cert.event_id,ev.name evento,u.name nome
           from certificates cert left join events ev on ev.id=cert.event_id
           left join users u on u.id=cert.user_id
           where upper(cert.validation_code)=? limit 1""",(code,)).fetchone()
        if not r or str(r['status']).upper() not in ('GERADO','ENVIADO'):
            return {'sucesso':False,'mensagem':'Credencial não localizada.'}
        titulo=titulo_atividade_para_exibicao(c,r['event_id'],r['activity'])
        atv=c.execute("""select workload from schedules where event_id=?
            and (titulo=? or synopsis_activity=? or synopsis=?) order by id limit 1""",
            (r['event_id'],titulo,r['activity'],r['activity'])).fetchone()
        return {'sucesso':True,'certificado':{'codigo':r['validation_code'],
          'nome':r['nome'] or '', 'evento':r['evento'] or '',
          'atividade':titulo or r['activity'] or '', 'data':r['created_at'] or '',
          'cargaHoraria':(atv['workload'] if atv else '') or ''}}
    finally:c.close()

def neutral(name,args):
    if name.startswith(("obter","buscar","listar")): return []
    if name.startswith(("salvar","atualizar","configurar","registrar","publicar","gerar","enviar","deletar","excluir","arquivar","cancelar","mudar","processar")):
        return {"sucesso":False,"mensagem":"Função do Apps Script preservada no inventário, mas ainda exige adaptação do serviço externo (Drive/Sheets/Email/PDF): "+name}
    return None


def obterVitrineEventos(args): return listarEventos(["publico"])

def obterCronogramaPublico(args):
    eid=str((args or [""])[0]); dados=buscarCronogramaEvento([eid]); c=con()
    out=[]
    for a in dados:
        n=c.execute("select count(*) n from registrations where event_id=? and activity=? and upper(status)='CONFIRMADO'",(eid,a.get("sinopse") or a.get("ministrante") or "")).fetchone()["n"]
        a["inscritos"]=n; a["vagasDisponiveis"]=max(0,int(a.get("vagas") or 0)-n); out.append(a)
    c.close(); return out

def gerarDocumentoPdfPresencaNativo(args):
    meta=(args or [{}])[0] or {}; eid=meta.get("idEvento",""); atividade=meta.get("atividade","")
    c=con(); ev=c.execute("select name from events where id=?",(eid,)).fetchone()
    rs=c.execute("""select r.email,u.name,a.status from registrations r left join users u on u.id=r.user_id
      left join attendance a on a.event_id=r.event_id and a.activity=r.activity and (a.user_id=r.user_id or lower(a.email)=lower(r.email))
      where r.event_id=? and (?='' or r.activity=?) order by u.name,r.email""",(eid,atividade,atividade)).fetchall();c.close()
    # HTML imprimível preserva a função de lista e permite "Salvar como PDF" sem dependência Google.
    rows="".join(f"<tr><td>{x['name'] or x['email']}</td><td>{x['email']}</td><td>{x['status'] or ''}</td><td>________________</td></tr>" for x in rs)
    html="<!doctype html><meta charset='utf-8'><title>Lista de presença</title><style>body{font-family:Arial;margin:30px}table{width:100%;border-collapse:collapse}td,th{border:1px solid #999;padding:8px}</style><h2>"+str(ev["name"] if ev else eid)+"</h2><h3>"+str(atividade)+"</h3><table><tr><th>Nome</th><th>E-mail</th><th>Presença</th><th>Assinatura</th></tr>"+rows+"</table><script>window.print()</script>"
    return {"sucesso":True,"html":html,"nomeArquivo":f"lista_presenca_{eid}.html"}

def obterPagamentosAuditoria(args):
    d=(args or [{}])[0] or {}; eid=d.get("idEvento",""); nome=d.get("nome","").lower(); c=con()
    q="""select p.*,u.name from payments p left join users u on u.id=p.user_id where upper(p.status)='PAGO'"""
    par=[]
    if eid:q+=" and p.event_id=?";par.append(eid)
    if nome:q+=" and lower(coalesce(u.name,'')) like ?";par.append("%"+nome+"%")
    rs=c.execute(q+" order by p.paid_at desc",par).fetchall();c.close()
    return [{"id":r["id"],"evento":r["event_id"],"nome":r["name"],"pagamento":r["txid"] or r["proof_name"],"data":r["paid_at"],"valor":r["total"],"metodo":r["method"]} for r in rs]

def obterFichaReembolso(args):
    """Consulta legada: comprovantes confirmados, sem depender de payments."""
    d=(args or [{}])[0] or {};eid=str(d.get("idEvento") or "");nome=str(d.get("nome") or "").strip()
    if not eid:return []
    c=con()
    try:
        rs=c.execute("""select rc.id,rc.registration_id,rc.event_id,rc.email,rc.activity,
          rc.value,rc.file_name,rc.sent_at,r.user_id,u.name,
          (select a.status from attendance a where a.event_id=rc.event_id
           and a.activity=rc.activity and (a.user_id=r.user_id or lower(a.email)=lower(rc.email))
           order by a.id desc limit 1) presence,
          (select count(*) from refunds rf where rf.payment_id='REC:'||rc.id) refund_count
          from receipts rc left join registrations r on r.id=rc.registration_id
          left join users u on u.id=r.user_id
          where rc.event_id=? and upper(trim(rc.status))='CONFIRMADO'
          and (lower(coalesce(u.name,'')) like ? or lower(coalesce(rc.email,'')) like ?)
          order by rc.id desc""",(eid,'%'+nome.lower()+'%','%'+nome.lower()+'%')).fetchall()
        result=[]
        for r in rs:
            present=str(r['presence'] or '').strip().upper() in ('PRESENTE','PRESENÇA','PRESENCA','CONFIRMADO','CONFIRMADA')
            result.append({'idPagamento':'REC:'+str(r['id']),'idUsuario':r['user_id'] or '',
              'idEvento':r['event_id'],'nome':r['name'] or r['email'],
              'atividade':r['activity'],'valor':float(r['value'] or 0),
              'comprovante':r['file_name'] or '', 'temComprovante':bool(r['file_name']),
              'presenca':r['presence'] or 'SEM REGISTRO',
              'reembolsado':bool(r['refund_count']),
              'podeReembolsar':not present and not bool(r['refund_count'])})
        return result
    finally:c.close()

def registrarReembolso(args):
    d=(args or [{}])[0] or {}
    if d.get("presenca"): return {"sucesso":False,"mensagem":"Reembolso bloqueado: há presença registrada na atividade."}
    c=con(); rid="REB-"+uuid.uuid4().hex[:10].upper()
    c.execute("insert into refunds values(?,?,?,?,?,?,?,?,?,?)",(rid,d.get("idPagamento",""),d.get("idUsuario",""),d.get("idEvento",""),d.get("atividade",""),float(d.get("valor") or 0),d.get("nomeArquivo",""),d.get("base64",""),d.get("observacao",""),now()))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Reembolso registrado.","id":rid}

def permission_catalog():
    return [
      ("eventos_visualizar","Eventos — visualizar","Consultar eventos autorizados."),("eventos_editar","Eventos — criar/alterar","Criar e alterar eventos."),("eventos_publicar","Eventos — publicar/arquivar/cancelar","Alterar o estado do evento."),
      ("cronograma_visualizar","Cronograma/Lista — visualizar","Consultar atividades e inscritos."),("presenca_lancar","Cronograma/Lista — lançar presença","Marcar ou desmarcar presença dos inscritos."),("lista_pdf","Cronograma/Lista — gerar lista PDF","Gerar lista de presença da atividade."),
      ("financeiro_visualizar","Financeiro — visualizar","Consultar informações financeiras autorizadas."),("financeiro_config_pix","Financeiro — configurar PIX","Alterar configuração PIX do evento."),("financeiro_auditoria","Financeiro — consulta/auditoria","Consultar pagamentos e auditoria."),("financeiro_reembolso","Financeiro — reembolso","Registrar procedimentos de reembolso."),
      ("cert_consultar","Certificados — consultar","Consultar situação PENDENTE, GERADO e ENVIADO."),("cert_visualizar","Certificados — visualizar PDF","Abrir certificado já confeccionado."),("cert_gerar","Certificados — gerar","Gerar certificados de participantes elegíveis."),("cert_enviar","Certificados — enviar","Enviar/publicar certificado."),("cert_excluir","Certificados — excluir/regenerar","Excluir geração para permitir nova emissão."),("cert_configurar","Certificados — configurar","Configurar modelo, assinatura e mensagem do evento."),
      ("relatorios_visualizar","Relatórios — visualizar","Consultar relatórios autorizados."),("usuarios_visualizar","Usuários — visualizar","Consultar usuários cadastrados."),("usuarios_editar","Usuários — editar","Alterar dados, categoria e atendimento autorizado."),("usuarios_bloquear","Usuários — bloquear/reativar","Bloquear e reativar contas sem apagar histórico."),
      ("config_backup_restauracao","Configurar — backup e restauração","Administrar cópias e pontos de restauração."),("config_aparencia","Configurar — aparência","Alterar cores e aparência geral."),("config_permissoes","Configurar — permissões","Alterar permissões gerais ou individuais."),("permissoes","Permissões","Acessar e configurar permissões gerais e individuais."),("perfil","Meu Perfil","Acessar e alterar os próprios dados e trocar a própria senha."),("vitrine","Vitrine","Cadastrar, editar e publicar banners/posts da página inicial.")]

def obterPermissoes(args):
    roles=["EQUIPE_ADMINISTRATIVA","COORDENADOR","MINISTRANTE","MONITOR_EXTENSIONISTA"]
    cat=permission_catalog(); c=con(); out={}
    for role in roles:
        rows=c.execute("select permission,enabled from role_permissions where role=?",(role,)).fetchall(); m={x["permission"]:bool(x["enabled"]) for x in rows}
        out[role]={p:m.get(p,False) for p,_,_ in cat}
    c.close(); return {"roles":out,"catalogo":[{"id":p,"nome":n,"descricao":d} for p,n,d in cat]}

def salvarPermissoes(args):
    d=(args or [{}])[0] or {}; roles=d.get("roles",d); c=con()
    allowed={"EQUIPE_ADMINISTRATIVA","COORDENADOR","MINISTRANTE","MONITOR_EXTENSIONISTA"}
    for role,perms in roles.items():
        if role not in allowed: continue
        for perm,val in perms.items():
            if role in {"MINISTRANTE","MONITOR_EXTENSIONISTA"} and perm.startswith("usuarios_"): val=False
            c.execute("insert into role_permissions(role,permission,enabled) values(?,?,?) on conflict(role,permission) do update set enabled=excluded.enabled",(role,perm,1 if val else 0))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Permissões gerais salvas."}

def obterPermissoesIndividuais(args):
    uid=str((args or [""])[0]).strip(); c=con(); u=c.execute("select id,name,role from users where id=?",(uid,)).fetchone()
    if not u: c.close(); return {"sucesso":False,"mensagem":"ID não encontrado."}
    if u["role"] in ("ADMINISTRADOR_MASTER","Participante","PARTICIPANTE"): c.close(); return {"sucesso":False,"mensagem":"Este perfil possui permissões estruturais fixas e não pode ser configurado."}
    base={r["permission"]:bool(r["enabled"]) for r in c.execute("select permission,enabled from role_permissions where role=?",(u["role"],)).fetchall()}
    exc={r["permission"]:bool(r["enabled"]) for r in c.execute("select permission,enabled from user_permissions where user_id=?",(uid,)).fetchall()}
    c.close(); vals={p:(exc[p] if p in exc else base.get(p,False)) for p,_,_ in permission_catalog()}
    return {"sucesso":True,"usuario":{"id":u["id"],"nome":u["name"],"categoria":u["role"]},"permissoes":vals,"excecoes":list(exc.keys())}

def salvarPermissoesIndividuais(args):
    d=(args or [{}])[0] or {}; uid=d.get("idUsuario",""); c=con(); u=c.execute("select role from users where id=?",(uid,)).fetchone()
    if not u or u["role"] in ("ADMINISTRADOR_MASTER","Participante","PARTICIPANTE"): c.close(); return {"sucesso":False,"mensagem":"Perfil não configurável."}
    c.execute("delete from user_permissions where user_id=?",(uid,))
    for perm,val in (d.get("permissoes") or {}).items():
        if u["role"] in ("MINISTRANTE","MONITOR_EXTENSIONISTA") and perm.startswith("usuarios_"): val=False
        c.execute("insert into user_permissions(user_id,permission,enabled) values(?,?,?)",(uid,perm,1 if val else 0))
    c.commit();c.close();return {"sucesso":True,"mensagem":"Permissões individuais salvas."}

def restaurarPermissoesCategoria(args):
    uid=str((args or [""])[0]);c=con();c.execute("delete from user_permissions where user_id=?",(uid,));c.commit();c.close();return {"sucesso":True,"mensagem":"Exceções removidas; o usuário voltou a herdar a categoria."}

def salvarPermissaoIndividual(args):
    d=(args or [{}])[0] or {};c=con();c.execute("insert into user_permissions(user_id,permission,enabled) values(?,?,?) on conflict(user_id,permission) do update set enabled=excluded.enabled",(d.get("idUsuario"),d.get("permissao"),1 if d.get("habilitado") else 0));c.commit();c.close();return {"sucesso":True}

def obterMeuPerfil(args):
    uid=str((args or [""])[0]); c=con(); r=c.execute("select id,name,cpf,phone,email,role,language from users where id=?",(uid,)).fetchone(); c.close()
    return ({"sucesso":False,"mensagem":"Usuário não encontrado."} if not r else {"sucesso":True,"id":r["id"],"nome":r["name"],"cpf":r["cpf"],"telefone":r["phone"],"email":r["email"],"tipo":r["role"],"idioma":r["language"]})

def salvarMeuPerfil(args):
    d=(args or [{}])[0] or {}; uid=d.get("id",""); c=con(); r=c.execute("select role from users where id=?",(uid,)).fetchone(); idioma=(d.get("idioma") or "pt").lower()
    obrig=[d.get("nome"),d.get("telefone"),d.get("email"),idioma]
    if not all(str(x or '').strip() for x in obrig): c.close(); return {"sucesso":False,"mensagem":"Preencha todos os campos obrigatórios."}
    if r and r['role']!='ADMINISTRADOR_MASTER' and idioma=='pt' and not str(d.get('cpf') or '').strip(): c.close(); return {"sucesso":False,"mensagem":"CPF é obrigatório para usuários brasileiros."}
    c.execute("update users set name=?,cpf=?,phone=?,email=?,language=? where id=?",(d.get("nome",""),d.get("cpf",""),d.get("telefone",""),d.get("email",""),idioma,uid)); c.commit(); c.close(); return {"sucesso":True,"mensagem":"Perfil atualizado."}

def trocarMinhaSenha(args):
    d=(args or [{}])[0] or {}; nova=str(d.get("novaSenha","") or ""); conf=str(d.get("confirmarSenha","") or "")
    if len(nova)<4:return {"sucesso":False,"mensagem":"A senha deve ter pelo menos 4 caracteres."}
    if nova!=conf:return {"sucesso":False,"mensagem":"As senhas não coincidem."}
    c=con(); c.execute("update users set password=? where id=?",(password_hash(nova),d.get("id",""))); c.commit(); c.close(); return {"sucesso":True,"mensagem":"Senha alterada com sucesso."}

def listarBannersVitrine(args):
    c=con(); rs=c.execute("select * from showcase_banners order by display_order,title").fetchall(); c.close(); return [dict(r) for r in rs]

def salvarBannerVitrine(args):
    d=(args or [{}])[0] or {}
    inicio=str(d.get('dataPublicacao') or '').strip()
    fim=str(d.get('dataTermino') or '').strip()
    try:
        for value in (inicio,fim):
            if value and datetime.date.fromisoformat(value).isoformat()!=value:
                raise ValueError('Data inválida')
    except ValueError:
        return {'sucesso':False,'mensagem':'Informe datas válidas no formato dia/mês/ano.'}
    if inicio and fim and inicio>fim:
        return {'sucesso':False,'mensagem':'A data de término não pode ser anterior à publicação.'}
    c=con(); bid=d.get("id")
    if bid:
        old=c.execute("select image from showcase_banners where id=?",(bid,)).fetchone(); img=d.get("imagem") or (old["image"] if old else "")
        c.execute("update showcase_banners set name=?,image=?,title=?,synopsis=?,banner_type='DIVULGACAO',event_id='',status=?,publish_date=?,end_date=? where id=?",(d.get("nome",""),img,d.get("titulo",""),d.get("sinopse",""),d.get("status","ATIVO"),inicio,fim,bid))
    else:
        bid="BAN-"+uuid.uuid4().hex[:10].upper(); order=(c.execute("select coalesce(max(display_order),0)+1 n from showcase_banners").fetchone()["n"] or 1)
        c.execute("insert into showcase_banners(id,name,image,title,synopsis,banner_type,event_id,status,display_order,created_at,publish_date,end_date) values(?,?,?,?,?,'DIVULGACAO','',?,?,?,?,?)",(bid,d.get("nome",""),d.get("imagem",""),d.get("titulo",""),d.get("sinopse",""),d.get("status","ATIVO"),order,now(),inicio,fim))
    c.commit(); c.close(); return {"sucesso":True,"mensagem":"Banner salvo.","id":bid}

def moverBannerVitrine(args):
    d=(args or [{}])[0] or {}; c=con(); rows=c.execute("select id from showcase_banners order by display_order,created_at").fetchall(); ids=[r['id'] for r in rows]
    if d.get('id') in ids:
        i=ids.index(d['id']); j=i-1 if str(d.get('direcao')).upper()=='UP' else i+1
        if 0<=j<len(ids): ids[i],ids[j]=ids[j],ids[i]
        for n,bid in enumerate(ids,1): c.execute("update showcase_banners set display_order=? where id=?",(n,bid))
    c.commit(); c.close(); return {"sucesso":True}

def excluirBannerVitrine(args):
    c=con(); c.execute("delete from showcase_banners where id=?",(str((args or [""])[0]),)); c.commit(); c.close(); return {"sucesso":True,"mensagem":"Banner excluído."}

def obterBannersPublicos(args):
    from zoneinfo import ZoneInfo
    hoje=datetime.datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    c=con()
    rs=c.execute("""select * from showcase_banners
      where upper(status)='ATIVO'
      and (publish_date IS NULL or publish_date='' or publish_date<=?)
      and (end_date IS NULL or end_date='' or end_date>=?)
      order by display_order,title""",(hoje,hoje)).fetchall()
    c.close()
    return [dict(r) for r in rs]

def obterTema(args):
    c=con();r=c.execute("select v from settings where k='theme'").fetchone();c.close()
    
    base={"fundo":"#f8fafc","painelLogin":"#ffffff","titulo":"#111827","fundoTitulo":"#ffffff","cabecalho":"#ffffff","textoCabecalho":"#111827","menuLateral":"#0f172a","textoMenuLateral":"#ffffff"}
    if r:
        try: base.update(json.loads(r["v"]))
        except Exception: pass
    return base

def salvarTema(args):
    d=(args or [{}])[0] or {}
    if not isinstance(d,dict) or any(k not in FE_APPEARANCE_BASE or not isinstance(v,str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",v) for k,v in d.items()):
        return {"sucesso":False,"mensagem":"Cores inválidas."}
    try:
        # Gerar CSS ANTES de confirmar o tema no banco; manter a configuração anterior em caso de falha.
        merged={**obterTema([]),**d}
        fe_write_appearance_css(merged,fe_read_extra_colors())
        c=con()
        try:
            c.execute("insert into settings(k,v) values('theme',?) on conflict(k) do update set v=excluded.v",(json.dumps(merged),))
            c.commit()
        finally:c.close()
        return {"sucesso":True,"mensagem":"Aparência gravada no CSS do servidor."}
    except Exception:
        return {"sucesso":False,"mensagem":"Não foi possível gravar o CSS de aparência."}

def adicionarCarrinho(args):
    d=(args or [{}])[0] or {}; uid=d.get("idUsuario",""); eid=d.get("idEvento",""); atividade=d.get("atividade",""); valor=float(d.get("valor") or 0)
    c=con(); cart=c.execute("select * from carts where user_id=? and status='ABERTO'",(uid,)).fetchone()
    if not cart:
        cid="CAR-"+uuid.uuid4().hex[:10].upper(); exp=(datetime.datetime.now()+datetime.timedelta(minutes=20)).isoformat(timespec="seconds")
        c.execute("insert into carts values(?,?,?,?,?,?)",(cid,uid,eid,"ABERTO",now(),exp))
    else: cid=cart["id"]
    if not c.execute("select 1 from cart_items where cart_id=? and event_id=? and activity=?",(cid,eid,atividade)).fetchone():
        c.execute("insert into cart_items(cart_id,event_id,activity,value,status) values(?,?,?,?,?)",(cid,eid,atividade,valor,"RESERVADO"))
    c.commit(); n=c.execute("select count(*) n from cart_items where cart_id=?",(cid,)).fetchone()["n"];c.close()
    return {"sucesso":True,"carrinho":cid,"quantidade":n,"expiraEmMinutos":20}

def obterCarrinho(args):
    uid=str((args or [""])[0]);c=con();cart=c.execute("select * from carts where user_id=? and status='ABERTO'",(uid,)).fetchone()
    if not cart:c.close();return {"itens":[],"quantidade":0,"total":0}
    itens=c.execute("select * from cart_items where cart_id=?",(cart["id"],)).fetchall();c.close()
    return {"id":cart["id"],"itens":[dict(x) for x in itens],"quantidade":len(itens),"total":sum(float(x["value"] or 0) for x in itens),"expira":cart["expires_at"]}

def finalizarCompraManual(args):
    d=(args or [{}])[0] or {}; uid=d.get("idUsuario",""); cid=d.get("idCarrinho",""); c=con(); itens=c.execute("select * from cart_items where cart_id=?",(cid,)).fetchall()
    if not itens:c.close();return {"sucesso":False,"mensagem":"Carrinho vazio."}
    pid="PAG-"+uuid.uuid4().hex[:10].upper(); total=sum(float(x["value"] or 0) for x in itens); eid=itens[0]["event_id"]
    c.execute("insert into payments(id,user_id,event_id,method,status,total,created_at) values(?,?,?,?,?,?,?)",(pid,uid,eid,"PIX_MANUAL","PENDENTE",total,now()));c.commit()
    cfg=c.execute("select * from pix_config where event_id=?",(eid,)).fetchone();c.close()
    return {"sucesso":True,"idPagamento":pid,"total":total,"chavePix":cfg["pix_key"] if cfg else "","beneficiario":cfg["receiver"] if cfg else ""}

def criarCobrancaPixApi(args):
    d=(args or [{}])[0] or {}; return {"sucesso":False,"mensagem":"Integração preparada, mas requer credenciais reais do provedor Pix configurado para criar cobrança/webhook."}


ROLE_REQUEST_OPTIONS={"EQUIPE_ADMINISTRATIVA","COORDENADOR","MINISTRANTE","MONITOR_EXTENSIONISTA"}

def _session_user(c,token):
    row=c.execute("select u.* ,s.last_activity from sessions s join users u on u.id=s.user_id where s.token=?",(str(token or ''),)).fetchone()
    if not row:return None
    try:
        policy=obterSeguranca([])
        minutes=policy['participante'] if str(row['role']).upper()=='PARTICIPANTE' else policy['administrativo']
        if datetime.datetime.now()-datetime.datetime.fromisoformat(row['last_activity'])>datetime.timedelta(minutes=int(minutes)):
            return None
    except (ValueError,TypeError):return None
    return row

def solicitarMudancaCategoria(args):
    d=(args or [{}])[0] or {};c=con()
    try:
        who=_session_user(c,d.get('token'))
        if not who or str(who['role']).upper()!='PARTICIPANTE':return {'sucesso':False,'mensagem':'Sessão de participante inválida.'}
        role=str(d.get('perfil') or '').upper(); reason=str(d.get('justificativa') or '').strip(); event=str(d.get('evento') or '').strip()
        if role not in ROLE_REQUEST_OPTIONS:return {'sucesso':False,'mensagem':'Categoria inválida.'}
        if len(reason)<10 or len(reason)>1500:return {'sucesso':False,'mensagem':'Informe uma justificativa entre 10 e 1500 caracteres.'}
        if role in ('COORDENADOR','MINISTRANTE','MONITOR_EXTENSIONISTA'):
            if not event or not c.execute('select 1 from events where id=?',(event,)).fetchone():return {'sucesso':False,'mensagem':'Selecione um evento válido.'}
        else:event=''
        if c.execute("select 1 from role_requests where user_id=? and status='PENDENTE'",(who['id'],)).fetchone():return {'sucesso':False,'mensagem':'Você já possui uma solicitação pendente.'}
        c.execute('insert into role_requests(user_id,requested_role,event_id,reason,created_at) values(?,?,?,?,?)',(who['id'],role,event,reason,now()));c.commit()
        return {'sucesso':True,'mensagem':'Solicitação enviada à administração.'}
    finally:c.close()

def minhasSolicitacoesCategoria(args):
    c=con()
    try:
        who=_session_user(c,(args or [''])[0]);
        if not who:return {'sucesso':False,'mensagem':'Sessão inválida.'}
        rows=c.execute('select id,requested_role,event_id,reason,status,created_at,decided_at,decision_note from role_requests where user_id=? order by id desc',(who['id'],)).fetchall()
        return {'sucesso':True,'solicitacoes':[dict(r) for r in rows]}
    finally:c.close()

def listarSolicitacoesCategoria(args):
    c=con()
    try:
        who=_session_user(c,(args or [''])[0]);
        if not who or who['role']!='ADMINISTRADOR_MASTER':return {'sucesso':False,'mensagem':'Acesso restrito ao Administrador Master.'}
        rows=c.execute("select r.*,u.name nome,u.email email,u.role perfil_atual from role_requests r join users u on u.id=r.user_id order by case when r.status='PENDENTE' then 0 else 1 end,r.id desc").fetchall()
        return {'sucesso':True,'solicitacoes':[dict(r) for r in rows]}
    finally:c.close()

def decidirSolicitacaoCategoria(args):
    d=(args or [{}])[0] or {};c=con()
    try:
        who=_session_user(c,d.get('token'))
        if not who or who['role']!='ADMINISTRADOR_MASTER':return {'sucesso':False,'mensagem':'Acesso restrito ao Administrador Master.'}
        decision=str(d.get('decisao') or '').upper()
        if decision not in ('APROVADA','RECUSADA'):return {'sucesso':False,'mensagem':'Decisão inválida.'}
        row=c.execute("select * from role_requests where id=? and status='PENDENTE'",(d.get('id'),)).fetchone()
        if not row:return {'sucesso':False,'mensagem':'Solicitação já analisada ou inexistente.'}
        if decision=='APROVADA':
            current=c.execute('select role from users where id=?',(row['user_id'],)).fetchone()
            if not current or str(current['role']).upper()!='PARTICIPANTE':return {'sucesso':False,'mensagem':'Perfil foi alterado; revise a solicitação.'}
            c.execute('update users set role=? where id=?',(row['requested_role'],row['user_id']))
            # Forçar novo login após elevação de privilégios.
            c.execute('delete from sessions where user_id=?',(row['user_id'],))
        c.execute('update role_requests set status=?,decided_at=?,decided_by=?,decision_note=? where id=?',(decision,now(),who['id'],str(d.get('observacao') or '')[:500],row['id']))
        c.commit();return {'sucesso':True,'mensagem':'Solicitação '+decision.lower()+' com sucesso.'}
    finally:c.close()

REG={
"solicitarMudancaCategoria":solicitarMudancaCategoria,"minhasSolicitacoesCategoria":minhasSolicitacoesCategoria,"listarSolicitacoesCategoria":listarSolicitacoesCategoria,"decidirSolicitacaoCategoria":decidirSolicitacaoCategoria,
"realizarLogin":realizarLogin,"cadastrarUsuario":cadastrarUsuario,"recuperarSenhaCasada":recuperarSenhaCasada,
"listarEventos":listarEventos,"criarEvento":criarEvento,"salvarEventoServidor":criarEvento,"salvarRascunhoEvento":criarEvento,
"buscarCronogramaEvento":buscarCronogramaEvento,"buscarDadosEventoUnitario":buscarDadosEventoUnitario,
"publicarEventoPorId":publicarEventoPorId,"excluirEventoRascunho":excluirEventoRascunho,
"cancelarEvento":lambda a:status_event(a,"CANCELADO"),"arquivarEvento":lambda a:status_event(a,"ARQUIVADO"),
"arquivarEventoParaPlanilhaIndependente":lambda a:status_event(a,"ARQUIVADO"),
"mudarStatusPublicacaoEvento":lambda a:status_event(a,str((a+[None,"PUBLICADO"])[1] or "PUBLICADO")),
"obterListaUsuariosParaSegurancaMaster":obterListaUsuariosParaSegurancaMaster,"obterUsuariosCadastradosAdmin":obterListaUsuariosParaSegurancaMaster,
"atualizarStatusAcessoUsuarioPorAdmin":atualizarStatusAcessoUsuarioPorAdmin,"salvarUsuarioCadastradoAdmin":salvarUsuarioCadastradoAdmin,
"excluirUsuarioCadastradoAdmin":excluirUsuarioCadastradoAdmin,"redefinirSenhaUsuarioAdmin":redefinirSenhaUsuarioAdmin,"obterConfiguracaoPixPorEvento":obterConfiguracaoPixPorEvento,
"salvarConfiguracaoPixPorEvento":salvarConfiguracaoPixPorEvento,"inscreverNoEvento":inscreverNoEvento,
"cancelarInscricao":cancelarInscricao,"enviarComprovantePagamento":enviarComprovantePagamento,
"confirmarPagamentoEvento":confirmarPagamentoEvento,"listarParticipantesPorAtividade":listarParticipantesPorAtividade,
"mudarStatusPresencaPorMembro":mudarStatusPresencaPorMembro,"obterIdiomasAtivos":obterIdiomasAtivos,
"buscarPerfilUsuarioPorId":buscarPerfilUsuarioPorId,"atualizarPerfilUsuarioPorId":atualizarPerfilUsuarioPorId,
"buscarInscricoesEComprovantes":buscarInscricoesEComprovantes,"buscarCertificadosAluno":buscarCertificadosAluno,
"obterFinanceiroPorEvento":obterFinanceiroPorEvento,"obterEstatisticasEvento":obterEstatisticasEvento,
"obterConfiguracaoCertificadoPorEvento":obterConfiguracaoCertificadoPorEvento,"salvarConfiguracaoCertificadoEvento":salvarConfiguracaoCertificadoEvento,
"obterPainelCertificadosPorEvento":obterPainelCertificadosPorEvento,"processarEntradaQRCodeMembro":processarEntradaQRCodeMembro,
"obterListaCertificadosParaAuditoria":obterListaCertificadosParaAuditoria,"atualizarDocumentoAssinado":atualizarDocumentoAssinado,
"mudarStatusPublicacaoEvento":mudarStatusPublicacaoEventoCompat,"redefinirSenha":redefinirSenha,"validarSessao":validarSessao,"encerrarSessao":encerrarSessao,
"obterVitrineEventos":obterVitrineEventos,"obterCronogramaPublico":obterCronogramaPublico,
"gerarDocumentoPdfPresencaNativo":gerarDocumentoPdfPresencaNativo,"obterPagamentosAuditoria":obterPagamentosAuditoria,
"obterFichaReembolso":obterFichaReembolso,"registrarReembolso":registrarReembolso,
"obterPermissoes":obterPermissoes,"salvarPermissoes":salvarPermissoes,"salvarPermissaoIndividual":salvarPermissaoIndividual,"obterPermissoesIndividuais":obterPermissoesIndividuais,"salvarPermissoesIndividuais":salvarPermissoesIndividuais,"restaurarPermissoesCategoria":restaurarPermissoesCategoria,
"obterMeuPerfil":obterMeuPerfil,"salvarMeuPerfil":salvarMeuPerfil,"trocarMinhaSenha":trocarMinhaSenha,"listarBannersVitrine":listarBannersVitrine,"salvarBannerVitrine":salvarBannerVitrine,"moverBannerVitrine":moverBannerVitrine,"excluirBannerVitrine":excluirBannerVitrine,"obterBannersPublicos":obterBannersPublicos,"obterTema":obterTema,"salvarTema":salvarTema,"obterSeguranca":obterSeguranca,"salvarSeguranca":salvarSeguranca,"adicionarCarrinho":adicionarCarrinho,"obterCarrinho":obterCarrinho,
"finalizarCompraManual":finalizarCompraManual,"criarCobrancaPixApi":criarCobrancaPixApi,"validarCredencialForEventoPublica":validarCredencialForEventoPublica,"listarModelosCertificados":listarModelosCertificados,"salvarModeloCertificado":salvarModeloCertificado,"excluirModeloCertificado":excluirModeloCertificado,"obterModelosCertificadosDrive":obterModelosCertificadosDrive,"obterTagsModeloCertificado":obterTagsModeloCertificado
}

@app.post("/api/participante/resumo")
async def resumo_participante(request:Request):
    """Dados privados do participante, filtrados pelo usuário da sessão validada."""
    try:
        payload=await request.json()
        token=str(payload.get("token") or "")
        if not token:
            return JSONResponse({"erro":"Sessão não informada."},status_code=401)
        auth=validarSessao([token])
        if not auth.get("sucesso") or str(auth.get("tipo") or "").upper()!="PARTICIPANTE":
            return JSONResponse({"erro":"Sessão de participante inválida."},status_code=403)
        c=con()
        uid=auth["id"]
        registrations=[dict(r) for r in c.execute("select id,event_id,activity,status,created_at from registrations where user_id=? order by created_at desc",(uid,)).fetchall()]
        certificates=[dict(r) for r in c.execute("select id,event_id,activity,status,language,file_url from certificates where user_id=? order by created_at desc",(uid,)).fetchall()]
        c.close()
        return {"nome":auth["nome"],"id":uid,"inscricoes":registrations,"certificados":certificates}
    except Exception:
        return JSONResponse({"erro":"Não foi possível consultar seus dados."},status_code=500)

PARTICIPANT_THEME_DEFAULTS={"header":"#ffffff","sidebar":"#152a48","page":"#eff5fc","card":"#ffffff","accent":"#2563eb","text":"#10233f"}

@app.get("/api/participante/tema")
async def participant_theme_read():
    c=con()
    try:
        row=c.execute("select v from settings where k='participant_theme'").fetchone()
        saved=json.loads(row['v']) if row else {}
        return {**PARTICIPANT_THEME_DEFAULTS,**{k:v for k,v in saved.items() if k in PARTICIPANT_THEME_DEFAULTS and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}}
    finally:c.close()

@app.post("/api/participante/tema")
async def participant_theme_write(request:Request):
    data=await request.json()
    auth=validarSessao([str(data.get('token') or '')])
    if not auth.get('sucesso') or str(auth.get('tipo') or '').upper()!='ADMINISTRADOR_MASTER':
        return JSONResponse({'erro':'Somente o Administrador Master pode alterar as cores.'},status_code=403)
    colors=data.get('colors') or {}
    if not isinstance(colors,dict) or set(colors)!=set(PARTICIPANT_THEME_DEFAULTS) or any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in colors.values()):
        return JSONResponse({'erro':'Cores inválidas.'},status_code=400)
    c=con()
    try:
        c.execute("insert into settings(k,v) values('participant_theme',?) on conflict(k) do update set v=excluded.v",(json.dumps(colors),))
        c.commit()
    finally:c.close()
    return {'sucesso':True,'mensagem':'Cores da Área do Participante salvas.'}

# As quatro categorias administrativas usam o mesmo painel do Master.
# A matriz de permissões é consultada no servidor, não calculada pelo navegador.
ADMIN_ROLES = {"ADMINISTRADOR_MASTER", "EQUIPE_ADMINISTRATIVA", "COORDENADOR", "MINISTRANTE", "MONITOR_EXTENSIONISTA"}

@app.post('/api/admin/acesso')
async def acesso_painel_administrativo(request:Request):
    data=await request.json()
    token=str(data.get('token') or '')
    c=con()
    try:
        who=_session_user(c,token)
        if not who or str(who['role']).upper() not in ADMIN_ROLES:
            return JSONResponse({'sucesso':False,'mensagem':'Sessão administrativa inválida.'},status_code=401)
        role=str(who['role']).upper()
        catalog=[p for p,_,_ in permission_catalog()]
        if role=='ADMINISTRADOR_MASTER':
            perms={p:True for p in catalog}
        else:
            perms={r['permission']:bool(r['enabled']) for r in c.execute('select permission,enabled from role_permissions where role=?',(role,))}
            perms={p:perms.get(p,False) for p in catalog}
            for r in c.execute('select permission,enabled from user_permissions where user_id=?',(who['id'],)):
                if r['permission'] in perms:perms[r['permission']]=bool(r['enabled'])
        return {'sucesso':True,'nome':who['name'],'categoria':role,'permissoes':perms}
    finally:c.close()

# Temas independentes para o terceiro modelo. Master e Participante são imutáveis aqui.
OPERATIONAL_ROLES = {"EQUIPE_ADMINISTRATIVA", "COORDENADOR", "MINISTRANTE", "MONITOR_EXTENSIONISTA"}
OP_THEME_DEFAULTS = {
    "header_bg":"#193650", "header_text":"#ffffff", "sidebar_bg":"#244a6b",
    "sidebar_text":"#ffffff", "active_bg":"#39719d", "active_text":"#ffffff",
    "submenu_bg":"#305879", "submenu_text":"#ffffff", "content_bg":"#eff3f8",
    "content_text":"#193650", "card_bg":"#ffffff", "card_text":"#193650",
    "card_border":"#cbd5e1", "button_bg":"#2563eb", "button_text":"#ffffff",
    "table_head_bg":"#e2e8f0", "table_head_text":"#193650", "table_row_bg":"#ffffff",
    "field_bg":"#ffffff", "field_border":"#94a3b8"
}

def _operational_theme(c, role):
    row=c.execute('select v from settings where k=?', ('operational_theme:'+role,)).fetchone()
    try: stored=json.loads(row['v']) if row else {}
    except (ValueError, TypeError): stored={}
    return {**OP_THEME_DEFAULTS, **{k:v for k,v in stored.items() if k in OP_THEME_DEFAULTS and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}}

@app.post('/api/operacional/tema')
async def operational_theme_api(request:Request):
    payload=await request.json()
    c=con()
    try:
        who=_session_user(c,str(payload.get('token') or ''))
        if not who: return JSONResponse({'sucesso':False,'mensagem':'Sessão inválida.'},status_code=401)
        actor=str(who['role']).upper()
        role=str(payload.get('perfil') or (actor if actor in OPERATIONAL_ROLES else '')).upper()
        if role not in OPERATIONAL_ROLES:
            return JSONResponse({'sucesso':False,'mensagem':'Perfil não configurável.'},status_code=400)
        if actor!='ADMINISTRADOR_MASTER' and actor!=role:
            return JSONResponse({'sucesso':False,'mensagem':'Acesso negado.'},status_code=403)
        if payload.get('acao')=='salvar':
            if actor!='ADMINISTRADOR_MASTER':
                return JSONResponse({'sucesso':False,'mensagem':'Somente o Master pode salvar.'},status_code=403)
            values=payload.get('cores')
            if not isinstance(values,dict) or set(values)!=set(OP_THEME_DEFAULTS) or any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in values.values()):
                return JSONResponse({'sucesso':False,'mensagem':'Paleta inválida.'},status_code=400)
            c.execute("insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v",('operational_theme:'+role,json.dumps(values)))
            c.commit()
        elif payload.get('acao')=='restaurar':
            if actor!='ADMINISTRADOR_MASTER':
                return JSONResponse({'sucesso':False,'mensagem':'Somente o Master pode restaurar.'},status_code=403)
            c.execute('delete from settings where k=?',('operational_theme:'+role,));c.commit()
        return {'sucesso':True,'perfil':role,'cores':_operational_theme(c,role)}
    finally:c.close()

@app.post('/api/presenca/pdf')
async def baixar_diario_presenca(request:Request):
    data=await request.json()
    eid=str(data.get('idEvento') or '').strip()
    activity=str(data.get('atividade') or '').strip()
    if not eid or not activity:
        return JSONResponse({'mensagem':'Evento e atividade são obrigatórios.'},status_code=400)
    c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'mensagem':'Acesso não autorizado.'},status_code=403)
        # Somente quem pode gerar listas de presença.
        role=str(who['role']).upper()
        if role!='ADMINISTRADOR_MASTER':
            perm=c.execute('select enabled from user_permissions where user_id=? and permission=?',(who['id'],'lista_pdf')).fetchone()
            if perm is None:
                perm=c.execute('select enabled from role_permissions where role=? and permission=?',(role,'lista_pdf')).fetchone()
            if not perm or not int(perm['enabled']):
                return JSONResponse({'mensagem':'Sem permissão para gerar lista PDF.'},status_code=403)
        ev=c.execute('select * from events where id=?',(eid,)).fetchone()
        acts=c.execute('select * from schedules where event_id=?',(eid,)).fetchall()
        norm=lambda x: re.sub(r'\s+',' ',str(x or '').strip()).casefold()
        matches=[a for a in acts if norm(a['synopsis_activity'] or a['speaker'])==norm(activity)]
        if not ev or len(matches)!=1:
            return JSONResponse({'mensagem':'Evento ou atividade não encontrado(a) de forma inequívoca.'},status_code=404)
        rows=c.execute("""select r.id,r.email,u.name from registrations r
          left join users u on u.id=r.user_id
          where r.event_id=? and lower(trim(r.activity))=lower(trim(?))
          and upper(coalesce(r.status,'')) not in ('CANCELADO','CANCELADA','REEMBOLSADO')
          order by upper(coalesce(u.name,r.email)),r.id""",(eid,activity)).fetchall()
        payload=build_pdf(ev,matches[0],rows)
        filename='DIARIO_FREQUENCIA_'+re.sub('[^A-Za-z0-9_-]','_',eid)+'.pdf'
        return Response(content=payload,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})
    finally:c.close()

# Gerenciamento de backups: exclusivo do Administrador Master; validação no servidor.
from fastapi.responses import FileResponse

def _fe_backup_master(token):
    c=con()
    try:
        who=_session_user(c,str(token or ''))
        return bool(who and str(who['role']).upper()=='ADMINISTRADOR_MASTER')
    finally:c.close()

@app.post('/api/admin/backup/gerenciar')
async def fe_backup_manage(request:Request):
    data=await request.json()
    if not _fe_backup_master(data.get('token')):
        return JSONResponse({'sucesso':False,'mensagem':'Acesso exclusivo do Administrador Master.'},status_code=403)
    try:
        action=data.get('acao','listar')
        if action=='criar':result=_bm.create('manual')
        elif action=='configurar':result=_bm.save_config(data.get('periodo',data.get('dias',0)),data.get('manter',10))
        elif action=='restaurar':
            if data.get('confirmacao')!='RESTAURAR':raise ValueError('Confirmação obrigatória: RESTAURAR')
            result=_bm.stage_restore(data.get('arquivo',''))
        elif action=='excluir':
            if data.get('confirmacao')!='EXCLUIR':raise ValueError('Confirmação obrigatória: EXCLUIR')
            result=_bm.delete_backup(data.get('arquivo',''))
        elif action=='listar':result=None
        else:raise ValueError('Ação inválida')
        return {'sucesso':True,'resultado':result,'configuracao':_bm.config(),'proximo_backup':(_bm.next_backup().isoformat() if _bm.next_backup() else None),'pontos':_bm.points()}
    except Exception as exc:
        logging.exception('Operação de backup falhou')
        return JSONResponse({'sucesso':False,'mensagem':str(exc)},status_code=400)

@app.get('/api/admin/backup/baixar/{arquivo}')
def fe_backup_download(arquivo:str,token:str=''):
    if not _fe_backup_master(token):return JSONResponse({'mensagem':'Acesso negado'},status_code=403)
    try:f=_bm.get_file(arquivo)
    except (ValueError,FileNotFoundError):return JSONResponse({'mensagem':'Arquivo inválido'},status_code=404)
    return FileResponse(f,filename=f.name,media_type='application/zip',headers={'Cache-Control':'no-store'})

@app.post('/api/admin/backup/manual')
async def backup_manual(request:Request):
    data=await request.json()
    c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            return JSONResponse({'sucesso':False,'mensagem':'Acesso exclusivo do Administrador Master.'},status_code=403)
    finally:c.close()
    try:
        result=_backup_db('manual',force=True)
        return {'sucesso':True,'mensagem':'Backup manual concluído e validado.','status':result,'backups':_backup_status()}
    except Exception as exc:
        logging.exception('Falha no backup manual')
        return JSONResponse({'sucesso':False,'mensagem':str(exc)},status_code=500)

@app.post('/api/admin/backup/status')
async def backup_status(request:Request):
    data=await request.json();c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            return JSONResponse({'sucesso':False},status_code=403)
    finally:c.close()
    return {'sucesso':True,'backups':_backup_status()}

# v25 - aparência compilada em CSS persistente, sem consulta visual ao banco na navegação.
FE_APPEARANCE_BASE={"fundo":"#f8fafc","painelLogin":"#ffffff","titulo":"#111827","fundoTitulo":"#ffffff","cabecalho":"#ffffff","textoCabecalho":"#111827","menuLateral":"#0f172a","textoMenuLateral":"#ffffff"}
FE_APPEARANCE_EXTRA={"active":"#2563eb","activeText":"#ffffff","divider":"#ffffff","footer":"#0f172a","footerText":"#ffffff"}
FE_APPEARANCE_PATH=BASE/'app/static/css/fe_appearance_generated.css'

def fe_read_extra_colors():
    c=con()
    try:
        row=c.execute("select v from settings where k='appearance_extra_v25'").fetchone()
        data=json.loads(row['v']) if row else {}
        return {**FE_APPEARANCE_EXTRA,**{k:v for k,v in data.items() if k in FE_APPEARANCE_EXTRA and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}}
    finally:c.close()

def fe_write_appearance_css(base,extra):
    import os
    vals={**{'--fe-'+k:v for k,v in base.items() if k in FE_APPEARANCE_BASE},**{'--fe-v24-'+k:v for k,v in extra.items() if k in FE_APPEARANCE_EXTRA}}
    if any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in vals.values()):raise ValueError('Cor inválida')
    content='/* CSS de aparência gerado pelo ForEvento */\n:root{\n'+''.join('  '+k+':'+v+';\n' for k,v in vals.items())+'}\n'
    path=FE_APPEARANCE_PATH;path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    try:
        temp.write_text(content,encoding='utf-8');os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

@app.get('/api/appearance.css')
async def fe_appearance_css():
    try:css=FE_APPEARANCE_PATH.read_text(encoding='utf-8')
    except OSError:css=':root{}'
    return Response(content=css,media_type='text/css',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/api/appearance/settings')
async def fe_appearance_settings():
    return fe_read_extra_colors()

@app.post('/api/appearance/settings')
async def fe_appearance_save(request:Request):
    data=await request.json()
    c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            return JSONResponse({'erro':'Somente o Administrador Master pode salvar aparência.'},status_code=403)
    finally:c.close()
    colors=data.get('colors')
    if not isinstance(colors,dict) or set(colors)!=set(FE_APPEARANCE_EXTRA) or any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in colors.values()):
        return JSONResponse({'erro':'Cores inválidas.'},status_code=400)
    try:
        fe_write_appearance_css(obterTema([]),colors)
        c=con()
        try:
            c.execute("insert into settings(k,v) values('appearance_extra_v25',?) on conflict(k) do update set v=excluded.v",(json.dumps(colors),))
            c.commit()
        finally:c.close()
    except Exception:
        return JSONResponse({'erro':'Falha ao gravar CSS no servidor.'},status_code=500)
    return {'sucesso':True}


@app.post("/api/admin/certificados/modelos")
async def fe_modelos_catalogo(request:Request):
    data=await request.json()
    c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Sessão administrativa inválida.'},status_code=403)
    finally:c.close()
    try:
        modelos=listarModelosCertificados([])
        return {'sucesso':True,'modelos':[
            {'id':str(m['id']),'nome':m['filename'],
             'codigoIdioma':m['language'],'tipoAssinatura':m['signature_type'], 'formato':Path(m['filename']).suffix.lower().lstrip('.')}
            for m in modelos]}
    except Exception as exc:
        return JSONResponse({'sucesso':False,'mensagem':'Falha ao listar modelos: '+str(exc)},status_code=500)

@app.post("/api/admin/certificados/modelos/previa")
async def fe_modelo_previa(request:Request):
    data=await request.json()
    c=con()
    try:
        who=_session_user(c,str(data.get('token') or ''))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Sessão administrativa inválida.'},status_code=403)
    finally:c.close()
    try:
        modelos=listarModelosCertificados([])
        modelo=next((m for m in modelos if str(m['id'])==str(data.get('id') or '')),None)
        if not modelo:
            return JSONResponse({'sucesso':False,'mensagem':'Modelo não encontrado.'},status_code=404)
        preview,mime=_miniatura_certificado(modelo['file_path'])
        if not preview:
            return {'sucesso':False,'mensagem':'Prévia indisponível: verifique LibreOffice (PPTX) e PyMuPDF (PDF) no Python do servidor.'}
        return {'sucesso':True,'base64':preview,'mime':mime}
    except Exception as exc:
        return JSONResponse({'sucesso':False,'mensagem':'Erro na prévia: '+str(exc)},status_code=500)

@app.post("/api/admin/certificados/gerar")
async def gerar_certificados_python(request:Request):
    """Geração autenticada; não passa pelo inventário Apps Script."""
    data=await request.json()
    token=str(data.get("token") or "")
    eid=str(data.get("idEvento") or "")
    c=con()
    try:
        who=_session_user(c,token)
        if not who or str(who["role"]).upper()=="PARTICIPANTE":
            return JSONResponse({"sucesso":False,"mensagem":"Acesso negado."},status_code=403)
        if str(who["role"]).upper()!="ADMINISTRADOR_MASTER":
            perm=c.execute("select enabled from user_permissions where user_id=? and permission='cert_gerar'",(who["id"],)).fetchone()
            if perm is None:
                perm=c.execute("select enabled from role_permissions where role=? and permission='cert_gerar'",(str(who["role"]).upper(),)).fetchone()
            if not perm or not int(perm["enabled"]):
                return JSONResponse({"sucesso":False,"mensagem":"Sem permissão para gerar certificados."},status_code=403)
    finally:c.close()
    # O servidor usa o formato gravado para o evento, não o valor do navegador.
    cfgcon=con()
    try:
        saved=cfgcon.execute('select v from settings where k=?',('cert_model_format:'+eid,)).fetchone()
        formato=str(saved['v'] if saved else '').lower().strip()
        modelrow=cfgcon.execute('select v from settings where k=?',('cert_model_id:'+eid,)).fetchone()
        modelo_salvo=str(modelrow['v'] if modelrow else '').strip()
    finally:cfgcon.close()
    if formato not in ('pdf','pptx'):
        return JSONResponse({'sucesso':False,'mensagem':'Defina e salve o formato PDF/PPTX deste evento antes de gerar.'},status_code=400)
    _sincronizar_modelos()
    from .cert_migration import gerar_em_massa
    return gerar_em_massa(con,_modelos_dir(),BASE,eid,str(request.base_url).rstrip("/"),modelo_salvo,formato)

# Preferência persistente e individual do evento; migração não destrutiva via settings.
@app.post('/api/admin/certificados/formato-evento')
async def formato_certificado_evento(request:Request):
    data=await request.json()
    eid=str(data.get('idEvento') or '').strip()
    token=str(data.get('token') or '')
    operation=str(data.get('operacao') or 'consultar')
    c=con()
    try:
        who=_session_user(c,token)
        if not who or str(who['role'] or '').upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Acesso negado.'},status_code=403)
        role=str(who['role'] or '').upper()
        if role!='ADMINISTRADOR_MASTER':
            perm=c.execute('select enabled from user_permissions where user_id=? and permission=?',(who['id'],'cert_gerar')).fetchone()
            if perm is None:
                perm=c.execute('select enabled from role_permissions where role=? and permission=?',(role,'cert_gerar')).fetchone()
            if not perm or not int(perm['enabled']):
                return JSONResponse({'sucesso':False,'mensagem':'Sem permissão para configurar certificados.'},status_code=403)
        if not eid or not c.execute('select 1 from events where id=?',(eid,)).fetchone():
            return JSONResponse({'sucesso':False,'mensagem':'Selecione um evento válido.'},status_code=400)
        key='cert_model_format:'+eid
        modelkey='cert_model_id:'+eid
        if operation=='salvar_modelo':
            mid=str(data.get('idModelo') or '').strip()
            if mid and (not mid.isdigit() or not c.execute('select 1 from certificate_models where id=?',(int(mid),)).fetchone()):
                return JSONResponse({'sucesso':False,'mensagem':'Modelo inexistente.'},status_code=400)
            c.execute('insert or replace into settings(k,v) values(?,?)',(modelkey,mid));c.commit()
        if operation=='salvar':
            fmt=str(data.get('formato') or '').lower().strip()
            if fmt not in ('pdf','pptx'):
                return JSONResponse({'sucesso':False,'mensagem':'Formato inválido.'},status_code=400)
            c.execute('insert or replace into settings(k,v) values(?,?)',(key,fmt))
            c.commit()
        row=c.execute('select v from settings where k=?',(key,)).fetchone()
        modelrow=c.execute('select v from settings where k=?',(modelkey,)).fetchone()
        return {'sucesso':True,'formato':row['v'] if row else 'pdf','configurado':bool(row),'idModelo':modelrow['v'] if modelrow else ''}
    finally:c.close()

@app.get("/api/certificados/arquivo/{certificate_id}")
def abrir_certificado_python(certificate_id:str,request:Request,token:str=""):
    """Arquivos privados; o participante precisa estar autenticado."""
    if not re.fullmatch(r"CERT-[A-F0-9]{16}",certificate_id):
        return JSONResponse({"erro":"Certificado não encontrado."},status_code=404)
    c=con()
    try:
        who=_session_user(c,request.headers.get("X-ForEvento-Token") or token)
        cert=c.execute("select * from certificates where id=?",(certificate_id,)).fetchone()
        if not who or not cert:
            return JSONResponse({"erro":"Acesso negado."},status_code=403)
        role=str(who["role"] or "").upper()
        if role=="PARTICIPANTE" and (str(cert["user_id"])!=str(who["id"]) or str(cert["status"]).upper()!="ENVIADO"):
            return JSONResponse({"erro":"Certificado ainda não liberado."},status_code=403)
        if role!="PARTICIPANTE" and role!="ADMINISTRADOR_MASTER":
            allowed=c.execute("select enabled from user_permissions where user_id=? and permission='cert_visualizar'",(who['id'],)).fetchone()
            if allowed is None:allowed=c.execute("select enabled from role_permissions where role=? and permission='cert_visualizar'",(role,)).fetchone()
            if not allowed or not int(allowed['enabled']):
                return JSONResponse({"erro":"Sem permissão para visualizar certificados."},status_code=403)
    finally:c.close()
    path=BASE/"storage"/"certificados"/(certificate_id+".pdf")
    if not path.is_file():
        return JSONResponse({"erro":"Arquivo não localizado."},status_code=404)
    return Response(content=path.read_bytes(),media_type="application/pdf",
                    headers={"Content-Disposition":"inline; filename=certificado.pdf","Cache-Control":"private, no-store"})

@app.post("/api/admin/certificados/excluir")
async def excluir_certificado_seguro(request:Request):
    """Exclui apenas o certificado; mantém inscrições/presenças e arquiva o PDF."""
    import os
    payload=await request.json()
    cid=str(payload.get('idCertificado') or '').strip()
    if not re.fullmatch(r'CERT-[A-F0-9]{16}',cid):
        return JSONResponse({'sucesso':False,'mensagem':'Identificador inválido.'},status_code=400)
    c=con()
    archive=None; original=None
    try:
        who=_session_user(c,payload.get('token'))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Sessão administrativa inválida.'},status_code=403)
        if str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            role=str(who['role']).upper()
            perm=c.execute("select enabled from user_permissions where user_id=? and permission='cert_excluir'",(who['id'],)).fetchone()
            if perm is None:perm=c.execute("select enabled from role_permissions where role=? and permission='cert_excluir'",(role,)).fetchone()
            if not perm or not int(perm['enabled']):
                return JSONResponse({'sucesso':False,'mensagem':'Sem permissão para excluir certificados.'},status_code=403)
        cert=c.execute('select id from certificates where id=?',(cid,)).fetchone()
        if not cert:return {'sucesso':False,'mensagem':'Certificado não localizado. Atualize a lista.'}
        original=BASE/'storage'/'certificados'/(cid+'.pdf')
        if original.exists():
            archive_dir=BASE/'storage'/'certificados_excluidos'
            archive_dir.mkdir(parents=True,exist_ok=True)
            archive=archive_dir/(cid+'_'+datetime.datetime.now().strftime('%Y%m%d%H%M%S')+'.pdf')
            if archive.exists():
                archive=archive_dir/(cid+'_'+uuid.uuid4().hex[:8]+'.pdf')
            os.replace(original,archive)
        try:
            c.execute('delete from certificates where id=?',(cid,))
            c.commit()
        except Exception:
            c.rollback()
            if archive and archive.exists():os.replace(archive,original)
            raise
        return {'sucesso':True,'mensagem':'Certificado excluído do painel. PDF preservado em storage/certificados_excluidos para recuperação. Inscrição e presença mantidas.'}
    except Exception:
        import logging
        logging.getLogger('forevento.certificados').exception('Falha ao excluir certificado %s',cid)
        return JSONResponse({'sucesso':False,'mensagem':'Erro interno ao excluir certificado. Confira o traceback no terminal Python e o estado do registro antes de tentar novamente.'},status_code=500)
    finally:c.close()

@app.post("/api/admin/reembolso/registrar")
async def registrar_reembolso_seguro(request:Request):
    """Registro administrativo; não executa transferência PIX."""
    d=await request.json();c=con()
    try:
        who=_session_user(c,d.get('token'))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Acesso negado.'},status_code=403)
        if str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            p=c.execute('select enabled from user_permissions where user_id=? and permission=?',(who['id'],'financeiro_reembolso')).fetchone()
            if p is None:p=c.execute('select enabled from role_permissions where role=? and permission=?',(str(who['role']).upper(),'financeiro_reembolso')).fetchone()
            if not p or not p['enabled']:
                return JSONResponse({'sucesso':False,'mensagem':'Sem permissão para reembolso.'},status_code=403)
        ident=str(d.get('idPagamento') or '')
        if not re.fullmatch(r'REC:[0-9]+',ident):
            return JSONResponse({'sucesso':False,'mensagem':'Identificador inválido.'},status_code=400)
        rc=c.execute("""select rc.*,r.user_id from receipts rc
            left join registrations r on r.id=rc.registration_id
            where rc.id=? and rc.event_id=? and upper(trim(rc.status))='CONFIRMADO' """,
            (int(ident[4:]),str(d.get('idEvento') or ''))).fetchone()
        if not rc:return JSONResponse({'sucesso':False,'mensagem':'Pagamento confirmado não encontrado.'},status_code=404)
        presence=c.execute("""select status from attendance where event_id=? and activity=?
           and (user_id=? or lower(email)=lower(?)) order by id desc limit 1""",
           (rc['event_id'],rc['activity'],rc['user_id'],rc['email'])).fetchone()
        if presence and str(presence['status'] or '').upper().strip() in ('PRESENTE','PRESENÇA','PRESENCA','CONFIRMADO','CONFIRMADA'):
            return JSONResponse({'sucesso':False,'mensagem':'Reembolso bloqueado: presença confirmada.'},status_code=409)
        if c.execute('select 1 from refunds where payment_id=?',(ident,)).fetchone():
            return JSONResponse({'sucesso':False,'mensagem':'Reembolso já registrado.'},status_code=409)
        note=str(d.get('observacao') or '').strip()
        if len(note)<5:return JSONResponse({'sucesso':False,'mensagem':'Informe uma observação com pelo menos 5 caracteres.'},status_code=400)
        rid='REB-'+uuid.uuid4().hex[:10].upper()
        c.execute("""insert into refunds(id,payment_id,user_id,event_id,activity,value,proof_name,proof_data,note,created_at)
          values(?,?,?,?,?,?,?,?,?,?)""",(rid,ident,rc['user_id'] or '',rc['event_id'],rc['activity'],
          float(rc['value'] or 0),'','',note+' | Registrado por: '+str(who['id']),now()))
        c.commit()
        return {'sucesso':True,'mensagem':'Reembolso registrado administrativamente. Confirme a devolução PIX fora do sistema.','id':rid}
    finally:c.close()

@app.post("/api/admin/reembolso/comprovante")
async def comprovante_reembolso_seguro(request:Request):
    d=await request.json();c=con()
    try:
        who=_session_user(c,d.get('token'))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Acesso negado.'},status_code=403)
        ident=str(d.get('idPagamento') or '')
        if not re.fullmatch(r'REC:[0-9]+',ident):return JSONResponse({'sucesso':False,'mensagem':'Identificador inválido.'},status_code=400)
        rc=c.execute('select file_name,file_data from receipts where id=?',(int(ident[4:]),)).fetchone()
        if not rc or not rc['file_data']:return JSONResponse({'sucesso':False,'mensagem':'Comprovante indisponível.'},status_code=404)
        return {'sucesso':True,'nomeArquivo':rc['file_name'] or 'comprovante','base64':rc['file_data']}
    finally:c.close()

@app.post('/api/admin/financeiro/consulta')
async def consultar_financeiro_autenticado(request:Request):
    d=await request.json();c=con()
    try:
        who=_session_user(c,str(d.get('token') or ''))
        if not who or str(who['role']).upper()=='PARTICIPANTE':
            return JSONResponse({'sucesso':False,'mensagem':'Acesso negado.'},status_code=403)
        role=str(who['role']).upper()
        perm='financeiro_reembolso' if d.get('modulo')=='reembolso' else 'financeiro_auditoria'
        if role!='ADMINISTRADOR_MASTER':
            p=c.execute('select enabled from user_permissions where user_id=? and permission=?',(who['id'],perm)).fetchone()
            if p is None:p=c.execute('select enabled from role_permissions where role=? and permission=?',(role,perm)).fetchone()
            if not p or not p['enabled']:
                return JSONResponse({'sucesso':False,'mensagem':'Sem permissão para esta consulta.'},status_code=403)
        eid=str(d.get('idEvento') or '').strip()
        if not eid:return JSONResponse({'sucesso':False,'mensagem':'Selecione um evento.'},status_code=400)
        from .financial_queries import rows
        status=str(d.get('situacao') or 'todos').lower()
        kind='refund' if d.get('modulo')=='reembolso' else 'audit'
        if status not in (('todos','pago','pendente') if kind=='audit' else ('todos','pago','reembolsado')):
            return JSONResponse({'sucesso':False,'mensagem':'Situação inválida.'},status_code=400)
        search=str(d.get('tipoBusca') or 'todos').lower()
        if search not in ('todos','nome','id'):return JSONResponse({'sucesso':False,'mensagem':'Filtro inválido.'},status_code=400)
        items=rows(c,eid,status,search,str(d.get('termo') or '').strip(),str(d.get('inicio') or ''),str(d.get('fim') or ''),kind)
        return {'sucesso':True,'itens':items}
    finally:c.close()


@app.post("/api/admin/financeiro/eventos")
async def eventos_financeiros_filtrados(request: Request):
    """Lista eventos do SQLite sem depender do adaptador legado do Apps Script."""
    data=await request.json()
    token=str(data.get("token") or "")
    situacao=str(data.get("situacao") or "ativo").strip().lower()
    if situacao not in ("ativo","encerrado","arquivado"):
        return JSONResponse({"sucesso":False,"mensagem":"Situação de evento inválida."},status_code=400)
    c=con()
    try:
        who=_session_user(c,token)
        if not who or str(who["role"] or "").upper()=="PARTICIPANTE":
            return JSONResponse({"sucesso":False,"mensagem":"Sessão administrativa inválida."},status_code=403)
        rows=c.execute("SELECT id,name,status FROM events ORDER BY name").fetchall()
        grupos={
            "ativo":{"PUBLICADO","ATIVO","EM_ANDAMENTO","ABERTO"},
            "encerrado":{"ENCERRADO","FINALIZADO","CONCLUIDO","CONCLUÍDO"},
            "arquivado":{"ARQUIVADO","ARQUIVADA"},
        }
        # Estados legados podem usar variações de grafia. Nunca descartar
        # eventos sem status reconhecido silenciosamente: rascunhos não são ativos.
        grupos["ativo"].update({"PUBLICADA","PUBLICADO","ATIVA","ABERTA","INSCRICOES_ABERTAS","INSCRIÇÕES_ABERTAS"})
        grupos["encerrado"].update({"ENCERRADA","FINALIZADA","CONCLUIDA","CONCLUÍDA","FECHADO","FECHADA"})
        grupos["arquivado"].update({"ARQUIVADO","ARQUIVADA"})
        eventos=[{"id":r["id"],"nome":r["name"],"status":r["status"]}
                 for r in rows if str(r["status"] or "").strip().upper() in grupos[situacao]]
        return {"sucesso":True,"eventos":eventos}
    except Exception:
        return JSONResponse({"sucesso":False,"mensagem":"Falha ao consultar eventos no banco de dados."},status_code=500)
    finally:
        c.close()


# Configuração SMTP separada do banco e indisponível nas rotas públicas.
@app.post("/api/admin/certificados/smtp")
async def cert_smtp_admin(request:Request):
    from .cert_delivery import smtp_config_load, smtp_config_save, smtp_test
    body=await request.json()
    c=con()
    try:
        who=_session_user(c,str(body.get('token') or ''))
        if not who or str(who['role']).upper()!='ADMINISTRADOR_MASTER':
            return JSONResponse({'sucesso':False,'mensagem':'Somente o Administrador Master pode configurar SMTP.'},status_code=403)
    finally:c.close()
    op=str(body.get('acao') or 'consultar')
    if op=='consultar':
        cfg=smtp_config_load(BASE)
        return {'sucesso':True,'config':{k:v for k,v in cfg.items() if k!='password'},'senhaConfigurada':bool(cfg.get('password'))}
    if op=='salvar':
        try: smtp_config_save(BASE,body.get('config') or {})
        except (ValueError,OSError) as exc:return JSONResponse({'sucesso':False,'mensagem':str(exc)},status_code=400)
        return {'sucesso':True,'mensagem':'Configuração SMTP salva no servidor.'}
    if op=='testar':
        try:return smtp_test(BASE,str(body.get('destinatario') or '').strip())
        except Exception:return {'sucesso':False,'mensagem':'Falha no teste SMTP. Confira servidor, porta e credenciais.'}
    return JSONResponse({'sucesso':False,'mensagem':'Operação inválida.'},status_code=400)

@app.post("/api/call/{name}")
async def api_call(name:str,request:Request):
    try:
        body=await request.json(); args=body.get("args",[])
        # As configurações de permissões são alteráveis somente pelo Master.
        # Não confiar no menu oculto como controle de segurança.
        master_only={'salvarTema','salvarPermissoes','salvarPermissoesIndividuais','salvarPermissaoIndividual','restaurarPermissoesCategoria'}
        if name in master_only | {'substituirModeloCertificado','excluirModeloCertificado','salvarModeloCertificado'}:
            c=con()
            try:
                who=_session_user(c,str(body.get('token') or ''))
                if not who or str(who['role']).upper()!='ADMINISTRADOR_MASTER':
                    return JSONResponse({'__error':'Somente o Administrador Master pode alterar permissões.'},status_code=403)
            finally:c.close()
        if name=='enviarCertificadoPorEmailAdmin':
            from .cert_delivery import enviar_certificado
            c=con()
            try:
                who=_session_user(c,str(body.get('token') or ''))
                if not who or str(who['role']).upper()=='PARTICIPANTE':
                    return JSONResponse({'__error':'Sessão administrativa inválida.'},status_code=403)
                if str(who['role']).upper()!='ADMINISTRADOR_MASTER':
                    role=str(who['role']).upper()
                    perm=c.execute('select enabled from user_permissions where user_id=? and permission=?',(who['id'],'cert_enviar')).fetchone()
                    if perm is None: perm=c.execute('select enabled from role_permissions where role=? and permission=?',(role,'cert_enviar')).fetchone()
                    if not perm or not int(perm['enabled']):
                        return JSONResponse({'__error':'Sem permissão para enviar certificados.'},status_code=403)
                cid=str(args[0] if args else '')
                opts=args[1] if len(args)>1 and isinstance(args[1],dict) else {}
                return {'result':enviar_certificado(c,BASE,cid,opts)}
            finally:c.close()
        if name=='registrarReembolso':
            return JSONResponse({'__error':'Utilize a operação autenticada de reembolso.'},status_code=403)
        fn=({"substituirModeloCertificado":substituirModeloCertificado}.get(name) or REG.get(name))
        result=fn(args) if fn else neutral(name,args)
        return {"result":result}
    except Exception as e:
        return JSONResponse({"__error":str(e)},status_code=500)


# Módulo de participante recuperado do fluxo Apps Script.
# Endpoints separados: identidade obtida da sessão, nunca do email enviado pelo navegador.
def _participant_from_payload(c, data):
    who=_session_user(c,str(data.get('token') or ''))
    if not who or str(who['role']).upper()!='PARTICIPANTE':return None
    return who

def _activity_name(row):
    return str(row['synopsis_activity'] or row['speaker'] or '').strip()

def titulo_atividade_para_exibicao(c, event_id, chave_antiga):
    """Resolve título sem alterar a chave usada por inscrições/presenças/pagamentos."""
    rows=c.execute("select titulo,synopsis_activity,speaker from schedules where event_id=?",(event_id,)).fetchall()
    matches=[r for r in rows if str(chave_antiga or '').strip() and
             str(chave_antiga).strip() in (str(r['synopsis_activity'] or '').strip(),str(r['speaker'] or '').strip())]
    return str(matches[0]['titulo'] or '').strip() if len(matches)==1 and matches[0]['titulo'] else str(chave_antiga or '')

def _active_count(c,eid,activity):
    return c.execute("select count(*) from registrations where event_id=? and activity=? and upper(status) not in ('CANCELADO','CANCELADA','REEMBOLSADO')",(eid,activity)).fetchone()[0]

def _event_payload(c):
    evs=c.execute("select * from events where upper(status)='PUBLICADO' order by name").fetchall()
    return [{'id':e['id'],'nome':e['name'],'imagem':e['image'],'resumo':e['short_synopsis'] or e['summary'],
             'periodo':e['period'],'local':e['location']} for e in evs]

@app.post('/api/participante/portal')
async def participante_portal(request:Request):
    data=await request.json();c=con()
    try:
        who=_participant_from_payload(c,data)
        if not who:return JSONResponse({'erro':'Sessão inválida. Faça login novamente.'},status_code=401)
        eid=str(data.get('evento') or '')
        if eid:
            ev=c.execute("select id from events where id=? and upper(status)='PUBLICADO'",(eid,)).fetchone()
            if not ev:return JSONResponse({'erro':'Evento não disponível.'},status_code=404)
            rows=c.execute('select * from schedules where event_id=? order by date,time,id',(eid,)).fetchall()
            activities=[]
            for a in rows:
                name=_activity_name(a)
                count=_active_count(c,eid,name)
                mine=c.execute("select r.id,r.status,rc.status receipt_status,rc.file_name from registrations r left join receipts rc on rc.id=(select max(id) from receipts where registration_id=r.id) where r.user_id=? and r.event_id=? and r.activity=? and upper(r.status)!='CANCELADO' order by r.created_at desc limit 1",(who['id'],eid,name)).fetchone()
                modality=str(a['modality'] or '').lower()
                cap=int(a['capacity'] or 0)
                activities.append({'id':a['id'],'nome':name,'data':a['date'],'hora':a['time'],'horaTermino':a['end_time'],'tipo':a['type'],'local':a['location'],'ministrante':a['speaker'],'titulo':a['titulo'] or name,
                  'ementa':a['syllabus'],'curriculo':a['curriculum'],'sinopse':a['synopsis'],'modalidade':a['modality'],'enderecoEletronico':a['electronic_address'],
                  'modeloPreco':a['price_model'],'precoValor':float(a['price'] or 0),'vagas':cap,'inscritos':count,
                  'vagasDisponiveis':max(0,cap-count) if cap else None,'online':modality=='online',
                  'inscricao':dict(mine) if mine else None})
            return {'atividades':activities}
        regs=c.execute("select r.id,r.event_id,e.name evento,r.activity,r.status,r.created_at,rc.status recibo,rc.file_name comprovante from registrations r left join events e on e.id=r.event_id left join receipts rc on rc.id=(select max(id) from receipts where registration_id=r.id) where r.user_id=? and upper(r.status)!='CANCELADO' order by r.created_at desc",(who['id'],)).fetchall()
        # Passaporte: uma inscrição por atividade, enriquecida com cronograma.
        # Não confundir comprovante enviado com pagamento confirmado.
        passaportes=[]
        for r in regs:
            status=str(r['status'] or '').upper()
            receipt=str(r['recibo'] or '').upper()
            if status not in ('CONFIRMADO','PENDENTE'):
                continue
            ev=c.execute('select id,name,location from events where id=?',(r['event_id'],)).fetchone()
            # Compatibilidade entre registros antigos e cronogramas migrados.
            # Não associar atividades diferentes por similaridade aproximada.
            import unicodedata
            def chave_atividade(value):
                value=unicodedata.normalize('NFKD',str(value or ''))
                return ' '.join(''.join(ch for ch in value if not unicodedata.combining(ch)).casefold().split())
            candidatos=c.execute('select * from schedules where event_id=? order by date,time,id',(r['event_id'],)).fetchall()
            registro_nome=chave_atividade(r['activity'])
            correspondentes=[item for item in candidatos if registro_nome and registro_nome in {
                chave_atividade(item['synopsis_activity']),
                chave_atividade(item['synopsis']),
                chave_atividade(item['speaker']) if not item['synopsis_activity'] else ''
            }]
            # Um vínculo ambíguo não deve exibir sala/data de outra atividade.
            schedule=correspondentes[0] if len(correspondentes)==1 else None
            a=dict(schedule) if schedule else {}
            paid=(str(a.get('price_model') or '').upper() in ('PAGA','PAGO') and float(a.get('price') or 0)>0)
            # Nunca anunciar CONFIRMADO se a inscrição ainda está pendente.
            pending=status=='PENDENTE' and receipt!='CONFIRMADO'
            passaportes.append({'idInscricao':r['id'],'idEvento':r['event_id'],
                'nomeEvento':ev['name'] if ev else (r['evento'] or r['event_id']),
                'localEvento':ev['location'] if ev else '',
                'categoria':a.get('titulo') or r['activity'],'dataAtividade':a.get('date') or '',
                'horaAtividade':a.get('time') or '', 'horaTermino':a.get('end_time') or '',
                'ministranteAtividade':a.get('speaker') or '',
                'salaAtividade':a.get('location') or '',
                'modalidadeAtividade':a.get('modality') or 'Presencial',
                'enderecoEletronicoAtividade':a.get('electronic_address') or '',
                'statusInscricao':status,'comprovanteEnviado':bool(r['comprovante']),
                'comprovanteStatus':receipt,'pago':paid,'aguardandoConfirmacao':pending,
                'dadosCronogramaEncontrados':bool(schedule),
                'cronogramaAmbiguo':len(correspondentes)>1})
        passaportes.sort(key=lambda r:(r['nomeEvento'].casefold(),str(r['dataAtividade']),str(r['horaAtividade']),str(r['categoria'])))
        # Nome do evento associado a cada certificado, sem alterar certificados nem o banco.
        certs=c.execute('''select cert.id,cert.event_id,cert.activity,cert.status,cert.language,
                    cert.file_url,cert.validation_code,ev.name as event_name
                    from certificates cert left join events ev on ev.id=cert.event_id
                    where cert.user_id=? order by cert.created_at desc''',(who['id'],)).fetchall()
        return {'eventos':_event_payload(c),'inscricoes':[dict(r) for r in regs],'certificados':[dict(r) for r in certs], 'passaportes':passaportes, 'usuario':{'nome':who['name'],'id':who['id']}}
    finally:c.close()

@app.post('/api/participante/inscricao')
async def participante_inscricao(request:Request):
    data=await request.json();eid=str(data.get('evento') or '');activity_id=data.get('atividade_id');operation=str(data.get('acao') or '')
    c=con()
    try:
        c.execute('BEGIN IMMEDIATE')
        who=_participant_from_payload(c,data)
        if not who:return JSONResponse({'erro':'Sessão inválida.'},status_code=401)
        ev=c.execute("select id from events where id=? and upper(status)='PUBLICADO'",(eid,)).fetchone()
        a=c.execute('select * from schedules where id=? and event_id=?',(activity_id,eid)).fetchone()
        if not ev or not a:return JSONResponse({'erro':'Evento ou atividade indisponível.'},status_code=404)
        name=_activity_name(a)
        current=c.execute("select * from registrations where user_id=? and event_id=? and activity=? and upper(status)!='CANCELADO' order by created_at desc limit 1",(who['id'],eid,name)).fetchone()
        if operation=='cancelar':
            if not current:return JSONResponse({'erro':'Inscrição ativa não encontrada.'},status_code=409)
            c.execute("update registrations set status='CANCELADO' where id=?",(current['id'],));c.commit()
            return {'sucesso':True,'mensagem':'Inscrição cancelada. Histórico preservado.'}
        if operation!='inscrever':return JSONResponse({'erro':'Ação inválida.'},status_code=400)
        if current:return JSONResponse({'erro':'Você já possui inscrição nesta atividade.'},status_code=409)
        raw_date=str(a['date'] or '').strip()
        try:
            if re.fullmatch(r'\d{2}/\d{2}/\d{4}',raw_date):
                d=datetime.datetime.strptime(raw_date,'%d/%m/%Y').date()
            else:
                d=datetime.date.fromisoformat(raw_date[:10])
            if d<datetime.date.today():return JSONResponse({'erro':'Inscrições encerradas para esta atividade.'},status_code=409)
        except ValueError:
            return JSONResponse({'erro':'Data da atividade inválida. Solicite a correção ao organizador.'},status_code=409)
        cap=int(a['capacity'] or 0)
        if str(a['modality'] or '').lower()!='online' and cap>0 and _active_count(c,eid,name)>=cap:
            return JSONResponse({'erro':'Atividade esgotada.'},status_code=409)
        paid=str(a['price_model'] or '').upper().strip() in ('PAGA','PAGO') and float(a['price'] or 0)>0
        rid='INS-'+uuid.uuid4().hex[:10].upper()
        c.execute('insert into registrations(id,user_id,email,event_id,activity,type,status,created_at) values(?,?,?,?,?,?,?,?)',
          (rid,who['id'],who['email'],eid,name,'Participante','PENDENTE' if paid else 'CONFIRMADO',now()))
        pix=c.execute('select * from pix_config where event_id=?',(eid,)).fetchone() if paid else None
        c.commit()
        return {'sucesso':True,'idInscricao':rid,'paga':paid,'status':'PENDENTE' if paid else 'CONFIRMADO',
          'pagamento':{'valor':float(a['price'] or 0),'chavePix':pix['pix_key'] if pix else '', 'beneficiario':pix['receiver'] if pix else ''} if paid else None}
    except sqlite3.Error:
        c.rollback();return JSONResponse({'erro':'Não foi possível registrar a inscrição.'},status_code=500)
    finally:c.close()

@app.post('/api/participante/comprovante')
async def participante_comprovante(request:Request):
    data=await request.json();rid=str(data.get('inscricao') or '');filename=str(data.get('nomeArquivo') or '')[:180]
    content=str(data.get('base64') or '')
    if not filename or not content or len(content)>8_000_000:return JSONResponse({'erro':'Comprovante ausente ou muito grande (limite aproximado de 5 MB).'},status_code=400)
    if not filename.lower().endswith(('.pdf','.png','.jpg','.jpeg')):return JSONResponse({'erro':'Formato não permitido.'},status_code=400)
    try:
        import base64 as _b64
        _b64.b64decode(content,validate=True)
    except Exception:return JSONResponse({'erro':'Arquivo inválido.'},status_code=400)
    c=con()
    try:
        who=_participant_from_payload(c,data)
        if not who:return JSONResponse({'erro':'Sessão inválida.'},status_code=401)
        r=c.execute("select * from registrations where id=? and user_id=? and upper(status)='PENDENTE'",(rid,who['id'])).fetchone()
        if not r:return JSONResponse({'erro':'Inscrição pendente não encontrada.'},status_code=404)
        existing=c.execute("select 1 from receipts where registration_id=? and upper(status)='CONFIRMADO'",(rid,)).fetchone()
        if existing:return JSONResponse({'erro':'Pagamento já confirmado.'},status_code=409)
        a=c.execute('select price from schedules where event_id=? and synopsis_activity=? limit 1',(r['event_id'],r['activity'])).fetchone()
        c.execute("insert into receipts(registration_id,event_id,email,activity,value,file_name,file_data,status,sent_at) values(?,?,?,?,?,?,?,?,?)",
          (rid,r['event_id'],who['email'],r['activity'],float(a['price'] or 0) if a else 0,filename,content,'PENDENTE',now()))
        c.commit();return {'sucesso':True,'mensagem':'Comprovante enviado. Aguardando confirmação financeira.'}
    finally:c.close()
