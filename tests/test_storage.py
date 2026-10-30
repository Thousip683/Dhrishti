from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import os
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.engine import make_url
from carbon_coach.api import app
from carbon_coach import domain
from carbon_coach.db_models import Base, SessionRow, CalculationRow, ActivityRow, IdempotencyRow, CorrectionRow
from carbon_coach.storage import DatabaseRepository, SessionRecord

@pytest.fixture(params=['sqlite'] + (['postgresql'] if os.getenv('TEST_POSTGRES_ADMIN_URL') else []))
def database(tmp_path, request):
    url='sqlite:///'+str(tmp_path/'ledger.db').replace('\\','/')
    database_name=None
    if request.param=='postgresql':
        import psycopg
        from psycopg import sql
        database_name='carbon_test_'+uuid4().hex
        with psycopg.connect(os.environ['TEST_POSTGRES_ADMIN_URL'],autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
        url=str(make_url(os.environ['TEST_POSTGRES_ADMIN_URL']).set(drivername='postgresql+psycopg',database=database_name))
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    config.attributes['database_url']=url
    command.upgrade(config,'head')
    repo=DatabaseRepository(url)
    previous=app.state.repository
    app.state.repository=repo
    try:
        yield repo,url
    finally:
        app.state.repository=previous
        repo.engine.dispose()
        if database_name:
            # Drop only the exact disposable database created by this fixture.
            assert database_name.startswith('carbon_test_') and len(database_name)==44
            with psycopg.connect(os.environ['TEST_POSTGRES_ADMIN_URL'],autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database_name)))

def session(client):
    result=client.post('/api/v1/sessions',json={})
    assert result.status_code==201,result.text
    assert result.json()['storage_mode']=='database'
    return result.json()['session_id'],{'Authorization':'Bearer '+result.json()['session_token']}

def calculate(client,sid,headers,km='12'):
    result=client.post(f'/api/v1/sessions/{sid}/calculations',headers={**headers,'Idempotency-Key':str(uuid4())},
        json={'category':'travel','input':{'mode':'bus','distance_km':km}})
    assert result.status_code==201,result.text
    return result.json()['calculation']

def log(client,sid,h,cid,headers=None):
    return client.post(f'/api/v1/sessions/{sid}/activities',headers=headers or {**h,'Idempotency-Key':str(uuid4())},
        json={'calculation_id':cid,'activity_date':'2026-10-01'})

def test_schema_matches_migration(database):
    repo,_=database
    assert repo.ready()
    with repo.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection),Base.metadata)==[]

def test_records_and_idempotency_survive_repository_restart(database):
    repo,url=database
    with TestClient(app) as c:
        sid,h=session(c)
        calc=calculate(c,sid,h)
        headers={**h,'Idempotency-Key':str(uuid4())}
        original=log(c,sid,h,calc['id'],headers)
        assert original.status_code==201,original.text
    repo.engine.dispose()
    restarted=DatabaseRepository(url)
    app.state.repository=restarted
    try:
        with TestClient(app) as c:
            assert log(c,sid,h,calc['id'],headers).json()==original.json()
            result=c.get(f'/api/v1/sessions/{sid}/summary?period=custom&start_date=2026-10-01&end_date=2026-10-02',headers=h)
            assert result.json()['summary']['total_kg_co2e']=='1.246200'
    finally:
        restarted.engine.dispose()

def test_parallel_retries_commit_exactly_once(database):
    with TestClient(app) as c:
        sid,h=session(c)
        calc=calculate(c,sid,h)
        headers={**h,'Idempotency-Key':str(uuid4())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:log(c,sid,h,calc['id'],headers),range(2)))
        assert all(r.status_code in (201,409) for r in results)
        results=[log(c,sid,h,calc['id'],headers) if r.status_code==409 else r for r in results]
        assert [r.status_code for r in results]==[201,201]
        assert results[0].json()==results[1].json()
        activities=c.get(f'/api/v1/sessions/{sid}/activities',headers=h).json()['items']
        assert len(activities)==1

def test_correction_lineage_and_superseded_receipt(database):
    repo,_=database
    with TestClient(app) as c:
        sid,h=session(c)
        first=calculate(c,sid,h)
        a=log(c,sid,h,first['id']).json()['activity']
        replacement=calculate(c,sid,h,'8')
        response=c.patch(f'/api/v1/sessions/{sid}/activities/{a["id"]}',headers={**h,'Idempotency-Key':str(uuid4()),'If-Match':'1'},json={'calculation_id':replacement['id']})
        assert response.status_code==200,response.text
        assert response.json()['activity']['kg_co2e']=='0.830800'
        assert log(c,sid,h,first['id']).status_code==409
    with DBSession(repo.engine) as db:
        assert db.get(CalculationRow,first['id']).lifecycle=='superseded'
        assert db.scalar(select(func.count()).select_from(CorrectionRow))==1

