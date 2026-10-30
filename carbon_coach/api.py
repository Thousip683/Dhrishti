"""Typed Carbon Coach API with transactional memory or database repositories."""
import asyncio
from copy import deepcopy
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import secrets
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from .storage import SessionRecord, configured_repository
from starlette.exceptions import HTTPException as StarletteHTTPException
from dotenv import load_dotenv
from . import schemas as contract
from .schemas import SessionInput, CalculationInput, ActivityInput, ActivityPatch, MessageInput, ReductionInput
from .gateway import GatewayRequest, MockGateway
from .adk_gateway import ADKGateway

from . import domain
from . import browser_security as browser

def documented_headers(
    authorization: str | None = Header(default=None, description='Bearer session_token on session routes.'),
    idempotency_key: str | None = Header(default=None, description='Unique retry key for session calculations and mutations.'),
    if_match: str | None = Header(default=None, description='Current record revision for PATCH or DELETE.'),
):
    """Expose request headers in OpenAPI; route services enforce their scope."""

load_dotenv()

@asynccontextmanager
async def lifespan(application):
    async def cleanup():
        while True:
            try:
                if await run_in_threadpool(application.state.repository.ready):
                    expired = await run_in_threadpool(application.state.repository.cleanup_expired)
                    for sid in expired:
                        await application.state.gateway.erase(sid)
            except Exception:
                # Readiness reports a failing store; don't leak database details.
                pass
            await asyncio.sleep(60)
    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app = FastAPI(lifespan=lifespan, responses={code: {'model': contract.ErrorResponse} for code in (400, 401, 403, 404, 405, 409, 412, 413, 422, 429, 500, 503)}, title='Carbon Coach', version='0.2.0', dependencies=[Depends(documented_headers)], description='Typed application API with durable SQLite or PostgreSQL storage. Apply Alembic migrations before use. Gemini is optional for direct calculation endpoints.')
app.add_middleware(CORSMiddleware, allow_origins=browser.allowed_origins(), allow_credentials=True,
    allow_methods=['GET','POST','PATCH','DELETE'], allow_headers=['Content-Type','Authorization','X-CSRF-Token','Idempotency-Key','If-Match'])
app.state.gateway = MockGateway() if os.getenv('GATEWAY_MODE') == 'mock' else ADKGateway()

app.state.repository = configured_repository()

def success(request, **values):
    return {'request_id': request.state.request_id, 'status': 'success', **values}

@app.middleware('http')
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid4())
    # Bound memory while reading, including callers without Content-Length.
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 65536:
            return JSONResponse({'request_id': request.state.request_id, 'status': 'error', 'error': {'code': 'PAYLOAD_TOO_LARGE', 'message': 'Request exceeds 64 KiB.', 'retryable': False}}, status_code=413)
        chunks.append(chunk)
    request._body = b''.join(chunks)
    uow = None
    try:
        if request.url.path.startswith('/api/v1/sessions') or (request.url.path.startswith('/api/v1/browser/') and not request.url.path.endswith('/bootstrap')):
            parts = request.url.path.strip('/').split('/')
            sid = parts[3] if len(parts) > 3 and parts[2]=='sessions' else browser.cookie_credentials(request)[0]
            nonce = request.cookies.get(browser.BOOTSTRAP_COOKIE, '')
            nonce_hash = sha256(nonce.encode()).hexdigest() if nonce and request.url.path=='/api/v1/browser/session' and request.method=='POST' else None
            uow = await run_in_threadpool(app.state.repository.begin, sid, nonce_hash)
            request.state.uow = uow
        response = await call_next(request)
        if uow is not None:
            if response.status_code < 400:
                await run_in_threadpool(uow.commit)
            else:
                await run_in_threadpool(uow.rollback)
        if response.status_code < 400 and getattr(request.state, 'browser_auth', None):
            sid, secret = request.state.browser_auth
            browser.set_cookie(response, request, browser.SESSION_COOKIE, f'{sid}.{secret}', '/api/v1')
            record=uow.get(sid) if uow is not None else None
            if record:
                response.headers['X-Session-Expires-At']=record.expires_at.isoformat()
    except domain.DomainError as exc:
        if uow is not None:
            await run_in_threadpool(uow.rollback)
        response = await domain_error(request, exc)
    except SQLAlchemyError:
        if uow is not None:
            await run_in_threadpool(uow.rollback)
        response = await domain_error(request, domain.DomainError('STORAGE_UNAVAILABLE', 'Database unavailable. No save was acknowledged; retry with the same key.', 503))
    finally:
        if uow is not None:
            await run_in_threadpool(uow.close)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

