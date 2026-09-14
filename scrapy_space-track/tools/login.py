import re
import json
from typing import Optional, Tuple, Any, Dict

try:
    from ..config import LOGIN_BTN
except ImportError:
    from config import LOGIN_BTN


_CSRF_COOKIE_RE = re.compile(r'spacetrack_csrf_cookie=([^;\s]+)')
_CSRF_INPUT_RE = re.compile(
    r'name=[\'"]spacetrack_csrf_token[\'"]\s+value=[\'"]([^\'"]+)[\'"]',
    re.I,
)
_ERROR_JSON_RE = re.compile(r'"error"\s*:\s*"([^"]+)"')


def extract_csrf(html_text: str, cookie_header: Optional[str] = None) -> Tuple[str, str]:
    m_input = _CSRF_INPUT_RE.search(html_text or '')
    csrf_from_input = m_input.group(1) if m_input else ''

    csrf_from_cookie = ''
    if cookie_header:
        mc = _CSRF_COOKIE_RE.search(cookie_header)
        if mc:
            csrf_from_cookie = mc.group(1)

    token = csrf_from_input or csrf_from_cookie
    cookie_token = csrf_from_cookie or csrf_from_input
    return token, cookie_token


def build_login_formdata(
    csrf_token: str,
    identity: str,
    password: str,
) -> Dict[str, str]:
    return {
        'spacetrack_csrf_token': csrf_token,
        'identity': identity,
        'password': password,
        'btnLogin': LOGIN_BTN,
    }


def detect_api_auth_error(body_text: str) -> Optional[str]:
    """Return a truthy string only if the Space-Track API response means the
    session cookie is missing / expired / invalid — i.e. the client needs to
    re-run the login POST to get a fresh chocolatechip.

    Other API errors (class does not exist, malformed query, rate-limit, ...)
    are explicitly NOT reported as auth errors so that callers don't loop on
    pointless re-auth attempts (anti-bot measure #3: avoid confusing a
    legitimate 200+{"error":"..."} payload with a login-wall).
    """
    if body_text is None:
        return None
    stripped = body_text.strip()
    # Empty body is suspicious but NOT an auth error by itself.  POST /auth/login
    # returns 200 + empty body both on success and on wrong credentials, so
    # callers must use a separate authenticated probe to distinguish.
    if stripped == '':
        return None

    error_message: Optional[str] = None
    if stripped.startswith('{'):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict) and 'error' in obj:
                error_message = str(obj['error'])
        except (ValueError, TypeError):
            m = _ERROR_JSON_RE.search(stripped)
            if m:
                error_message = m.group(1)
    else:
        lower_plain = stripped.lower()
        if 'must be logged in' in lower_plain or 'login required' in lower_plain:
            return 'auth required (plain)'

    if not error_message:
        return None

    auth_phrases = (
        'must be logged in',
        'login required',
        'not logged in',
        'not authorised',
        'not authorized',
        'authentication failed',
        'unauthenticated',
    )
    e_lower = error_message.lower()
    if any(phrase in e_lower for phrase in auth_phrases):
        return error_message
    # Anything else (e.g. "Your Class Does Not Exist", "429 rate limit", ...)
    # is a real API response, NOT a login issue.
    return None
