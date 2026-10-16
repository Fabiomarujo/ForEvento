from sqlalchemy import inspect, text
from .db import engine

# Migrações leves para o SQLite de DESENVOLVIMENTO.
# Em produção/PostgreSQL, a implantação deverá usar Alembic.
EVENT_COLUMNS = {
    "code": "VARCHAR(30) DEFAULT ''",
    "cover_path": "VARCHAR(500) DEFAULT ''",
    "summary": "TEXT DEFAULT ''",
    "period": "VARCHAR(100) DEFAULT ''",
    "location": "VARCHAR(180) DEFAULT ''",
    "capacity": "INTEGER DEFAULT 0",
    "keyword": "VARCHAR(80) DEFAULT 'GERAL'",
    "schedule_synopsis": "TEXT DEFAULT ''",
    "status": "VARCHAR(40) DEFAULT 'RASCUNHO'",
    "payment_mode": "VARCHAR(20) DEFAULT 'MANUAL'",
    "pix_key": "VARCHAR(180) DEFAULT ''",
    "pix_receiver": "VARCHAR(180) DEFAULT ''",
    "pix_provider": "VARCHAR(80) DEFAULT ''",
    "pix_environment": "VARCHAR(30) DEFAULT 'TESTE'",
    "payment_deadline_minutes": "INTEGER DEFAULT 20",
    "created_at": "DATETIME"
}
USER_COLUMNS = {
    "role": "VARCHAR(60) DEFAULT 'Participante'",
    "phone": "VARCHAR(30) DEFAULT ''",
    "language": "VARCHAR(5) DEFAULT 'pt'",
    "access_status": "VARCHAR(20) DEFAULT 'AUTORIZADO'",
    "created_at": "DATETIME"
}

def _add_missing(table, columns):
    insp=inspect(engine)
    if table not in insp.get_table_names(): return
    current={c["name"] for c in insp.get_columns(table)}
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in current:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))

def migrate_dev_schema():
    if engine.dialect.name != "sqlite":
        return
    _add_missing("events", EVENT_COLUMNS)
    _add_missing("users", USER_COLUMNS)
    # Garante códigos não vazios em registros antigos.
    with engine.begin() as conn:
        rows=conn.execute(text("SELECT id, code, status FROM events")).fetchall() if "events" in inspect(engine).get_table_names() else []
        for row in rows:
            if not row.code:
                conn.execute(text("UPDATE events SET code=:c WHERE id=:id"),{"c":f"RASC-LEGADO-{row.id:05d}","id":row.id})
