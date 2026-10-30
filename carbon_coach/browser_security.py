"""Same-origin anonymous browser sessions; no credentials are exposed to JS."""
from hashlib import sha256
import hmac
import os
import secrets
from .domain import DomainError

SESSION_COOKIE = 'cc_session'
BOOTSTRAP_COOKIE = 'cc_bootstrap'
TTL = 24 * 60 * 60

def allowed_origins():
    return [value.strip().rstrip('/') for value in os.getenv('ALLOWED_ORIGINS',
        'http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:5173,http://localhost:5173').split(',') if value.strip()]

def check_origin(request):
    origin = request.headers.get('origin', '').rstrip('/')
    if origin not in allowed_origins():
        raise DomainError('ORIGIN_REJECTED', 'This browser origin is not allowed.', 403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise DomainError('ORIGIN_REJECTED', 'Cross-site browser mutations are not allowed.', 403)

def csrf(secret):
    return hmac.new(secret.encode(), b'carbon-coach-browser-csrf-v1', sha256).hexdigest()

def check_csrf(request, secret):
    check_origin(request)
    provided = request.headers.get('x-csrf-token', '')
    if not secret or not secrets.compare_digest(provided, csrf(secret)):
        raise DomainError('CSRF_REJECTED', 'Refresh the session before trying this action again.', 403)

def cookie_credentials(request):
    value = request.cookies.get(SESSION_COOKIE, '')
    sid, separator, secret = value.partition('.')
    return (sid, secret) if separator and 20 <= len(secret) <= 128 and len(sid) == 36 else (None, None)

def set_cookie(response, request, name, value, path):
    # Local HTTP is explicitly supported. Non-local deployments must use HTTPS.
    secure = os.getenv('COOKIE_SECURE', '').lower() == 'true' or request.url.scheme == 'https' or request.url.hostname not in ('localhost','127.0.0.1','testserver')
    response.set_cookie(name, value, max_age=TTL, httponly=True, secure=secure, samesite='lax', path=path)

def clear_cookies(response):
    response.delete_cookie(SESSION_COOKIE, path='/api/v1')
    response.delete_cookie(BOOTSTRAP_COOKIE, path='/api/v1/browser')
