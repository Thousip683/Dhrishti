from uuid import uuid4
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from fastapi.testclient import TestClient
from carbon_coach.api import app
from carbon_coach.adk_gateway import ADKGateway
from carbon_coach.agent import build_agent

class SpecialistModel(BaseLlm):
    """Script the real ADK handoff/tool loop; never send a provider request."""
    model: str='combined-scripted-test'

    async def generate_content_async(self,llm_request,stream=False):
        contents=llm_request.contents
        commands={'summary','log-bus','compare-mass','hello-hi'}
        # ADK adds synthetic user-role handoff instructions. They must not be
        # mistaken for the actual user command in this scripted model.
        last_user=max(i for i,content in enumerate(contents) if content.role=='user' and any(part.text in commands for part in content.parts or []))
        text=' '.join(part.text or '' for part in contents[last_user].parts or [])
        replies=[part.function_response for content in contents[last_user+1:] for part in content.parts or [] if part.function_response]
        names=[reply.name for reply in replies]
        needed='compare_food_options' if 'compare-mass' in text else ('calculate_travel_emissions' if 'log-bus' in text else ('ask_for_details' if 'hello-hi' in text else 'get_summary'))
        if needed not in llm_request.tools_dict:
            call=types.FunctionCall(name='transfer_to_agent',args={'agent_name':'coach_agent' if needed=='compare_food_options' else 'tracker_agent'})
        elif needed=='calculate_travel_emissions' and 'log_activity' not in names:
            calculations=[reply for reply in replies if reply.name==needed]
            call=types.FunctionCall(name='log_activity',args={'calculation_id':calculations[-1].response['result']['id']}) if calculations else types.FunctionCall(name=needed,args={'mode':'bus','km':'12'})
        elif needed not in names:
            arguments={'original_food':'poultry','alternative_food':'peas','kg':'0.2'} if needed=='compare_food_options' else ({'category':'general'} if needed=='ask_for_details' else {'period':'today'})
            call=types.FunctionCall(name=needed,args=arguments)
        else:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='Untrusted generated claim: 999 kg CO2e.')]))
            return
        yield LlmResponse(content=types.Content(role='model',parts=[types.Part(function_call=call)]))

def test_manual_and_specialist_chat_share_one_ledger_and_survive_gateway_restart(tmp_path,monkeypatch):
    unused=tmp_path/'must_not_create.sqlite3'
    monkeypatch.setenv('CARBON_DB_PATH',str(unused))
    previous=app.state.gateway
    gateway=ADKGateway(agent=build_agent(SpecialistModel()))
    app.state.gateway=gateway
    try:
        with TestClient(app) as c:
            session=c.post('/api/v1/sessions',json={}).json()
            base='/api/v1/sessions/'+session['session_id']
            headers={'Authorization':'Bearer '+session['session_token']}
            def key():return {**headers,'Idempotency-Key':str(uuid4())}
            today=c.get(base+'/capabilities',headers=headers).json()['local_today']
            calc=c.post(base+'/calculations',headers=key(),json={'category':'travel','input':{'mode':'bus','distance_km':'12'}}).json()['calculation']
            assert c.post(base+'/activities',headers=key(),json={'calculation_id':calc['id'],'activity_date':today}).status_code==201
            operation=key()
            summary=c.post(base+'/messages',headers=operation,json={'text':'summary'})
            assert summary.status_code==200,summary.text
            assert '1.25' in summary.json()['reply'] and '999' not in summary.json()['reply']
            assert summary.json()['committed_activity_ids']==[]
            assert 'transfer_to_agent' in summary.json()['tool_calls']
            assert c.post(base+'/messages',headers=operation,json={'text':'summary'}).json()==summary.json()
            assert len(c.get(base+'/messages',headers=headers).json()['messages'])==2
            logged=c.post(base+'/messages',headers=key(),json={'text':'log-bus'})
            assert logged.json()['status']=='success',logged.text
            assert len(logged.json()['committed_activity_ids'])==1
            assert len(c.get(base+'/activities',headers=headers).json()['items'])==2
            # Recreate the provider adapter: durable transcript and ledger must
            # be sufficient to restore the next conversation context.
            app.state.gateway=ADKGateway(agent=build_agent(SpecialistModel()))
            restored=c.post(base+'/messages',headers=key(),json={'text':'summary'})
            assert restored.json()['status']=='success',restored.text
            assert '2.49' in restored.json()['reply']
            comparison=c.post(base+'/messages',headers=key(),json={'text':'compare-mass'})
            assert comparison.json()['status']=='success',comparison.text
            assert '1.78' in comparison.json()['reply']
            assert 'compare_food_options' in comparison.json()['tool_calls']
            assert len(c.get(base+'/activities',headers=headers).json()['items'])==2
            hindi=c.post(base+'/messages',headers=key(),json={'text':'hello-hi','language':'hi'})
            assert hindi.json()['status']=='success',hindi.text
            assert 'मदद' in hindi.json()['reply']
        assert not unused.exists(),'The runtime must not create the upstream standalone ledger.'
    finally:
        app.state.gateway=previous