@app.exception_handler(domain.DomainError)
async def domain_error(request, exc):
    response = JSONResponse({'request_id': request.state.request_id, 'status': 'error', 'error': {'code': exc.code, 'message': exc.message, 'retryable': exc.http >= 500}}, status_code=exc.http)
    if request.url.path.startswith('/api/v1/browser/') and exc.http in (401,404):
        browser.clear_cookies(response)
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'request_id': request.state.request_id, 'status': 'error', 'error': {'code': 'INVALID_REQUEST', 'message': 'Request validation failed.', 'retryable': False, 'field_errors': [{'field': '.'.join(map(str, e['loc'])), 'reason': e['msg']} for e in exc.errors()]}}, status_code=422)

@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    codes = {404: 'NOT_FOUND', 405: 'METHOD_NOT_ALLOWED'}
    return JSONResponse({'request_id': request.state.request_id, 'status': 'error',
        'error': {'code': codes.get(exc.status_code, 'HTTP_ERROR'), 'message': str(exc.detail),
                  'retryable': exc.status_code >= 500}}, status_code=exc.status_code, headers=exc.headers)

@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse({'request_id': request.state.request_id, 'status': 'error',
        'error': {'code': 'INTERNAL_ERROR', 'message': 'The request could not be completed.', 'retryable': True}}, status_code=500)

def session_for(request, sid):
    auth = request.headers.get('authorization', '')
    if auth:
        if not auth.startswith('Bearer '):
            raise domain.DomainError('UNAUTHORIZED', 'A valid bearer credential is required.', 401)
        secret=auth[7:]
    else:
        cookie_sid, secret=browser.cookie_credentials(request)
        if not secret:
            raise domain.DomainError('UNAUTHORIZED', 'Start a session to continue.', 401)
        if cookie_sid != sid:
            raise domain.DomainError('NOT_FOUND', 'Session not found.', 404)
        if request.method not in ('GET','HEAD','OPTIONS'):
            browser.check_csrf(request,secret)
        request.state.browser_auth=(sid,secret)
    token_hash = sha256(secret.encode()).hexdigest()
    record = request.state.uow.get(sid)
    if not record or not secrets.compare_digest(token_hash, record.token_hash):
        raise domain.DomainError('NOT_FOUND', 'Session not found.', 404)
    now = datetime.now(timezone.utc)
    if record.expires_at <= now:
        request.state.uow.pop(sid, None)
        raise domain.DomainError('UNAUTHORIZED', 'Session has expired.', 401)
    record.expires_at = now + timedelta(hours=24)
    return record

def idempotency(request, record, body):
    key = request.headers.get('idempotency-key')
    if not key or len(key) > 128:
        raise domain.DomainError('INVALID_REQUEST', 'Idempotency-Key header is required and limited to 128 characters.')
    cache_key = f'{request.method}:{request.url.path}:{key}'
    fingerprint = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    cached = record.cache.get(cache_key)
    if cached and cached[0] != fingerprint:
        raise domain.DomainError('IDEMPOTENCY_CONFLICT', 'This key was used with a different request.', 409)
    return cache_key, fingerprint, deepcopy(cached[1]) if cached else None

def save_cache(record, cache_key, fingerprint, reply):
    record.cache[cache_key] = (fingerprint, deepcopy(reply))
    return reply

def revision(request):
    value = request.headers.get('if-match', '').strip('"')
    if not value.isdigit():
        raise domain.DomainError('INVALID_REQUEST', 'If-Match must contain the current record revision.')
    return int(value)

@app.get('/', include_in_schema=False)
def home():
    index=frontend_dist()/'index.html'
    return FileResponse(index) if index.is_file() else RedirectResponse('/docs')

@app.get('/healthz', response_model=contract.HealthResponse)
def health():
    return {'status': 'ok', 'storage_mode': app.state.repository.mode, 'chat_configured': app.state.gateway.configured}

