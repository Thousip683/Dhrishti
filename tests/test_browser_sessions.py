from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from carbon_coach.api import app
from carbon_coach.browser_security import csrf
from carbon_coach import schemas

ORIGIN='http://127.0.0.1:8001'

def start(client,timezone='Asia/Kolkata'):
    bootstrap=client.get('/api/v1/browser/bootstrap')
    assert bootstrap.status_code==200
    headers={'Origin':ORIGIN,'X-CSRF-Token':bootstrap.json()['csrf_token'],'Idempotency-Key':str(uuid4())}
    result=client.post('/api/v1/browser/session',headers=headers,json={'timezone':timezone})
    assert result.status_code==201,result.text
    assert 'session_token' not in result.json()
    return result.json(),headers

def test_bootstrap_replay_restore_and_cookie_flags():
    with TestClient(app) as c:
        metadata,h=start(c)
        assert c.post('/api/v1/browser/session',headers=h,json={'timezone':'Asia/Kolkata'}).json()['session_id']==metadata['session_id']
        assert c.post('/api/v1/browser/session',headers=h,json={'timezone':'UTC'}).status_code==409
        restored=c.get('/api/v1/browser/session')
        schemas.BrowserSessionResponse.model_validate(restored.json())
        assert restored.json()['session_id']==metadata['session_id']
        assert restored.headers.get('X-Session-Expires-At')
        assert 'HttpOnly' in restored.headers['set-cookie'] and 'SameSite=lax' in restored.headers['set-cookie']
        assert len(app.state.repository.records)==1

def test_cookie_mutations_require_origin_and_csrf_but_bearer_still_works():
    with TestClient(app) as c:
        metadata,h=start(c)
        base=f'/api/v1/sessions/{metadata["session_id"]}'
        payload={'category':'travel','input':{'mode':'bus','distance_km':'12'}}
        assert c.post(base+'/calculations',json=payload).status_code==403
        assert c.post(base+'/calculations',headers={**h,'Origin':'https://attacker.example'},json=payload).status_code==403
        assert c.post(base+'/calculations',headers={**h,'X-CSRF-Token':'wrong'},json=payload).status_code==403
        assert c.post(base+'/calculations',headers=h,json=payload).status_code==201
        c.cookies.clear()
        bearer=c.post('/api/v1/sessions',json={}).json()
        assert c.post(f'/api/v1/sessions/{bearer["session_id"]}/calculations',headers={'Authorization':'Bearer '+bearer['session_token'],'Idempotency-Key':str(uuid4())},json=payload).status_code==201

def test_timezone_updates_and_erasure():
    with TestClient(app) as c:
        metadata,h=start(c)
        assert c.patch('/api/v1/browser/session',headers=h,json={'timezone':'not/a/zone'}).status_code==422
        result=c.patch('/api/v1/browser/session',headers=h,json={'timezone':'UTC'})
        assert result.status_code==200 and result.json()['timezone']=='UTC'
        assert c.get('/api/v1/browser/session').json()['timezone']=='UTC'
        assert c.delete('/api/v1/browser/session',headers=h).status_code==204
        assert not c.cookies.get('cc_session') and not c.cookies.get('cc_bootstrap')
        assert app.state.repository.records=={} and app.state.repository.bootstraps=={}
        assert c.get('/api/v1/browser/session').status_code==401

def test_expiry_clears_stale_browser_credentials():
    with TestClient(app) as c:
        metadata,h=start(c)
        app.state.repository.records[metadata['session_id']].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        response=c.get('/api/v1/browser/session')
        assert response.status_code==401
        assert not c.cookies.get('cc_session')
        start(c)

def test_spa_fallback_does_not_swallow_api_or_missing_assets(tmp_path,monkeypatch):
    (tmp_path/'index.html').write_text('<html>Carbon Coach shell</html>')
    monkeypatch.setenv('FRONTEND_DIST',str(tmp_path))
    with TestClient(app) as c:
        assert 'Carbon Coach shell' in c.get('/settings').text
        assert c.get('/api/v1/missing').status_code==404
        assert c.get('/missing.js').status_code==404
        assert c.get('/healthz').json()['status']=='ok'
