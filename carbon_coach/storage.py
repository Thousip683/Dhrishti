"""Transactional aggregate repositories for memory, SQLite and PostgreSQL.

SQLite intentionally serializes write transactions for the local application.
PostgreSQL locks a session row NOWAIT to coordinate requests across workers.
DB calls are run in worker threads by API middleware, never while holding the
event loop during lock acquisition or commit.
"""
import asyncio
from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from uuid import uuid4
from sqlalchemy import create_engine, delete, event, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DBSession
from .db_models import SessionRow, CalculationRow, ActivityRow, IdempotencyRow, CorrectionRow, BrowserBootstrapRow
from .domain import DomainError, fixed

@dataclass
class SessionRecord:
    token_hash: str
    ledger: dict
    expires_at: datetime
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cache: dict = field(default_factory=dict)

def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

class MemoryRepository:
    mode = 'memory'
    def __init__(self):
        self.records = {}
        self.bootstraps = {}
    def begin(self, sid=None, bootstrap_hash=None):
        return MemoryTransaction(self.records, self.bootstraps)
    def ready(self):
        return True
    def cleanup_expired(self):
        expired=[sid for sid,record in self.records.items() if record.expires_at <= datetime.now(timezone.utc) and not record.lock.locked()]
        for sid in expired:
            del self.records[sid]
        for key in [key for key,value in self.bootstraps.items() if value['session_id'] in expired]:
            del self.bootstraps[key]
        return expired

class MemoryTransaction(MutableMapping):
    def __init__(self, records, bootstraps):
        self.records = records
        self.bootstraps = bootstraps
    def __getitem__(self,key): return self.records[key]
    def __setitem__(self,key,value): self.records[key]=value
    def __delitem__(self,key):
        del self.records[key]
        for nonce in [nonce for nonce,value in self.bootstraps.items() if value['session_id']==key]:
            del self.bootstraps[nonce]
    def __iter__(self): return iter(self.records)
    def __len__(self): return len(self.records)
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def lookup_bootstrap(self, key): return self.bootstraps.get(key)
    def register_bootstrap(self, key, value): self.bootstraps[key]=value