@app.get('/readyz', response_model=contract.ReadyResponse)
async def ready():
    if not await run_in_threadpool(app.state.repository.ready):
        raise domain.DomainError('STORAGE_UNAVAILABLE', 'Database schema is unavailable. Apply migrations before use.', 503)
    return {'status': 'ready', 'factor_count': len(domain.FACTORS)}

@app.post('/api/v1/sessions', status_code=201, response_model=contract.SessionResponse)
async def create_session(body: SessionInput, request: Request):
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise domain.DomainError('INVALID_REQUEST', 'Use a valid IANA timezone.')
    sid, token = str(uuid4()), secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    ledger = {'timezone': body.timezone, 'region': body.region, 'locale': body.locale, 'calculations': {}, 'activities': []}
    request.state.uow[sid] = SessionRecord(sha256(token.encode()).hexdigest(), ledger, expires)
    return success(request, session_id=sid, session_token=token, expires_at=expires.isoformat(), storage_mode=app.state.repository.mode, **body.model_dump(mode='json'))

@app.delete('/api/v1/sessions/{sid}', status_code=204)
async def erase(sid: str, request: Request):
    record = session_for(request, sid)
    if record.lock.locked():
        raise domain.DomainError('SESSION_BUSY', 'Wait for the active turn before erasing.', 409)
    del request.state.uow[sid]
    await app.state.gateway.erase(sid)
    response=Response(status_code=204)
    if getattr(request.state,'browser_auth',None):
        request.state.browser_auth=None
        browser.clear_cookies(response)
    return response

@app.get('/api/v1/factors', response_model=contract.FactorListResponse)
def factors(request: Request, category: str | None = None):
    return success(request, items=[f for f in domain.FACTORS.values() if category is None or f['category'] == category], recipes=domain.RECIPES)

@app.get('/api/v1/factors/{fid}/versions/{version}', response_model=contract.FactorResponse)
def factor_version(fid: str, version: str, request: Request):
    f = domain.factor(fid)
    if f['version'] != version:
        raise domain.DomainError('NOT_FOUND', 'Factor version not found.', 404)
    return success(request, factor=f)

def unlocked(request, sid):
    record = session_for(request, sid)
    if record.lock.locked():
        raise domain.DomainError('SESSION_BUSY', 'A conversational turn is running; retry when complete.', 409)
    return record

@app.post('/api/v1/sessions/{sid}/calculations', status_code=201, response_model=contract.CalculationResponse)
async def calculate(sid: str, body: CalculationInput, request: Request):
    record = unlocked(request, sid)
    key, digest, cached = idempotency(request, record, body.model_dump(mode='json'))
    if cached:
        return cached
    selected_ref = (body.factor_id, body.factor_version) if body.factor_id is not None else None
    result = domain.calculate(record.ledger, body.category, body.input.model_dump(exclude_none=True), requested_factor_ref=selected_ref)
    return save_cache(record, key, digest, success(request, calculation=result))

@app.get('/api/v1/sessions/{sid}/capabilities', response_model=contract.CapabilitiesResponse)
async def activity_capabilities(sid: str, request: Request):
    record = session_for(request, sid)
    return success(request, **domain.capabilities(record.ledger))

@app.post('/api/v1/sessions/{sid}/energy-conversions', status_code=201, response_model=contract.EnergyConversionResponse)
async def convert_appliance(sid: str, body: contract.ApplianceInput, request: Request):
    record = unlocked(request, sid)
    key,digest,cached = idempotency(request, record, body.model_dump(mode='json'))
    if cached:
        return cached
    conversion = domain.convert_energy(record.ledger, body.model_dump(exclude_none=True))
    return save_cache(record,key,digest,success(request,conversion=conversion))

@app.get('/api/v1/sessions/{sid}/energy-conversions/{cid}', response_model=contract.EnergyConversionResponse)
async def energy_conversion_detail(sid: str, cid: str, request: Request):
    record = session_for(request, sid)
    conversion = record.ledger.get('energy_conversions',{}).get(cid)
    if conversion is None:
        raise domain.DomainError('NOT_FOUND','Energy conversion not found.',404)
    return success(request,conversion=conversion)

