"""Backups consistentes SQLite; nunca cria/substitui o banco principal."""
import os, sqlite3, threading, json, tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOCK=threading.RLock()
BASE=Path(__file__).resolve().parent.parent
DB=Path(os.getenv('FOREVENTO_DB_PATH',str(BASE/'forevento.db'))).resolve()
DEST=Path(os.getenv('FOREVENTO_BACKUP_DIR',str(BASE.parent/'Backups_ForEvento'))).resolve()
try: TZ=ZoneInfo(os.getenv('FOREVENTO_TIMEZONE','America/Sao_Paulo'))
except ZoneInfoNotFoundError: TZ=None

def _now(): return datetime.now(TZ) if TZ else datetime.now().astimezone()
def _counts(conn):
    result={}
    for table in ('users','events','showcase_banners','registrations','attendance'):
        try: result[table]=conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
        except sqlite3.DatabaseError: result[table]=None
    return result

def _read_info(file):
    if not file.is_file() or file.stat().st_size<100:return None
    try:
        with sqlite3.connect('file:'+file.as_posix()+'?mode=ro',uri=True,timeout=10) as c:
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':return None
            return _counts(c)
    except (sqlite3.DatabaseError,OSError):return None

def _suspicious(current,previous):
    if not previous:return False
    # Não substituir backup com dados por um banco sem registros.
    return any(previous.get(k,0) and current.get(k)==0 for k in ('users','events','showcase_banners','registrations'))

def backup(kind='automatico',force=False):
    if kind not in ('automatico','manual'):raise ValueError('Tipo inválido')
    with _LOCK:
        if not DB.is_file():raise FileNotFoundError('Banco principal não encontrado; nenhuma cópia criada')
        current=_read_info(DB)
        if current is None:raise RuntimeError('Banco principal inválido; backup anterior preservado')
        DEST.mkdir(parents=True,exist_ok=True)
        target=DEST/('backup_'+kind+'.db')
        stamp=DEST/('backup_'+kind+'.json')
        now=_now(); today=now.date().isoformat()
        if kind=='automatico' and not force and target.is_file() and stamp.is_file():
            try:
                if json.loads(stamp.read_text(encoding='utf-8')).get('date')==today and _read_info(target) is not None:
                    return {'sucesso':True,'status':'ja_existe','data':today,'arquivo':str(target)}
            except (ValueError,OSError):pass
        previous=_read_info(target)
        if _suspicious(current,previous):
            raise RuntimeError('Queda inesperada de registros; backup anterior preservado. Verifique o banco principal.')
        fd,tmp=tempfile.mkstemp(prefix='.forevento_backup_',suffix='.db',dir=DEST)
        os.close(fd)
        try:
            with sqlite3.connect('file:'+DB.as_posix()+'?mode=ro',uri=True,timeout=20) as origin:
                with sqlite3.connect(tmp,timeout=20) as copy:origin.backup(copy)
            copied=_read_info(Path(tmp))
            if copied is None or copied!=current:
                raise RuntimeError('Backup não passou na verificação de integridade e contagens')
            os.replace(tmp,target)
            metadata={'date':today,'datetime':now.isoformat(),'counts':copied,'type':kind}
            temp_meta=stamp.with_suffix('.json.tmp')
            temp_meta.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp_meta,stamp)
            return {'sucesso':True,'status':'criado','data':today,'arquivo':str(target),'contagens':copied}
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

def status():
    result={}
    for kind in ('automatico','manual'):
        file=DEST/('backup_'+kind+'.db'); meta=DEST/('backup_'+kind+'.json')
        info=_read_info(file)
        details={}
        if meta.is_file():
            try:details=json.loads(meta.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        result[kind]={'existe':info is not None,'data':details.get('datetime'),'contagens':info}
    return result
