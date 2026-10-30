from uuid import uuid4
from fastapi.testclient import TestClient
from carbon_coach.api import app

def session(client):
    result=client.post('/api/v1/sessions',json={}).json()
    return result['session_id'], {'Authorization':'Bearer '+result['session_token']}

def key(headers):
    return {**headers,'Idempotency-Key':str(uuid4())}

def test_flow_retries_correction_and_delete():
    with TestClient(app) as c:
        sid,h=session(c)
        base=f'/api/v1/sessions/{sid}'
        calc_headers=key(h)
        payload={'category':'travel','input':{'mode':'bus','distance_km':'12'}}
        first=c.post(base+'/calculations',headers=calc_headers,json=payload)
        assert first.status_code==201
        assert c.post(base+'/calculations',headers=calc_headers,json=payload).json()==first.json()
        assert c.post(base+'/calculations',headers=calc_headers,json={**payload,'input':{'mode':'bus','distance_km':'5'}}).status_code==409
        calc=first.json()['calculation']
        log_headers=key(h)
        body={'calculation_id':calc['id'],'activity_date':'2026-10-01'}
        a=c.post(base+'/activities',headers=log_headers,json=body).json()['activity']
        assert c.post(base+'/activities',headers=log_headers,json=body).json()['activity']['id']==a['id']
        assert c.post(base+'/activities',headers=key(h),json=body).status_code==409
        result=c.get(base+'/summary?period=custom&start_date=2026-10-01&end_date=2026-10-02',headers=h).json()
        assert result['summary']['total_kg_co2e']=='1.246200'
        patched=c.patch(base+'/activities/'+a['id'],headers={**key(h),'If-Match':'1'},json={'note':'Corrected note'})
        assert patched.status_code==200 and patched.json()['activity']['revision']==2
        assert c.delete(base+'/activities/'+a['id'],headers={**h,'If-Match':'1'}).status_code==412
        assert c.delete(base+'/activities/'+a['id'],headers={**h,'If-Match':'2'}).status_code==204
        assert c.get(base+'/activities',headers=h).json()['items']==[]

def test_auth_validation_and_no_fabricated_chat(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    with TestClient(app) as c:
        sid,h=session(c)
        other,other_h=session(c)
        base=f'/api/v1/sessions/{sid}'
        assert c.get(base+'/activities').status_code==401
        assert c.get(base+'/activities',headers=other_h).status_code==404
        assert c.post(base+'/calculations',headers=key(h),json={'category':'travel','input':{'mode':'bus','distance_km':'NaN'}}).status_code==422
        assert c.post(base+'/messages',headers=key(h),json={'text':'hello'}).status_code==503
        assert c.delete(base,headers=h).status_code==204
        assert c.get(base+'/activities',headers=h).status_code==404

def test_openapi_and_factor_sources():
    with TestClient(app) as c:
        assert c.get('/healthz').json()['storage_mode']=='memory'
        assert c.get('/openapi.json').status_code==200
        factors=c.get('/api/v1/factors').json()['items']
        assert len(factors)==11
        assert all(f['approved'] and f['source_locator'] and not f['fixture_only'] for f in factors)