def test_transaction_rollback_keeps_ledger_and_cache_together(database):
    repo,_=database
    with TestClient(app) as c:
        sid,h=session(c)
    tx=repo.begin(sid)
    record=tx[sid]
    calc=domain.calculate(record.ledger,'travel',{'mode':'bus','distance_km':'12'})
    domain.log(record.ledger,calc['id'],'2026-10-01')
    record.cache['aborted-key']=('fingerprint',{'status':'success'})
    tx.rollback()
    tx.close()
    next_tx=repo.begin(sid)
    try:
        assert next_tx[sid].ledger['activities']==[]
        assert calc['id'] not in next_tx[sid].ledger['calculations']
        assert 'aborted-key' not in next_tx[sid].cache
    finally:
        next_tx.rollback()
        next_tx.close()

def test_erasure_cascades_and_expiry_cleanup(database):
    repo,_=database
    with TestClient(app) as c:
        sid,h=session(c)
        calc=calculate(c,sid,h)
        assert log(c,sid,h,calc['id']).status_code==201
        assert c.delete(f'/api/v1/sessions/{sid}',headers=h).status_code==204
    with DBSession(repo.engine) as db:
        for model in (SessionRow,CalculationRow,ActivityRow,IdempotencyRow,CorrectionRow):
            assert db.scalar(select(func.count()).select_from(model))==0
    tx=repo.begin()
    tx['expired']=SessionRecord(sha256(b'test-token').hexdigest(),{'timezone':'Asia/Kolkata'},datetime.now(timezone.utc)-timedelta(seconds=1))
    tx.commit()
    tx.close()
    assert repo.cleanup_expired()==['expired']

def test_database_ownership_and_stale_revision(database):
    with TestClient(app) as c:
        sid,h=session(c)
        other,other_h=session(c)
        calc=calculate(c,sid,h)
        assert log(c,other,other_h,calc['id']).status_code==404
        a=log(c,sid,h,calc['id']).json()['activity']
        assert c.patch(f'/api/v1/sessions/{sid}/activities/{a["id"]}',headers={**h,'Idempotency-Key':str(uuid4()),'If-Match':'99'},json={'note':'stale'}).status_code==412
        assert c.get(f'/api/v1/sessions/{sid}/activities/{a["id"]}',headers=other_h).status_code==404

def test_browser_bootstrap_and_cookie_session_survive_restart(database):
    repo,url=database
    with TestClient(app) as c:
        bootstrap=c.get('/api/v1/browser/bootstrap').json()
        headers={'Origin':'http://127.0.0.1:8001','X-CSRF-Token':bootstrap['csrf_token'],'Idempotency-Key':str(uuid4())}
        metadata=c.post('/api/v1/browser/session',headers=headers,json={'timezone':'UTC'}).json()
        assert 'session_id' in metadata,metadata
        cookies=dict(c.cookies)
    restarted=DatabaseRepository(url)
    app.state.repository=restarted
    try:
        with TestClient(app) as c:
            c.cookies.update(cookies)
            restored=c.get('/api/v1/browser/session')
            assert restored.status_code==200,restored.text
            assert restored.json()['session_id']==metadata['session_id']
            assert c.post('/api/v1/browser/session',headers=headers,json={'timezone':'UTC'}).json()['session_id']==metadata['session_id']
            assert c.delete('/api/v1/browser/session',headers=headers).status_code==204
    finally:
        restarted.engine.dispose()

def test_appliance_evidence_persists_with_saved_electricity_receipt(database):
    repo,url=database
    with TestClient(app) as c:
        sid,h=session(c)
        base=f'/api/v1/sessions/{sid}'
        energy=c.post(base+'/energy-conversions',headers={**h,'Idempotency-Key':str(uuid4())},json={'power_kw':'1.5','hours':'4','power_basis':'rated','duty_cycle':'0.5'})
        assert energy.status_code==201,energy.text
        conversion=energy.json()['conversion']
        preview=c.post(base+'/calculations',headers={**h,'Idempotency-Key':str(uuid4())},json={'category':'electricity','input':{'kwh':conversion['kwh'],'grid_region':'UK','conversion_id':conversion['id']}})
        assert preview.status_code==201,preview.text
        activity=log(c,sid,h,preview.json()['calculation']['id']).json()['activity']
    restarted=DatabaseRepository(url)
    app.state.repository=restarted
    try:
        with TestClient(app) as c:
            evidence=c.get(base+'/activities/'+activity['id'],headers=h)
            assert evidence.status_code==200,evidence.text
            assert evidence.json()['calculation']['energy_conversion']==conversion
            assert c.get(base+'/energy-conversions/'+conversion['id'],headers=h).json()['conversion']==conversion
    finally:
        restarted.engine.dispose()