class DatabaseRepository:
    mode = 'database'
    def __init__(self, url):
        if url.startswith('postgresql://'):
            url = url.replace('postgresql://','postgresql+psycopg://',1)
        self.engine = create_engine(url, pool_pre_ping=True,
            connect_args={'check_same_thread':False,'timeout':2} if url.startswith('sqlite:') else {})
        if self.engine.dialect.name == 'sqlite':
            @event.listens_for(self.engine,'connect')
            def sqlite_options(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA journal_mode=WAL')
    def begin(self,sid=None,bootstrap_hash=None):
        try:
            return DatabaseTransaction(self.engine,sid,bootstrap_hash)
        except OperationalError as exc:
            code=getattr(exc.orig,'sqlstate',None)
            raise DomainError('SESSION_BUSY' if code=='55P03' else 'STORAGE_UNAVAILABLE',
                'Session is busy; retry this request with the same idempotency key.' if code=='55P03' else 'Database unavailable or busy. Retry shortly.',409 if code=='55P03' else 503) from None
    def ready(self):
        try:
            names=set(inspect(self.engine).get_table_names())
            return {'sessions','calculations','activities','idempotency_records','requests','activity_corrections','browser_bootstraps','alembic_version'} <= names
        except Exception:
            return False
    def cleanup_expired(self):
        with DBSession(self.engine) as db, db.begin():
            query=select(SessionRow).where(SessionRow.expires_at <= datetime.now(timezone.utc))
            if self.engine.dialect.name=='postgresql':
                query=query.with_for_update(skip_locked=True)
            rows=db.scalars(query.limit(100)).all()
            expired=[row.id for row in rows]
            for row in rows:
                db.delete(row)
            return expired

class DatabaseTransaction(MutableMapping):
    def __init__(self,engine,sid,bootstrap_hash=None):
        self.db=DBSession(engine,expire_on_commit=False)
        self.records={}
        self.original={}
        self.deleted=set()
        self.bootstraps={}
        try:
            if engine.dialect.name=='sqlite':
                self.db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            else:
                self.db.begin()
            if bootstrap_hash:
                if engine.dialect.name=='postgresql':
                    lock_id=int.from_bytes(bytes.fromhex(bootstrap_hash)[:8],signed=True)
                    if not self.db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key':lock_id}):
                        raise DomainError('SESSION_BUSY','Session creation is already processing. Retry with the same key.',409)
                row=self.db.get(BrowserBootstrapRow,bootstrap_hash)
                if row:
                    self.bootstraps[bootstrap_hash]=dict(session_id=row.session_id,payload_hash=row.payload_hash,expires_at=aware(row.expires_at))
                    sid=sid or row.session_id
            if sid:
                query=select(SessionRow).where(SessionRow.id==sid)
                if engine.dialect.name=='postgresql':
                    query=query.with_for_update(nowait=True)
                row=self.db.scalar(query)
                if row:
                    self._load(row)
        except Exception:
            self.db.rollback()
            self.db.close()
            raise
    def _load(self,row):
        ledger=deepcopy(row.context)
        calculations=self.db.scalars(select(CalculationRow).where(CalculationRow.session_id==row.id)).all()
        ledger['calculations']={c.id:deepcopy(c.receipt) for c in calculations}
        ledger['calculation_states']={c.id:c.lifecycle for c in calculations}
        ledger['activities']=[]
        for a in self.db.scalars(select(ActivityRow).where(ActivityRow.session_id==row.id)):
            ledger['activities'].append(dict(id=a.id,calculation_id=a.calculation_id,category=a.category,
                activity_date=a.activity_date.isoformat(),kg_co2e=fixed(a.kg_co2e),note=a.note,
                revision=a.revision,deleted=a.deleted,created_at=aware(a.created_at).isoformat()))
        cache={r.key:(r.payload_hash,deepcopy(r.response)) for r in self.db.scalars(select(IdempotencyRow).where(IdempotencyRow.session_id==row.id))}
        self.records[row.id]=SessionRecord(row.token_hash,ledger,aware(row.expires_at),cache=cache)
        self.original[row.id]=deepcopy(ledger)
    def __getitem__(self,key): return self.records[key]
    def __setitem__(self,key,value): self.records[key]=value
    def __delitem__(self,key):
        del self.records[key]
        self.deleted.add(key)
    def __iter__(self): return iter(self.records)
    def __len__(self): return len(self.records)
    def lookup_bootstrap(self,key): return self.bootstraps.get(key)
    def register_bootstrap(self,key,value): self.bootstraps[key]=value
    def commit(self):
        for sid in self.deleted:
            self.db.execute(delete(SessionRow).where(SessionRow.id==sid))
        for sid,record in self.records.items():
            context={key:deepcopy(value) for key,value in record.ledger.items() if key not in ('calculations','activities','calculation_states')}
            row=self.db.get(SessionRow,sid)
            if row is None:
                row=SessionRow(id=sid,token_hash=record.token_hash,context=context,expires_at=record.expires_at,revision=1)
                self.db.add(row)
            else:
                row.context=context
                row.expires_at=record.expires_at
                row.revision+=1
            self.db.flush()
            states=record.ledger.get('calculation_states',{})
            for cid,receipt in record.ledger.get('calculations',{}).items():
                self.db.merge(CalculationRow(id=cid,session_id=sid,kg_co2e=Decimal(receipt['kg_co2e']),
                    lifecycle=states.get(cid,'uncommitted'),receipt=deepcopy(receipt)))
            self.db.flush()
            before={a['id']:a for a in self.original.get(sid,{}).get('activities',[])}
            for item in record.ledger.get('activities',[]):
                self.db.merge(ActivityRow(id=item['id'],session_id=sid,calculation_id=item['calculation_id'],
                    category=item['category'],activity_date=date.fromisoformat(item['activity_date']),
                    kg_co2e=Decimal(item['kg_co2e']),note=item['note'],revision=item['revision'],
                    deleted=item['deleted'],created_at=datetime.fromisoformat(item['created_at'])))
                previous=before.get(item['id'])
                if previous and previous['calculation_id']!=item['calculation_id']:
                    self.db.add(CorrectionRow(id=str(uuid4()),session_id=sid,activity_id=item['id'],
                        previous_calculation_id=previous['calculation_id'],replacement_calculation_id=item['calculation_id'],
                        revision=item['revision'],changed_at=datetime.now(timezone.utc)))
            self.db.flush()
            for key,(fingerprint,response) in record.cache.items():
                if self.db.get(IdempotencyRow,(sid,key)) is None:
                    self.db.add(IdempotencyRow(session_id=sid,key=key,payload_hash=fingerprint,
                        response=deepcopy(response),created_at=datetime.now(timezone.utc)))
        for nonce_hash, value in self.bootstraps.items():
            if value['session_id'] not in self.deleted:
                self.db.merge(BrowserBootstrapRow(nonce_hash=nonce_hash,**value))
        self.db.commit()
    def rollback(self): self.db.rollback()
    def close(self): self.db.close()

def configured_repository():
    if os.getenv('STORAGE_MODE','database')=='memory':
        return MemoryRepository()
    return DatabaseRepository(os.getenv('DATABASE_URL','sqlite:///./carbon_coach.db'))
