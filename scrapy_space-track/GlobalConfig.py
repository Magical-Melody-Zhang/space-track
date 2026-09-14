"""
Standalone-test mock: GlobalConfig.
In enterprise env this module is injected by the outer platform.  For isolated testing
we return plausible defaults so every `.get(key, default)` calls in setting.py /
config.py resolve without errors.

NOTE: This file keeps ONLY the keys that the ORIGINAL (pre-extraction) project
expected.  Cookie-bypass keys and client-hint keys added in a prior step are
INTENTIONALLY removed here so the codebase defaults back to the original
username + password login flow.
"""
from typing import Any, Dict

GLOBAL_CONFIG: Dict[str, Any] = {
    "SpaceTrack/user": "815398413@qq.com",
    "SpaceTrack/password": "abcde0123456789",
    "SpaceTrack/gp_latest_table": "ods_spider_spacetrack_latest_df",
    "SpaceTrack/satcat_table": "ods_spider_spacetrack_satcat_df",
    "SpaceTrack/tle_history_prefix": "ods_spider_spacetrack_tle_",
    "SpaceTrack/db_backend": "mysql",
    "SpaceTrack/mysql_host": "127.0.0.1",
    "SpaceTrack/mysql_port": 3306,
    "SpaceTrack/mysql_user": "root",
    "SpaceTrack/mysql_password": "",
    "SpaceTrack/mysql_db": "xtck",
    "SpaceTrack/mysql_charset": "utf8mb4",
    "SpaceTrack/tle_mysql_host": "127.0.0.1",
    "SpaceTrack/tle_mysql_port": 3306,
    "SpaceTrack/tle_mysql_user": "root",
    "SpaceTrack/tle_mysql_password": "",
    "SpaceTrack/tle_mysql_db": "xtck",
    "SpaceTrack/tle_mysql_charset": "utf8mb4",
    "SpaceTrack/starrocks_host": "",
    "SpaceTrack/starrocks_port": 9030,
    "SpaceTrack/starrocks_user": "",
    "SpaceTrack/starrocks_password": "",
    "SpaceTrack/starrocks_db": "",
}
