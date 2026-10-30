"""Adapter for the existing agent; model and tool behavior remain unchanged."""
from copy import deepcopy
import asyncio
import os
from .gateway import GatewayRequest, GatewayResult
from .domain import DomainError

class ADKGateway:
    def __init__(self, agent=None):
        self.sessions = None
        self.runner = None
        self.agent = agent

    @property
    def configured(self):
        return self.agent is not None or bool(os.getenv('GOOGLE_API_KEY'))

    def _initialize(self):
        if self.runner is None:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from .agent import root_agent
            self.sessions = InMemorySessionService()
            self.runner = Runner(agent=self.agent or root_agent, app_name='carbon_coach', session_service=self.sessions)

    async def erase(self, session_id):
        if self.sessions is not None:
            await self.sessions.delete_session(app_name='carbon_coach', user_id=session_id, session_id=session_id)

    async def run(self, request: GatewayRequest):
        if not self.configured:
            raise DomainError('MODEL_UNAVAILABLE', 'Set GOOGLE_API_KEY in .env to enable Gemini chat. Offline calculation endpoints are ready.', 503)
        self._initialize()
        from google.genai import types
        sid = request.session_id
        saved = await self.sessions.get_session(app_name='carbon_coach', user_id=sid, session_id=sid)
        if saved is None:
            saved = await self.sessions.create_session(app_name='carbon_coach', user_id=sid, session_id=sid, state={'ledger': deepcopy(request.ledger)})
            # Rehydrate conversational text from the same durable session as the
            # application. Do not persist recursive ADK state-delta snapshots.
            from google.adk.events import Event
            for message in request.ledger.get('chat_history', [])[-40:]:
                await self.sessions.append_event(saved, Event(author='user' if message['role']=='user' else 'carbon_coach',
                    invocation_id=message['id'], content=types.Content(role='user' if message['role']=='user' else 'model',parts=[types.Part(text=message['text'])])))
        original_ids = {a['id'] for a in request.ledger.get('activities', [])}
        failed = False
        calls = []
        try:
            async with asyncio.timeout(60):
                async for event in self.runner.run_async(user_id=sid, session_id=sid,
                    new_message=types.Content(role='user', parts=[types.Part(text=request.text)]),
                    state_delta={'ledger': deepcopy(request.ledger), 'turn_receipts': [], 'needs_clarification': False, 'response_language':request.locale}):
                    calls.extend(call.name for call in (event.get_function_calls() or []))
        except Exception:
            failed = True
        saved = await self.sessions.get_session(app_name='carbon_coach', user_id=sid, session_id=sid)
        state = saved.state if saved else {}
        ledger = deepcopy(state.get('ledger', request.ledger))
        receipts = state.get('turn_receipts', [])
        reply = '\n\n'.join(dict.fromkeys(receipts)) or ('Gemini could not complete this turn. No new result is available.' if failed else 'Please describe an activity to estimate.')
        return GatewayResult(status='partial_failure' if failed else ('needs_clarification' if state.get('needs_clarification') else 'success'),
            reply=reply, ledger=ledger,
            committed_activity_ids=[a['id'] for a in ledger.get('activities', []) if a['id'] not in original_ids and not a['deleted']],
            warnings=['Model turn interrupted; completed receipts are preserved.'] if failed else [], tool_calls=calls)
