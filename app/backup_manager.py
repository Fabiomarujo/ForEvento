"""ForEvento: backup manual/agendado e restauração diferida para a próxima inicialização.
Backup é uma cópia SQLite consistente. Nunca remove backups anteriores automaticamente fora da retenção escolhida.
"""
import os, sqlite3, json, tempfile, zipfile, threading, shutil, uuid
from pathlib import Path
from datetime import datetime, timedelta
import calendar
BASE=Path(__file__).resolve().parent.parent
DB=Path(os.getenv('FOREVENTO_DB_PATH', str(BASE/'forevento.db'))).resolve()
ROOT=Path(os.getenv('FOREVENTO_BACKUP_DIR',str(BASE.parent/'Backups_ForEvento'))).resolve()
LOCK=threading.RLock()
CFG=ROOT/'forevento_backup_config.json'
PENDING=ROOT/'restauracao_pendente.json'
INTERVALS={'0','1','7','15','30','3m'}

def _valid_keep(value):
    try:
        n=int(value)
    except (TypeError,ValueError):
        return 10
    return n if 5<=n<=10 else 10

def config():
    try:
        c=json.loads(CFG.read_text(encoding='utf8'))
        return {'days':str(c.get('days',0)),'keep':_valid_keep(c.get('keep',10)),'last':c.get('last',''), 'last_auto':c.get('last_auto',''), 'last_auto_status':c.get('last_auto_status','')}
    except (OSError,ValueError,TypeError):return {'days':'0','keep':10,'last':'','last_auto':'','last_auto_status':''}

def save_config(days,keep):
    days=str(days)
    try:
        keep=int(keep)
    except (TypeError,ValueError) as exc:
        raise ValueError('Limite de backups deve estar entre 5 e 10') from exc
    if days not in INTERVALS or not 5<=keep<=10:raise ValueError('Agendamento ou retenção inválida')
    ROOT.mkdir(parents=True,exist_ok=True)
    with LOCK:
        c=config();c.update(days=days,keep=keep)
        _write_json(CFG,c)
    return c

def _write_json(path,data):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def _integrity(path):
    with sqlite3.connect('file:'+Path(path).resolve().as_posix()+'?mode=ro',uri=True,timeout=20) as c:
        return c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def create(kind='manual'):
    if kind not in ('manual','automatico'):raise ValueError('Tipo inválido')
    with LOCK:
        if not DB.is_file() or not _integrity(DB):raise RuntimeError('Banco principal ausente ou inválido')
        ROOT.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        name='forevento_'+kind+'_'+stamp+'.zip'
        final=ROOT/name
        with tempfile.TemporaryDirectory(prefix='fe_snapshot_',dir=ROOT) as td:
            snap=Path(td)/'forevento.db'
            origin=sqlite3.connect('file:'+DB.as_posix()+'?mode=ro',uri=True,timeout=30)
            target=sqlite3.connect(str(snap),timeout=30)
            try:origin.backup(target)
            finally:target.close();origin.close()
            if not _integrity(snap):raise RuntimeError('Snapshot SQLite não passou na verificação')
            tmp=Path(td)/'pacote.zip'
            with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
                z.write(snap,'forevento.db')
                for folder in ('modelos_cert','storage'):
                    root=BASE/folder
                    if root.is_dir():
                        for f in root.rglob('*'):
                            if f.is_file() and not f.is_symlink():z.write(f,f.relative_to(BASE).as_posix())
                z.writestr('manifesto.json',json.dumps({'data':datetime.now().isoformat(),'tipo':kind,'banco':'forevento.db'},ensure_ascii=False))
            with zipfile.ZipFile(tmp) as z:
                if z.testzip() is not None:raise RuntimeError('Falha na verificação do arquivo ZIP')
            os.replace(tmp,final)
        c=config();c['last']=datetime.now().isoformat();
        if kind=='automatico':c['last_auto']=c['last'];c['last_auto_status']='Concluído'
        _write_json(CFG,c)
        _prune(c.get('keep',10))
        return {'arquivo':name,'data':c['last'],'tamanho':final.stat().st_size}

def _prune(keep=10):
    keep=_valid_keep(keep)  # Somente backups automáticos, com retenção de 5 a 10
    autos=sorted(ROOT.glob('forevento_automatico_*.zip'),reverse=True)
    for f in autos[keep:]:f.unlink(missing_ok=True)

def points():
    ROOT.mkdir(parents=True,exist_ok=True)
    result=[]
    for f in sorted(ROOT.glob('forevento_*.zip'),reverse=True):
        if not f.is_file():continue
        st=f.stat()
        result.append({'arquivo':f.name,'data':datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),'tamanho':st.st_size,'tipo':'Automático' if '_automatico_' in f.name else 'Manual'})
    return result

