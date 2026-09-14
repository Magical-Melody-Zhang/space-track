import json
from typing import Any, Iterable

import scrapy
from scrapy import FormRequest, Request
from scrapy.http import Response

try:
    from ..items import GPLatestItem, HistoryTLEItem, SatCatTLEItem
    from ..schemas import build_models
    from ..tools.login import extract_csrf, build_login_formdata, detect_api_auth_error
except ImportError:
    from items import GPLatestItem, HistoryTLEItem, SatCatTLEItem
    from schemas import build_models
    from tools.login import extract_csrf, build_login_formdata, detect_api_auth_error


class SpacetrackGPSpider(scrapy.Spider):
    name = 'spacetrack_gp'
    allowed_domains = ['www.space-track.org']

    custom_settings = {}

    def __init__(
        self,
        epoch_window: str = 'now-30',
        limit: str = '',
        offset: str = '',
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.epoch_window = epoch_window or 'now-30'
        self.limit = str(limit) if limit not in (None, '') else ''
        self.offset = str(offset) if offset not in (None, '') else ''
        self._update_time = None

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    async def start(self):  # Scrapy 2.13+ async start() API (start_requests() removed in 2.18)
        if not self._cfg('SPACETRACK_USER') or not self._cfg('SPACETRACK_PASSWORD'):
            self.logger.error(
                'SPACETRACK_USER / SPACETRACK_PASSWORD not set. Check setting.py or GlobalConfig.'
            )
            return

        login_url = self._cfg('SPACETRACK_LOGIN_URL')
        if not login_url:
            self.logger.error('SPACETRACK_LOGIN_URL missing in settings.')
            return

        self.logger.info(
            'Starting SpaceTrack GP spider. epoch_window=%s limit=%s offset=%s',
            self.epoch_window, self.limit or 'ALL', self.offset or '0',
        )
        yield Request(
            url=login_url,
            callback=self._on_login_page,
            errback=self._on_request_error,
            dont_filter=True,
            meta={'_st_stage': 'get_login_page'},
        )

    def _build_gp_url(self) -> str:
        """Build a Space-Track basicspacedata query URL for the GP class.

        Query-segment order is critical: Space-Track parses REST path segments
        left-to-right and silently ignores malformed trailing parts (returning
        0 rows instead of an error).  Order is fixed to:

            class/<C> / <key>/<predicate><value> / orderby/<field> / limit/<N>
              [ / <offset>,<rows> ]? / format/<F>

        The comma-offset form is only appended when BOTH limit AND a non-zero
        offset are given — the server returns zero rows when asked for
        "/limit/0,20" (offset=0 with comma syntax) but works correctly for
        "/limit/20" on its own.
        """
        base = self._cfg('SPACETRACK_BASE', 'https://www.space-track.org')
        orderby = self._cfg('SPACETRACK_GP_ORDERBY', 'NORAD_CAT_ID,EPOCH')
        if not self.limit:
            limit_seg = ''
        else:
            try:
                off = int(self.offset) if self.offset else 0
            except (ValueError, TypeError):
                off = 0
            if off > 0:
                limit_seg = f'/limit/{self.offset},{self.limit}'
            else:
                # Single-argument form — server behaviour is well defined.
                limit_seg = f'/limit/{self.limit}'
        return (
            f'{base}/basicspacedata/query/class/gp/'
            f'EPOCH/%3E{self.epoch_window}/'
            f'orderby/{orderby}{limit_seg}/format/json'
        )

    def _probe_session_url(self) -> str:
        """A tiny authenticated probe that validates the chocolatechip cookie
        was actually dropped after a successful POST login.

        We use a 1-row GP query because the class name is guaranteed to
        exist (it's the same class we use for the real fetch).  Any response
        that isn't the literal "must be logged in" auth error is treated as
        session-valid.  This is required because Space-Track deliberately
        returns HTTP 200 + empty body both for login POST success AND for
        invalid credentials (anti-bot measure #3).
        """
        base = self._cfg('SPACETRACK_BASE', 'https://www.space-track.org')
        return (
            f'{base}/basicspacedata/query/class/gp/'
            f'NORAD_CAT_ID/%3E0/EPOCH/%3Enow-1000/'
            f'orderby/NORAD_CAT_ID/limit/1/format/json'
        )

    def _on_login_page(self, response: Response):
        stage = (response.meta or {}).get('_st_stage')
        self.logger.debug('Login GET done. status=%s stage=%s len=%s url=%s',
                          response.status, stage, len(response.text or ''), response.url)
        login_url = self._cfg('SPACETRACK_LOGIN_URL')
        cookie_header = response.headers.get('Cookie') or response.headers.get('Set-Cookie') or b''
        if isinstance(cookie_header, bytes):
            try:
                cookie_header = cookie_header.decode('utf-8', errors='ignore')
            except Exception:
                cookie_header = ''
        csrf, cookie_csrf = extract_csrf(response.text or '', str(cookie_header))
        if not csrf:
            self.logger.error(
                'Failed to extract CSRF token from login page html. body_len=%d url=%s cookie_csrf=%r',
                len(response.text or ''), response.url, cookie_csrf,
            )
            return
        form = build_login_formdata(
            csrf_token=csrf,
            identity=self._cfg('SPACETRACK_USER', ''),
            password=self._cfg('SPACETRACK_PASSWORD', ''),
        )
        yield FormRequest(
            url=login_url,
            formdata=form,
            callback=self._on_login_post_done,
            errback=self._on_request_error,
            dont_filter=True,
            meta={'_st_stage': 'post_login'},
        )

    def _on_login_post_done(self, response: Response):
        body = (response.text or '').strip()
        status = response.status
        stage = (response.meta or {}).get('_st_stage')
        auth_err = detect_api_auth_error(body) if body else None

        # Space-Track returns HTTP 200 + empty body when credentials are
        # wrong, which is indistinguishable from the "silent redirect"
        # success path.  We therefore don't trust POST body at all — we
        # always fire a 1-row authenticated probe next.
        if status != 200 or (body and auth_err):
            self.logger.error(
                'SpaceTrack login POST failed. status=%s body_len=%s auth_err=%r snippet=%r',
                status, len(body), auth_err, (body[:300] if body else ''),
            )
            return

        self.logger.debug(
            'Login POST returned HTTP %s body_len=%d auth_err=%r; probing session cookie now',
            status, len(body), auth_err,
        )
        yield Request(
            url=self._probe_session_url(),
            callback=self._on_login_probe_done,
            errback=self._on_request_error,
            dont_filter=True,
            meta={'_st_stage': 'probe_session'},
        )

    def _on_login_probe_done(self, response: Response):
        body = (response.text or '').strip()
        auth_err = detect_api_auth_error(body)
        if not body or auth_err:
            self.logger.error(
                'SpaceTrack session probe FAILED. auth_err=%r body_len=%d snippet=%r. '
                'Likely username/password wrong, or account unverified/banned.',
                auth_err, len(body), (body[:300] if body else ''),
            )
            return
        # try JSON decode to be extra-safe
        try:
            payload = json.loads(body)
        except Exception as exc:
            self.logger.error('Session probe JSON decode failed: %s snippet=%r', exc, body[:200])
            return
        if isinstance(payload, dict) and payload.get('error'):
            self.logger.error('Session probe returned explicit error: %r', payload['error'])
            return
        self.logger.info(
            'SpaceTrack session probe PASSED (chocolatechip cookie present). '
            'Probe payload type=%s len=%d. Fetching GP data now.',
            type(payload).__name__, len(body),
        )
        gp_url = self._build_gp_url()
        yield Request(
            url=gp_url,
            callback=self._on_gp_json,
            errback=self._on_request_error,
            dont_filter=True,
            meta={'_st_stage': 'get_gp_json'},
        )

    def _on_gp_json(self, response: Response):
        raw = response.text or ''
        if not raw.strip():
            self.logger.error('GP JSON response empty. url=%s status=%s', response.url, response.status)
            return
        try:
            rows = json.loads(raw)
        except Exception as exc:
            self.logger.error(
                'Failed to decode GP JSON url=%s status=%s len=%s exc=%s snippet=%r',
                response.url, response.status, len(raw), exc, raw[:300],
            )
            return
        auth_err = detect_api_auth_error(raw)
        if auth_err or (isinstance(rows, dict) and rows.get('error')):
            err = auth_err or (isinstance(rows, dict) and rows.get('error'))
            self.logger.error(
                'GP JSON says user is logged out mid-crawl: %r url=%s. '
                'SpaceTrackLoginMiddleware should have intercepted this; re-check settings.',
                err, response.url,
            )
            return
        if not isinstance(rows, list):
            self.logger.error('GP JSON root is not a list (got %s). url=%s', type(rows).__name__, response.url)
            return
        n = len(rows)
        self.logger.info('Received GP JSON rows: %d from url=%s', n, response.url)
        if n == 0:
            # 0 rows is valid for very narrow epoch windows (e.g. now-30 on an
            # idle server).  Log once at WARN so user can widen the window.
            self.logger.warning(
                'GP JSON returned 0 rows. If unexpected, widen epoch_window '
                '(currently %r) or run without --limit to see backfill data.',
                self.epoch_window,
            )
        ok = 0
        dropped = 0
        import datetime
        self._update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for row in rows:
            triple = build_models(row, self._update_time)
            if triple is None:
                dropped += 1
                continue
            gp_model, hist_model, sat_model = triple
            yield GPLatestItem(**gp_model.model_dump())
            yield HistoryTLEItem(**hist_model.model_dump())
            yield SatCatTLEItem(**sat_model.model_dump())
            ok += 1
        self.logger.info('GP JSON parsed ok=%d filtered=%d rows_total=%d', ok, dropped, n)

    def _on_request_error(self, failure):
        self.logger.error(
            'Request error stage=%s url=%s exc=%s',
            getattr(failure.request, 'meta', {}).get('_st_stage', '?'),
            getattr(failure.request, 'url', '?'),
            failure.value,
        )
