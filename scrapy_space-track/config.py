import os
from typing import Dict, Tuple

try:
    from GlobalConfig import GLOBAL_CONFIG
except ImportError:
    GLOBAL_CONFIG = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SPACETRACK_BASE = 'https://www.space-track.org'
LOGIN_URL = f'{SPACETRACK_BASE}/auth/login'
GP_EPOCH_WINDOW = 'now-30'
GP_ORDERBY = 'NORAD_CAT_ID,EPOCH'
GP_QUERY_CSV = (
    f'{SPACETRACK_BASE}/basicspacedata/query/class/gp/'
    f'EPOCH/%3E{GP_EPOCH_WINDOW}/orderby/{GP_ORDERBY}/format/csv'
)
GP_QUERY_JSON = (
    f'{SPACETRACK_BASE}/basicspacedata/query/class/gp/'
    f'EPOCH/%3E{GP_EPOCH_WINDOW}/orderby/{GP_ORDERBY}/format/json'
)

DEFAULT_HEADERS = {
    'User-agent': (
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

SPACETRACK_USER = GLOBAL_CONFIG.get('SpaceTrack/user', '')
SPACETRACK_PASSWORD = GLOBAL_CONFIG.get('SpaceTrack/password', '')
LOGIN_BTN = 'LOGIN'

FILTER_NORAD_MIN = 270000
FILTER_NAME_PREFIX_TBA = 'TBA'

ORBIT_CLASS_GEO = 'GEO'
ORBIT_CLASS_MEO = 'MEO'
ORBIT_CLASS_LEO = 'LEO'
ORBIT_CLASS_HEO = 'HEO'
ORBIT_CLASS_OTHER = 'OTHER'

ORBIT_RULES: Dict[str, Tuple[float, float]] = {
    'GEO_MEAN_MOTION': (0.99, 1.01),
    'GEO_MAX_ECC': (0.0, 0.01),
    'MEO_PERIOD': (600.0, 800.0),
    'MEO_MAX_ECC': (0.0, 0.25),
    'LEO_MIN_MEAN_MOTION': (11.25, float('inf')),
    'LEO_MAX_ECC': (0.0, 0.25),
    'HEO_MIN_ECC': (0.25, float('inf')),
}

OBJECT_TYPE_MAP: Dict[str, str] = {
    'PAYLOAD': 'PAY',
    'DEBRIS': 'DEB',
    'ROCKET BODY': 'R/B',
}
OBJECT_TYPE_DEFAULT = 'UNK'

TABLE_GP_LATEST = 'xt_gp_lastest'
TABLE_SATCAT = 'xt_satcat'
TABLE_HISTORY_TLE_PREFIX = 'xt_tle_'
HISTORY_TLE_FIELDS = [
    'norad_id', 'sate_name', 'epoch', 'tle1', 'tle2',
    'orbit_class', 'period', 'sate_type', 'fixed_lon', 'update_time',
]

CSV_OUTPUT_DIR = os.path.join(BASE_DIR, 'out')
CSV_NAME_TEMPLATE = 'FullCatalog-{date}.csv'

BATCH_INSERT_SIZE = 1000

REQUEST_TIMEOUT = 30
DOWNLOAD_MAX_RETRY = 3
DOWNLOAD_RETRY_DELAY = 5