@app.post('/api/v1/sessions/{sid}/activities', status_code=201, response_model=contract.ActivityResponse)
async def log_activity(sid: str, body: ActivityInput, request: Request):
    record = unlocked(request, sid)
    key, digest, cached = idempotency(request, record, body.model_dump(mode='json'))
    if cached:
        return cached
    if any(a['calculation_id'] == body.calculation_id for a in record.ledger['activities']):
        raise domain.DomainError('CALCULATION_ALREADY_LOGGED', 'This calculation has already been logged.', 409)
    item = domain.log(record.ledger, body.calculation_id, body.activity_date.isoformat(), body.note)
    return save_cache(record, key, digest, success(request, activity=item))

@app.get('/api/v1/sessions/{sid}/activities', response_model=contract.ActivityListResponse)
async def activities(sid: str, request: Request, start_date: str | None = None, end_date: str | None = None, category: str | None = None):
    record = session_for(request, sid)
    validate_filters(start_date, end_date, category)
    items = [a for a in record.ledger['activities'] if not a['deleted'] and (not category or a['category'] == category) and (not start_date or a['activity_date'] >= start_date) and (not end_date or a['activity_date'] < end_date)]
    return success(request, items=sorted(items, key=lambda a: (a['activity_date'], a['created_at'], a['id'])), next_cursor=None)

def validate_filters(start_date, end_date, category=None):
    if category is not None and category not in domain.CATEGORIES:
        raise domain.DomainError('UNSUPPORTED_ACTIVITY', 'Choose a supported category.')
    for value in (start_date, end_date):
        if value is not None:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise domain.DomainError('INVALID_DATE', 'Use YYYY-MM-DD calendar dates.')
    if start_date and end_date and end_date <= start_date:
        raise domain.DomainError('INVALID_DATE', 'end_date must be later than start_date.')

@app.get('/api/v1/sessions/{sid}/calculations/{cid}', response_model=contract.CalculationResponse)
async def calculation_detail(sid: str, cid: str, request: Request):
    record = session_for(request, sid)
    calculation = record.ledger['calculations'].get(cid)
    if calculation is None:
        raise domain.DomainError('NOT_FOUND', 'Calculation not found.', 404)
    return success(request, calculation=calculation)

@app.get('/api/v1/sessions/{sid}/activities/{aid}', response_model=contract.ActivityDetailResponse)
async def activity_detail(sid: str, aid: str, request: Request):
    record = session_for(request, sid)
    item = next((a for a in record.ledger['activities'] if a['id'] == aid and not a['deleted']), None)
    if item is None:
        raise domain.DomainError('NOT_FOUND', 'Activity not found.', 404)
    return success(request, activity=item, calculation=record.ledger['calculations'][item['calculation_id']])

@app.patch('/api/v1/sessions/{sid}/activities/{aid}', response_model=contract.ActivityResponse)
async def patch_activity(sid: str, aid: str, body: ActivityPatch, request: Request):
    record = unlocked(request, sid)
    key, digest, cached = idempotency(request, record, {**body.model_dump(mode='json'), 'revision': request.headers.get('if-match')})
    if cached:
        return cached
    item = next((a for a in record.ledger['activities'] if a['id'] == aid and not a['deleted']), None)
    if not item:
        raise domain.DomainError('NOT_FOUND', 'Activity not found.', 404)
    if item['revision'] != revision(request):
        raise domain.DomainError('REVISION_MISMATCH', 'Reload current revision.', 412)
    if not body.model_fields_set or all(getattr(body, k) is None for k in body.model_fields_set):
        raise domain.DomainError('INVALID_REQUEST', 'Provide at least one replacement field.')
    draft = deepcopy(record.ledger)
    original = next(a for a in draft['activities'] if a['id'] == aid)
    replacement_id = body.calculation_id or item['calculation_id']
    if replacement_id != item['calculation_id']:
        if any(a['calculation_id'] == replacement_id for a in draft['activities']):
            raise domain.DomainError('CALCULATION_ALREADY_LOGGED', 'Replacement already committed.', 409)
    # Validate a candidate record before atomically replacing the original.
    candidate_state = {'timezone': draft['timezone'], 'calculations': draft['calculations'], 'activities': []}
    replacement = domain.log(candidate_state, replacement_id, (body.activity_date.isoformat() if body.activity_date is not None else item['activity_date']), body.note if body.note is not None else item['note'])
    if replacement_id != item['calculation_id']:
        draft.setdefault('calculation_states', {})[item['calculation_id']] = 'superseded'
        draft['calculation_states'][replacement_id] = 'active'
    original.update({**replacement, 'id': aid, 'revision': item['revision'] + 1, 'created_at': item['created_at']})
    record.ledger = draft
    return save_cache(record, key, digest, success(request, activity=deepcopy(original)))

