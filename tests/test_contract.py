import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from carbon_coach.api import app
from carbon_coach.gateway import GatewayRequest, MockGateway
from carbon_coach import schemas

def new_session(client):
    body=client.post('/api/v1/sessions',json={}).json()
    return body['session_id'], {'Authorization':'Bearer '+body['session_token']}

def test_every_success_json_route_has_named_response_schema():
    schema=app.openapi()
    for path,operations in schema['paths'].items():
        for verb,operation in operations.items():
            for status,response in operation['responses'].items():
                if status.startswith('2') and status != '204':
                    assert '$ref' in response['content']['application/json']['schema'], (path,verb)

def test_owned_evidence_and_typed_errors():
    with TestClient(app) as c:
        sid,headers=new_session(c)
        base=f'/api/v1/sessions/{sid}'
        response=c.post(base+'/calculations',headers={**headers,'Idempotency-Key':str(uuid4())},json={'category':'travel','input':{'mode':'bus','distance_km':'12'}})
        calc=response.json()['calculation']
        assert c.get(base+'/calculations/'+calc['id'],headers=headers).status_code==200
        _,other=new_session(c)
        assert c.get(base+'/calculations/'+calc['id'],headers=other).status_code==404
        for url in [base+'/activities?start_date=bad',base+'/activities?category=bad',base+'/summary?period=week&start_date=2026-10-01','/api/v1/not-a-route']:
            response=c.get(url,headers=headers)
            assert response.status_code in (404,422)
            schemas.ErrorResponse.model_validate(response.json())

def test_mock_chat_replay_and_no_activity_mutation():
    original=app.state.gateway
    app.state.gateway=MockGateway()
    try:
        with TestClient(app) as c:
            sid,h=new_session(c)
            h['Idempotency-Key']=str(uuid4())
            path=f'/api/v1/sessions/{sid}/messages'
            first=c.post(path,headers=h,json={'text':'hello'})
            assert first.status_code==200
            result=schemas.MessageResponse.model_validate(first.json())
            assert result.committed_activity_ids==[]
            assert 'Mock' in result.reply
            assert c.post(path,headers=h,json={'text':'hello'}).json()==first.json()
            assert app.state.repository.records[sid].ledger['activities']==[]
    finally:
        app.state.gateway=original

def test_contract_fixtures_and_generated_artifacts_are_current():
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('export_contract',root/'scripts/export_contract.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path,content in module.artifacts().items():
        assert path.read_text(encoding='utf-8')==content, f'Regenerate {path.name}'