def get_file(name):
    if not re_name(name):raise ValueError('Nome de backup inválido')
    f=ROOT/name
    if not f.is_file():raise FileNotFoundError('Backup não encontrado')
    return f

def delete_backup(name):
    """Remove somente um ZIP selecionado; nunca o banco ativo ou arquivos de dados."""
    with LOCK:
        f=get_file(name)  # valida nome e restringe à pasta de backups
        if PENDING.exists():
            try:
                pending=json.loads(PENDING.read_text(encoding='utf8'))
            except (OSError,ValueError) as exc:
                raise RuntimeError('Estado da restauração pendente ilegível; exclusão bloqueada') from exc
            if pending.get('arquivo')==name:
                raise RuntimeError('Backup reservado para restauração pendente; exclusão bloqueada')
        f.unlink()
        return {'mensagem':'Backup excluído do servidor: '+name}

def re_name(name):
    import re
    return bool(re.fullmatch(r'forevento_(?:manual|automatico)_\d{8}_\d{6}_\d{6}\.zip',str(name)))

def verify_zip(f):
    with zipfile.ZipFile(f) as z:
        if 'forevento.db' not in z.namelist() or z.testzip() is not None:raise ValueError('Backup ZIP inválido')
        if any(n.startswith('/') or '..' in Path(n).parts for n in z.namelist()):raise ValueError('Caminhos inseguros no backup')
        with tempfile.TemporaryDirectory(prefix='fe_verify_',dir=ROOT) as td:
            db=Path(td)/'forevento.db'
            with z.open('forevento.db') as inp,db.open('wb') as dest:shutil.copyfileobj(inp,dest)
            if not _integrity(db):raise ValueError('Banco SQLite do backup inválido')

def stage_restore(name):
    with LOCK:
        f=get_file(name);verify_zip(f)
        if PENDING.exists():raise RuntimeError('Já existe uma restauração aguardando reinicialização')
        _write_json(PENDING,{'arquivo':name,'solicitado':datetime.now().isoformat()})
        return {'mensagem':'Restauração validada e agendada. Reinicie o servidor ForEvento para aplicar; o banco atual será preservado em uma cópia de segurança.'}

def apply_pending_on_startup():
    if not PENDING.is_file():return
    with LOCK:
        data=json.loads(PENDING.read_text(encoding='utf8'))
        f=get_file(data['arquivo']);verify_zip(f)
        # Protege o banco atual com uma cópia independente, antes de qualquer substituição.
        rescue=create('manual')
        with tempfile.TemporaryDirectory(prefix='fe_restore_',dir=ROOT) as td:
            with zipfile.ZipFile(f) as z:
                db=Path(td)/'forevento.db'
                with z.open('forevento.db') as inp,db.open('wb') as dest:shutil.copyfileobj(inp,dest)
            if not _integrity(db):raise RuntimeError('Restauração cancelada: banco inválido')
            # Na inicialização, antes de init_db(), não há conexões do aplicativo abertas.
            replacement=DB.with_name('.forevento_restore_'+uuid.uuid4().hex+'.db')
            shutil.copy2(db,replacement)
            try:os.replace(replacement,DB)
            finally:replacement.unlink(missing_ok=True)
        PENDING.unlink()
        return rescue

def _add_months(date, months):
    index=date.year*12+(date.month-1)+months
    year, month=divmod(index,12)
    month+=1
    return date.replace(year=year,month=month,day=min(date.day,calendar.monthrange(year,month)[1]))

def next_backup(c=None):
    c=c or config()
    days=str(c.get('days','0'))
    if days=='0':return None
    reference=c.get('last_auto') or c.get('last')
    try:base=datetime.fromisoformat(reference) if reference else datetime.now()
    except (ValueError,TypeError):base=datetime.now()
    if days=='3m':return _add_months(base,3)
    if days not in INTERVALS:return None
    return base+timedelta(days=int(days))

def due():
    c=config()
    if str(c['days'])=='0':return False
    if not (c.get('last_auto') or c.get('last')):return True
    nxt=next_backup(c)
    return bool(nxt and datetime.now()>=nxt)

def run_scheduler():
    import time,logging
    while True:
        try:
            if due():create('automatico')
        except Exception as exc:
            logging.exception('Backup automático do ForEvento falhou')
            with LOCK:
                c=config();c['last_auto_status']='Erro: '+str(exc)[:160];_write_json(CFG,c)
        time.sleep(3600)

def start_scheduler():
    threading.Thread(target=run_scheduler,name='ForEventoBackupScheduler',daemon=True).start()