@app.delete('/api/v1/sessions/{sid}/activities/{aid}', status_code=204)
async def delete_activity(sid: str, aid: str, request: Request):
    record = unlocked(request, sid)
    item = next((a for a in record.ledger['activities'] if a['id'] == aid), None)
    if item and item['deleted']:
        return Response(status_code=204)
    domain.remove_activity(record.ledger, aid, revision(request))
    return Response(status_code=204)

@app.get('/api/v1/sessions/{sid}/summary', response_model=contract.SummaryResponse)
async def summary(sid: str, request: Request, period: str = 'week', start_date: str | None = None, end_date: str | None = None):
    record = session_for(request, sid)
    validate_filters(start_date, end_date)
    if period != 'custom' and (start_date is not None or end_date is not None):
        raise domain.DomainError('INVALID_DATE', 'Explicit dates require period=custom.')
    return success(request, summary=domain.summary(record.ledger, period, start_date, end_date))

@app.post('/api/v1/sessions/{sid}/reductions', response_model=contract.ReductionResponse)
async def reductions(sid: str, body: ReductionInput, request: Request):
    record = unlocked(request, sid)
    key, digest, cached = idempotency(request, record, body.model_dump(mode='json'))
    if cached:
        return cached
    return save_cache(record, key, digest, success(request, **domain.reductions(record.ledger, body.period)))

@app.post('/api/v1/sessions/{sid}/messages', response_model=contract.MessageResponse)
async def message(sid: str, body: MessageInput, request: Request):
    record = session_for(request, sid)
    key, digest, cached = idempotency(request, record, body.model_dump(mode='json'))
    if cached:
        return cached
    if record.lock.locked():
        raise domain.DomainError('SESSION_BUSY', 'Another turn is running.', 409)
    async with record.lock:
        result = await app.state.gateway.run(GatewayRequest(
            session_id=sid, request_id=request.state.request_id, text=body.text,
            ledger=deepcopy(record.ledger),locale=body.language))
        record.ledger = deepcopy(result.ledger)
        message_id=str(uuid4())
        stamp=datetime.now(timezone.utc).isoformat()
        history=record.ledger.setdefault('chat_history',[])
        history.extend([dict(id=str(uuid4()),role='user',text=body.text,created_at=stamp,status='success',tool_calls=[]),
            dict(id=message_id,role='assistant',text=result.reply,created_at=stamp,status=result.status,tool_calls=result.tool_calls)])
        reply = success(request, reply=result.reply, message_id=message_id,
            committed_activity_ids=result.committed_activity_ids, warnings=result.warnings,tool_calls=result.tool_calls)
        reply['status'] = result.status
        return save_cache(record, key, digest, reply)

@app.get('/api/v1/sessions/{sid}/messages', response_model=contract.ChatHistoryResponse)
async def chat_history(sid: str, request: Request):
    record=session_for(request,sid)
    return success(request,messages=record.ledger.get('chat_history',[]))

def browser_metadata(request, sid, record, secret):
    return success(request, session_id=sid, expires_at=record.expires_at.isoformat(),
        storage_mode=app.state.repository.mode, timezone=record.ledger.get('timezone','Asia/Kolkata'),
        locale=record.ledger.get('locale','en'), region=record.ledger.get('region','UK'),
        csrf_token=browser.csrf(secret),
        chat_mode='mock' if isinstance(app.state.gateway,MockGateway) else ('configured' if app.state.gateway.configured else 'unavailable'))

@app.get('/api/v1/browser/bootstrap', response_model=contract.BrowserBootstrapResponse)
async def browser_bootstrap(request: Request, response: Response):
    _, session_secret=browser.cookie_credentials(request)
    nonce=session_secret or request.cookies.get(browser.BOOTSTRAP_COOKIE) or secrets.token_urlsafe(32)
    browser.set_cookie(response,request,browser.BOOTSTRAP_COOKIE,nonce,'/api/v1/browser')
    return success(request,csrf_token=browser.csrf(nonce))

