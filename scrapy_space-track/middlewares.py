from typing import Optional

try:
    from scrapy import signals
    from scrapy.http import Request, Response, FormRequest
    from scrapy.exceptions import IgnoreRequest
except ImportError:  # pragma: no cover - scrapy is a runtime dep
    signals = None
    Request = None
    Response = None
    FormRequest = None
    IgnoreRequest = Exception

try:
    from .tools.login import extract_csrf, build_login_formdata, detect_api_auth_error
except ImportError:
    try:
        from tools.login import extract_csrf, build_login_formdata, detect_api_auth_error
    except ImportError:  # pragma: no cover
        extract_csrf = None
        build_login_formdata = None
        detect_api_auth_error = None


class FixedHeadersMiddleware:
    """
    Forces a consistent Origin header and a plausible per-request Referer so
    that the CDN and Apache tier see browser-like navigational headers on
    every request (anti-bot measure #5).  Referers are chained so that:

    * Requests ending in /auth/login   → Referer = <BASE>/
    * Any /basicspacedata/* call       → Referer = <BASE>/auth/login (GET)
      or the previous page in the flow
    * All others fall back to BASE + /

    Origin is always SPACETRACK_BASE (no trailing slash) to match CORS POSTs
    from the login form.
    """

    AUTH_LOGIN_PATH = '/auth/login'

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or 'https://www.space-track.org'

    @classmethod
    def from_crawler(cls, crawler):
        base = crawler.settings.get('SPACETRACK_BASE', 'https://www.space-track.org')
        mw = cls(base_url=base)
        if signals is not None:
            crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        return mw

    def spider_opened(self, spider):
        self.base_url = spider.settings.get('SPACETRACK_BASE', self.base_url)

    def process_request(self, request, spider):
        if request.headers is None:
            return None
        base = self.base_url.rstrip('/')
        if not request.headers.get('Origin'):
            request.headers['Origin'] = base

        if not request.headers.get('Referer'):
            url = request.url or ''
            # 1. POST /auth/login → Referer = GET /auth/login (self)
            if self.AUTH_LOGIN_PATH in url:
                ref = f'{base}{self.AUTH_LOGIN_PATH}'
            # 2. Any basicspacedata call → Referer = /auth/login to mimic
            #    having landed there right after the login POST redirect
            elif '/basicspacedata/' in url:
                ref = f'{base}{self.AUTH_LOGIN_PATH}'
            else:
                ref = f'{base}/'
            request.headers['Referer'] = ref
        return None


