"""
Space-Track GP Spider Settings
For downloading latest General Perturbations (GP / TLE) from www.space-track.org
"""
import os
from datetime import datetime

try:
    from GlobalConfig import GLOBAL_CONFIG
except ImportError:
    GLOBAL_CONFIG = {}

BOT_NAME = "scrapy_space-track"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

DOWNLOAD_DELAY = 3.0
RANDOMIZE_DOWNLOAD_DELAY = True
AUTOTHROTTLE_ENABLED = False

COOKIES_ENABLED = True
COOKIES_DEBUG = False

DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'middlewares.FixedHeadersMiddleware': 300,
    'middlewares.SpaceTrackLoginMiddleware': 400,
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700,
}

DOWNLOAD_TIMEOUT = 180
DOWNLOAD_MAXSIZE = 500 * 1024 * 1024

DNS_CACHE_ENABLED = True

REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 5

RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [401, 403, 408, 429, 500, 502, 503, 504, 522, 524]
RETRY_PRIORITY_ADJUST = -1

HTTPERROR_ALLOWED_CODES = [401, 403, 429]

LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'
LOG_FILE = None

TELNETCONSOLE_ENABLED = False

SPIDER_PT = None

REQUEST_FINGERPRINTER_IMPLEMENTATION = '2.7'

TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'

SPACETRACK_USER = GLOBAL_CONFIG.get('SpaceTrack/user', '')
SPACETRACK_PASSWORD = GLOBAL_CONFIG.get('SpaceTrack/password', '')
SPACETRACK_BASE = 'https://www.space-track.org'
SPACETRACK_LOGIN_URL = f'{SPACETRACK_BASE}/auth/login'
SPACETRACK_GP_EPOCH_WINDOW = 'now-30'
SPACETRACK_GP_ORDERBY = 'NORAD_CAT_ID,EPOCH'
SPACETRACK_GP_QUERY_CSV = (
    f'{SPACETRACK_BASE}/basicspacedata/query/class/gp/'
    f'EPOCH/%3E{SPACETRACK_GP_EPOCH_WINDOW}/'
    f'orderby/{SPACETRACK_GP_ORDERBY}/format/csv'
)
SPACETRACK_GP_QUERY_JSON = (
    f'{SPACETRACK_BASE}/basicspacedata/query/class/gp/'
    f'EPOCH/%3E{SPACETRACK_GP_EPOCH_WINDOW}/'
    f'orderby/{SPACETRACK_GP_ORDERBY}/format/json'
)

DEFAULT_REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,application/json,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'max-age=0',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'upgrade-insecure-requests': '1',
    'Referer': SPACETRACK_BASE,
    'Origin': SPACETRACK_BASE,
}

FILTER_NORAD_MIN = 270000
FILTER_NAME_PREFIX_TBA = 'TBA'
BATCH_INSERT_SIZE = 1000

ITEM_PIPELINES = {
    'pipelines.SchemaValidatePipeline': 100,
    'pipelines.GPLatestDBPipeline': 300,
    'pipelines.HistoryTLEDBPipeline': 310,
    'pipelines.SatCatTLEDBPipeline': 320,
    'pipelines.ConsolePrintPipeline': 500,
}

TABLE_GP_LATEST = GLOBAL_CONFIG.get(
    'SpaceTrack/gp_latest_table', 'ods_spider_spacetrack_latest_df'
)
TABLE_SATCAT   = GLOBAL_CONFIG.get(
    'SpaceTrack/satcat_table',   'ods_spider_spacetrack_satcat_df'
)
HISTORY_TLE_TABLE_PREFIX = GLOBAL_CONFIG.get(
    'SpaceTrack/tle_history_prefix', 'ods_spider_spacetrack_tle_'
)

SCHEMA_VALIDATE_ENABLED = True
GP_LATEST_PIPELINE_ENABLED = False
HISTORY_TLE_PIPELINE_ENABLED = False
SATCAT_TLE_PIPELINE_ENABLED = False

CONSOLE_PRINT_ENABLED = True
CONSOLE_PRINT_PRETTY = True
CONSOLE_PRINT_OUTPUT_FILE = ''

CLOSESPIDER_ITEMCOUNT = 60

CSV_EXPORT_ENABLED = False
CSV_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
CSV_NAME_TEMPLATE = 'FullCatalog-{date}.csv'

DB_BACKEND = GLOBAL_CONFIG.get('SpaceTrack/db_backend', 'mysql').lower()

MYSQL_HOST = GLOBAL_CONFIG.get('SpaceTrack/mysql_host', '127.0.0.1')
MYSQL_PORT = int(GLOBAL_CONFIG.get('SpaceTrack/mysql_port', 3306))
MYSQL_USER = GLOBAL_CONFIG.get('SpaceTrack/mysql_user', 'root')
MYSQL_PASSWORD = GLOBAL_CONFIG.get('SpaceTrack/mysql_password', '')
MYSQL_DB = GLOBAL_CONFIG.get('SpaceTrack/mysql_db', 'xtck')
MYSQL_CHARSET = GLOBAL_CONFIG.get('SpaceTrack/mysql_charset', 'utf8mb4')
MYSQL_AUTOCOMMIT = False
MYSQL_CONNECT_TIMEOUT = 30

TLE_MYSQL_HOST = GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_host', MYSQL_HOST)
TLE_MYSQL_PORT = int(GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_port', MYSQL_PORT))
TLE_MYSQL_USER = GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_user', MYSQL_USER)
TLE_MYSQL_PASSWORD = GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_password', MYSQL_PASSWORD)
TLE_MYSQL_DB = GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_db', MYSQL_DB)
TLE_MYSQL_CHARSET = GLOBAL_CONFIG.get('SpaceTrack/tle_mysql_charset', MYSQL_CHARSET)

STARROCKS_ENABLED = False
STARROCKS_HOST = GLOBAL_CONFIG.get('SpaceTrack/starrocks_host', '')
STARROCKS_PORT = int(GLOBAL_CONFIG.get('SpaceTrack/starrocks_port', 9030))
STARROCKS_USER = GLOBAL_CONFIG.get('SpaceTrack/starrocks_user', '')
STARROCKS_PASSWORD = GLOBAL_CONFIG.get('SpaceTrack/starrocks_password', '')
STARROCKS_DB = GLOBAL_CONFIG.get('SpaceTrack/starrocks_db', '')
STARROCKS_CHARSET = 'utf8mb4'
STARROCKS_BATCH_SIZE = BATCH_INSERT_SIZE