@app.post('/api/v1/browser/session', status_code=201, response_model=contract.BrowserSessionResponse)
async def browser_create(body: SessionInput, request: Request, response: Response):
    nonce=request.cookies.get(browser.BOOTSTRAP_COOKIE,'')
    browser.check_csrf(request,nonce)
    if not 20 <= len(nonce) <= 128:
        raise domain.DomainError('UNAUTHORIZED','Initialize the browser session first.',401)
    if not request.headers.get('idempotency-key') or len(request.headers['idempotency-key'])>128:
        raise domain.DomainError('INVALID_REQUEST','A bounded Idempotency-Key is required.')
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError,ValueError):
        raise domain.DomainError('INVALID_REQUEST','Use a valid IANA timezone.')
    digest=sha256(nonce.encode()).hexdigest()
    fingerprint=sha256(json.dumps(body.model_dump(),sort_keys=True).encode()).hexdigest()
    previous=request.state.uow.lookup_bootstrap(digest)
    if previous:
        if previous['expires_at']<=datetime.now(timezone.utc):
            raise domain.DomainError('UNAUTHORIZED','Session creation expired. Start again.',401)
        if previous['payload_hash']!=fingerprint:
            raise domain.DomainError('IDEMPOTENCY_CONFLICT','This browser already created a session with different settings. Restore it before editing settings.',409)
        sid=previous['session_id']
        record=request.state.uow.get(sid)
        if record is None or record.expires_at<=datetime.now(timezone.utc):
            raise domain.DomainError('UNAUTHORIZED','Session expired. Start again.',401)
    else:
        sid=str(uuid4())
        record=SessionRecord(digest,{'timezone':body.timezone,'region':body.region,'locale':body.locale,'calculations':{},'activities':[]},datetime.now(timezone.utc)+timedelta(hours=24))
        request.state.uow[sid]=record
        request.state.uow.register_bootstrap(digest,dict(session_id=sid,payload_hash=fingerprint,expires_at=record.expires_at))
    browser.set_cookie(response,request,browser.SESSION_COOKIE,f'{sid}.{nonce}','/api/v1')
    return browser_metadata(request,sid,record,nonce)

@app.get('/api/v1/browser/session', response_model=contract.BrowserSessionResponse)
async def browser_restore(request: Request):
    sid,secret=browser.cookie_credentials(request)
    if not sid:
        raise domain.DomainError('UNAUTHORIZED','No browser session is available.',401)
    record=session_for(request,sid)
    return browser_metadata(request,sid,record,secret)

@app.patch('/api/v1/browser/session', response_model=contract.BrowserSessionResponse)
async def browser_settings(body: contract.SessionSettingsInput, request: Request):
    sid,secret=browser.cookie_credentials(request)
    if not sid:
        raise domain.DomainError('UNAUTHORIZED','No browser session is available.',401)
    record=session_for(request,sid)
    key,digest,cached=idempotency(request,record,body.model_dump())
    if cached:
        return cached
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError,ValueError):
        raise domain.DomainError('INVALID_REQUEST','Use a valid IANA timezone.')
    record.ledger['timezone']=body.timezone
    return save_cache(record,key,digest,browser_metadata(request,sid,record,secret))

@app.delete('/api/v1/browser/session', status_code=204)
async def browser_erase(request: Request):
    sid,_=browser.cookie_credentials(request)
    if not sid:
        raise domain.DomainError('UNAUTHORIZED','No browser session is available.',401)
    session_for(request,sid)
    del request.state.uow[sid]
    await app.state.gateway.erase(sid)
    request.state.browser_auth=None
    response=Response(status_code=204)
    browser.clear_cookies(response)
    return response

def frontend_dist():
    return Path(os.getenv('FRONTEND_DIST',str(Path(__file__).resolve().parents[1]/'frontend/dist'))).resolve()

@app.get('/{path:path}', include_in_schema=False)
async def frontend_route(path: str):
    if path.split('/')[0] in ('api','healthz','readyz','docs','openapi.json','redoc'):
        raise domain.DomainError('NOT_FOUND','Route not found.',404)
    root=frontend_dist()
    target=(root/path).resolve()
    if not target.is_relative_to(root):
        raise domain.DomainError('NOT_FOUND','Route not found.',404)
    if target.is_file():
        return FileResponse(target)
    if not Path(path).suffix and (root/'index.html').is_file():
        return FileResponse(root/'index.html')
    raise domain.DomainError('NOT_FOUND','Page not found.',404)