class SpaceTrackLoginMiddleware:
    """
    Detects the "200 + body.error=You must be logged in..." pattern returned
    by the Space-Track GP API when cookies expire (anti-bot measure #3).
    Re-runs GET /auth/login → extract CSRF → POST login (again doing the
    body-empty post-login probe), then re-dispatches the failed GP request.
    """

    AUTH_LOGIN_PATH = '/auth/login'
    MAX_REAUTH = 2

    def __init__(self, settings):
        self._login_url: Optional[str] = None
        self._base_url: Optional[str] = None
        self._user: Optional[str] = None
        self._password: Optional[str] = None
        self._orderby: Optional[str] = None
        self._in_flight_reauth: bool = False
        self._reauth_count: int = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(settings=crawler.settings)

    # ---- internal helpers ----

    def _is_login_request(self, request) -> bool:
        if self._login_url and request.url == self._login_url:
            return True
        return self.AUTH_LOGIN_PATH in (request.url or '')

    def _probe_url(self) -> str:
        base = (self._base_url or 'https://www.space-track.org').rstrip('/')
        return (
            f'{base}/basicspacedata/query/class/gp/'
            f'NORAD_CAT_ID/%3E0/EPOCH/%3Enow-1000/'
            f'orderby/NORAD_CAT_ID/limit/1/format/json'
        )

    # ---- downloader hooks ----

    def process_request(self, request, spider):
        if not getattr(spider, '_st_configured', False):
            self._login_url = spider.settings.get('SPACETRACK_LOGIN_URL', self._login_url)
            self._base_url = spider.settings.get('SPACETRACK_BASE', self._base_url)
            self._user = spider.settings.get('SPACETRACK_USER', '')
            self._password = spider.settings.get('SPACETRACK_PASSWORD', '')
            self._orderby = spider.settings.get('SPACETRACK_GP_ORDERBY', 'NORAD_CAT_ID,EPOCH')
            spider._st_configured = True
        return None

    def process_response(self, request, response, spider):
        if detect_api_auth_error is None:
            return response
        if self._is_login_request(request):
            self._in_flight_reauth = False
            return response
        err = detect_api_auth_error(response.text or '')
        if not err:
            return response
        spider.logger.warning(
            'SpaceTrackLoginMiddleware detected auth_error=%s url=%s; '
            'triggering re-auth (attempt=%d/%d)',
            err, request.url, self._reauth_count + 1, self.MAX_REAUTH,
        )
        if self._reauth_count >= self.MAX_REAUTH:
            spider.logger.error(
                'Giving up after %d re-auth attempts; dropping %s',
                self.MAX_REAUTH, request.url,
            )
            if IgnoreRequest is not None:
                raise IgnoreRequest(f'spacetrack auth exhausted: {err}')
            return response
        if self._in_flight_reauth:
            if Request is None:
                return response
            retry = request.copy()
            retry.dont_filter = True
            retry.meta.setdefault('st_retry', 0)
            retry.meta['st_retry'] = retry.meta['st_retry'] + 1
            retry.priority = request.priority - 100
            return retry
        self._in_flight_reauth = True
        self._reauth_count += 1
        if Request is None or FormRequest is None:
            return response
        login_req = Request(
            url=self._login_url,
            callback=self._mw_on_login_page,
            cb_kwargs={
                'retry_request': request,
                'spider_ref': spider,
            },
            dont_filter=True,
            priority=request.priority + 10,
        )
        return login_req

    # ---- callbacks (run in Spider context by Scrapy engine) ----

    def _mw_on_login_page(self, response, retry_request, spider_ref):
        if extract_csrf is None or build_login_formdata is None or FormRequest is None:
            return retry_request
        cookie_header = ''
        if hasattr(response.headers, 'getlist'):
            cookies = response.headers.getlist('Set-Cookie')
            cookie_header = '; '.join(
                c.decode('latin1', errors='ignore').split(';', 1)[0] for c in cookies if c
            )
        tok, _ = extract_csrf(response.text or '', cookie_header)
        if not tok:
            spider_ref.logger.warning('SpaceTrackLoginMiddleware: csrf extract failed; retry original')
            return retry_request
        form = build_login_formdata(tok, self._user or '', self._password or '')
        # Use an explicit FormRequest instead of FormRequest.from_response() —
        # the latter auto-embeds ALL inputs/selects from the page which
        # Space-Track's Apache tier rejects with HTTP 400 because of hidden
        # tracker/UI fields that the browser never actually POSTs back.
        login_post_url = self._login_url or (response.url or '').split('#', 1)[0].split('?', 1)[0]
        return FormRequest(
            url=login_post_url,
            formdata=form,
            callback=self._mw_on_login_post_done,
            cb_kwargs={
                'retry_request': retry_request,
                'spider_ref': spider_ref,
            },
            dont_filter=True,
            priority=retry_request.priority + 5,
        )

    def _mw_on_login_post_done(self, response, retry_request, spider_ref):
        # Anti-bot measure #3: POST /auth/login returns 200 + empty body
        # whether credentials are right or wrong.  We must not trust the body
        # — we confirm the session via a tiny authenticated probe instead.
        body = (response.text or '').strip()
        auth_err = detect_api_auth_error(body) if (body and detect_api_auth_error is not None) else None
        if response.status != 200 or auth_err:
            spider_ref.logger.error(
                'SpaceTrackLoginMiddleware POST login hard-fail. status=%s auth_err=%r body=%r',
                response.status, auth_err, (body[:200] if body else ''),
            )
            self._in_flight_reauth = False
            return retry_request
        # Re-run the 1-row SatCat probe to make sure chocolatechip cookie
        # was actually dropped.  Only if it passes do we release the
        # original GP request.
        if Request is None:
            self._in_flight_reauth = False
            return retry_request
        return Request(
            url=self._probe_url(),
            callback=self._mw_on_login_probe_done,
            cb_kwargs={
                'retry_request': retry_request,
                'spider_ref': spider_ref,
            },
            dont_filter=True,
            priority=retry_request.priority + 3,
        )

    def _mw_on_login_probe_done(self, response, retry_request, spider_ref):
        body = (response.text or '').strip()
        auth_err = detect_api_auth_error(body) if (body and detect_api_auth_error is not None) else None
        self._in_flight_reauth = False
        if not body or auth_err:
            spider_ref.logger.error(
                'SpaceTrackLoginMiddleware session probe FAILED after re-auth. '
                'auth_err=%r body_len=%d snippet=%r. Re-issuing GP request anyway '
                '(Spider callbacks will catch the error if it repeats).',
                auth_err, len(body), (body[:200] if body else ''),
            )
        else:
            spider_ref.logger.info(
                'SpaceTrackLoginMiddleware session probe PASSED after re-auth '
                '(body_len=%d). Re-issuing original GP request.',
                len(body),
            )
        retry = retry_request.copy()
        retry.dont_filter = True
        retry.priority = retry_request.priority - 99
        return retry
