import csv
import datetime
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymysql
except ImportError:  # pragma: no cover - pymysql is mandatory in runtime; here we allow import lint
    pymysql = None

try:
    from .schemas import (
        GPLatestModel,
        HistoryTLEModel,
        SatCatTLEModel,
    )
except ImportError:
    try:
        from schemas import (
            GPLatestModel,
            HistoryTLEModel,
            SatCatTLEModel,
        )
    except ImportError:  # pragma: no cover
        GPLatestModel = None
        HistoryTLEModel = None
        SatCatTLEModel = None

logger = logging.getLogger(__name__)


# ---------- helpers ----------

def _chunks(lst: List[Any], size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _year_table(prefix: str, year: Optional[int]) -> str:
    if year is None or year <= 0:
        return f'{prefix}misc_df'
    return f'{prefix}{year}_df'


class MySQLClient:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        charset: str = 'utf8mb4',
        autocommit: bool = False,
        connect_timeout: int = 30,
    ):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.db = db
        self.charset = charset
        self.autocommit = autocommit
        self.connect_timeout = connect_timeout
        self._conn: Optional[Any] = None

    def connect(self):
        if pymysql is None:
            logger.error('pymysql not installed. Run: pip install pymysql')
            return None
        if self._conn is not None:
            try:
                self._conn.ping(reconnect=True)
                return self._conn
            except Exception:
                self._conn = None
        try:
            self._conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db,
                charset=self.charset,
                autocommit=self.autocommit,
                connect_timeout=self.connect_timeout,
            )
        except Exception as exc:
            logger.error('MySQL connect failed %s@%s:%s/%s : %s',
                         self.user, self.host, self.port, self.db, exc)
            self._conn = None
        return self._conn

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def executemany_commit(self, sql: str, rows: List[Tuple[Any, ...]], batch: int) -> int:
        conn = self.connect()
        if conn is None or not rows:
            return 0
        affected = 0
        try:
            with conn.cursor() as cur:
                for sub in _chunks(rows, batch):
                    cur.executemany(sql, sub)
                    affected += cur.rowcount or 0
            conn.commit()
        except Exception as exc:
            logger.error('executemany failed sql[:120]=%s error=%s rows=%d', sql[:120], exc, len(rows))
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        return affected


# ---------- SQL (mirrors original gp.py) ----------

SQL_GP_LATEST_UPSERT = '''
INSERT INTO {table} (
  norad_id, intldes, name, epoch, tle1, tle2, orbit_class, period, perigee, apogee,
  semimajorAxis, eccentricity, inclination, raan, argPerigee, meanAnomaly,
  rev_at_epoch, object_type, rcs_size, country_code, launch_date, launch_site, decay_date
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  name = VALUES(name), epoch = VALUES(epoch), tle1 = VALUES(tle1), tle2 = VALUES(tle2),
  orbit_class = VALUES(orbit_class), period = VALUES(period), perigee = VALUES(perigee),
  apogee = VALUES(apogee), semimajorAxis = VALUES(semimajorAxis),
  eccentricity = VALUES(eccentricity), inclination = VALUES(inclination),
  raan = VALUES(raan), argPerigee = VALUES(argPerigee), meanAnomaly = VALUES(meanAnomaly),
  rev_at_epoch = VALUES(rev_at_epoch), object_type = VALUES(object_type),
  rcs_size = VALUES(rcs_size), country_code = VALUES(country_code),
  launch_date = VALUES(launch_date), launch_site = VALUES(launch_site),
  decay_date = VALUES(decay_date)
'''.strip()

SQL_HISTORY_TLE_UPSERT = '''
INSERT INTO {table} (
  norad_id, sate_name, epoch, tle1, tle2, orbit_class, period, sate_type, fixedLon, update_time
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  epoch = VALUES(epoch), sate_name = VALUES(sate_name), tle1 = VALUES(tle1),
  tle2 = VALUES(tle2), period = VALUES(period), update_time = VALUES(update_time)
'''.strip()

SQL_SATCAT_UPSERT = '''
INSERT INTO {table} (norad_id, epoch, tle1, tle2, update_time)
VALUES (%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  epoch = VALUES(epoch), tle1 = VALUES(tle1), tle2 = VALUES(tle2),
  update_time = VALUES(update_time)
'''.strip()


# ---------- 1. SchemaValidate ----------

class SchemaValidatePipeline:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.ok = 0
        self.dropped = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(enabled=crawler.settings.getbool('SCHEMA_VALIDATE_ENABLED', True))

    def open_spider(self, spider):
        if self.enabled:
            spider.logger.info('SchemaValidatePipeline enabled.')

    def process_item(self, item, spider):
        if not self.enabled:
            return item
        try:
            norad = int(item.get('norad_id'))
            if norad <= 0:
                raise ValueError('invalid norad_id')
        except Exception as exc:
            self.dropped += 1
            from scrapy.exceptions import DropItem
            raise DropItem(f'invalid item: {exc}')
        self.ok += 1
        return item

    def close_spider(self, spider):
        spider.logger.info('SchemaValidate summary ok=%d dropped=%d', self.ok, self.dropped)


# ---------- 2. GPLatest ----------

class GPLatestDBPipeline:
    def __init__(self, settings):
        self.enabled = settings.getbool('GP_LATEST_PIPELINE_ENABLED', True)
        self.batch = int(settings.get('BATCH_INSERT_SIZE', 1000))
        self.table = settings.get('TABLE_GP_LATEST', settings.get('GP_LATEST_TABLE', 'xt_gp_lastest'))
        self._client: Optional[MySQLClient] = None
        self._buf: List[Tuple[Any, ...]] = []
        self._written = 0
        self._closed = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(settings=crawler.settings)

    def open_spider(self, spider):
        if not self.enabled:
            spider.logger.info('GPLatestDBPipeline disabled.')
            return
        s = spider.settings
        self._client = MySQLClient(
            host=s.get('MYSQL_HOST', '127.0.0.1'),
            port=int(s.get('MYSQL_PORT', 3306)),
            user=s.get('MYSQL_USER', 'root'),
            password=s.get('MYSQL_PASSWORD', ''),
            db=s.get('MYSQL_DB', 'xtck'),
            charset=s.get('MYSQL_CHARSET', 'utf8mb4'),
            autocommit=bool(s.get('MYSQL_AUTOCOMMIT', False)),
            connect_timeout=int(s.get('MYSQL_CONNECT_TIMEOUT', 30)),
        )

    def process_item(self, item, spider):
        if not self.enabled:
            return item
        if item.__class__.__name__ != 'GPLatestItem':
            return item
        if GPLatestModel is None:
            return item
        try:
            data = {k: item.get(k) for k in GPLatestModel.model_fields}
            model = GPLatestModel(**data)
        except Exception as exc:
            spider.logger.debug('GPLatestModel build fail norad=%s err=%s', item.get('norad_id'), exc)
            return item
        self._buf.append(model.to_db_tuple())
        if len(self._buf) >= self.batch:
            self._flush(spider)
        return item

    def _flush(self, spider):
        if not self._buf or self._client is None:
            return
        sql = SQL_GP_LATEST_UPSERT.format(table=self.table)
        try:
            affected = self._client.executemany_commit(sql, list(self._buf), self.batch)
            self._written += affected
            spider.logger.info('GPLatestDB flush %d rows -> %s (affected=%d total=%d)',
                              len(self._buf), self.table, affected, self._written)
        finally:
            self._buf.clear()

    def close_spider(self, spider):
        if self._closed:
            return
        self._closed = True
        if self.enabled and self._buf:
            self._flush(spider)
        if self._client is not None:
            self._client.close()
        if self.enabled:
            spider.logger.info('GPLatestDBPipeline closed. written=%d', self._written)


# ---------- 3. SatCat ----------

class SatCatTLEDBPipeline:
    def __init__(self, settings):
        self.enabled = settings.getbool('SATCAT_TLE_PIPELINE_ENABLED', True)
        self.batch = int(settings.get('BATCH_INSERT_SIZE', 1000))
        self.table = settings.get('TABLE_SATCAT', settings.get('SATCAT_TABLE', 'xt_satcat'))
        self._client: Optional[MySQLClient] = None
        self._buf: List[Tuple[Any, ...]] = []
        self._written = 0
        self._closed = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(settings=crawler.settings)

    def open_spider(self, spider):
        if not self.enabled:
            spider.logger.info('SatCatTLEDBPipeline disabled.')
            return
        s = spider.settings
        self._client = MySQLClient(
            host=s.get('MYSQL_HOST', '127.0.0.1'),
            port=int(s.get('MYSQL_PORT', 3306)),
            user=s.get('MYSQL_USER', 'root'),
            password=s.get('MYSQL_PASSWORD', ''),
            db=s.get('MYSQL_DB', 'xtck'),
            charset=s.get('MYSQL_CHARSET', 'utf8mb4'),
            autocommit=bool(s.get('MYSQL_AUTOCOMMIT', False)),
            connect_timeout=int(s.get('MYSQL_CONNECT_TIMEOUT', 30)),
        )

    def process_item(self, item, spider):
        if not self.enabled:
            return item
        if item.__class__.__name__ != 'SatCatTLEItem':
            return item
        if SatCatTLEModel is None:
            return item
        try:
            data = {k: item.get(k) for k in SatCatTLEModel.model_fields}
            model = SatCatTLEModel(**data)
        except Exception as exc:
            spider.logger.debug('SatCatTLEModel build fail norad=%s err=%s', item.get('norad_id'), exc)
            return item
        self._buf.append(model.to_db_tuple())
        if len(self._buf) >= self.batch:
            self._flush(spider)
        return item

    def _flush(self, spider):
        if not self._buf or self._client is None:
            return
        sql = SQL_SATCAT_UPSERT.format(table=self.table)
        try:
            affected = self._client.executemany_commit(sql, list(self._buf), self.batch)
            self._written += affected
            spider.logger.info('SatCatTLEDB flush %d rows -> %s (affected=%d total=%d)',
                              len(self._buf), self.table, affected, self._written)
        finally:
            self._buf.clear()

    def close_spider(self, spider):
        if self._closed:
            return
        self._closed = True
        if self.enabled and self._buf:
            self._flush(spider)
        if self._client is not None:
            self._client.close()
        if self.enabled:
            spider.logger.info('SatCatTLEDBPipeline closed. written=%d', self._written)


# ---------- 4. HistoryTLE (year-partitioned) ----------

class HistoryTLEDBPipeline:
    def __init__(self, settings):
        self.enabled = settings.getbool('HISTORY_TLE_PIPELINE_ENABLED', True)
        self.batch = int(settings.get('BATCH_INSERT_SIZE', 1000))
        self.prefix = settings.get('HISTORY_TLE_TABLE_PREFIX', settings.get('TABLE_HISTORY_TLE_PREFIX', 'xt_tle_'))
        self._client: Optional[MySQLClient] = None
        self._buf: Dict[int, List[Tuple[Any, ...]]] = defaultdict(list)
        self._written = 0
        self._closed = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(settings=crawler.settings)

    def open_spider(self, spider):
        if not self.enabled:
            spider.logger.info('HistoryTLEDBPipeline disabled.')
            return
        s = spider.settings
        self._client = MySQLClient(
            host=s.get('TLE_MYSQL_HOST') or s.get('MYSQL_HOST', '127.0.0.1'),
            port=int(s.get('TLE_MYSQL_PORT') or s.get('MYSQL_PORT', 3306)),
            user=s.get('TLE_MYSQL_USER') or s.get('MYSQL_USER', 'root'),
            password=s.get('TLE_MYSQL_PASSWORD') if s.get('TLE_MYSQL_PASSWORD') is not None else s.get('MYSQL_PASSWORD', ''),
            db=s.get('TLE_MYSQL_DB') or s.get('MYSQL_DB', 'xtck'),
            charset=s.get('TLE_MYSQL_CHARSET') or s.get('MYSQL_CHARSET', 'utf8mb4'),
            autocommit=bool(s.get('MYSQL_AUTOCOMMIT', False)),
            connect_timeout=int(s.get('MYSQL_CONNECT_TIMEOUT', 30)),
        )

    def process_item(self, item, spider):
        if not self.enabled or self._client is None:
            return item
        if item.__class__.__name__ != 'HistoryTLEItem':
            return item
        if HistoryTLEModel is None:
            return item
        try:
            data = {k: item.get(k) for k in HistoryTLEModel.model_fields}
            model = HistoryTLEModel(**data)
        except Exception as exc:
            spider.logger.debug('HistoryTLEModel build fail norad=%s err=%s', item.get('norad_id'), exc)
            return item
        year = model.epoch_year or 0
        self._buf[year].append(model.to_db_tuple())
        if len(self._buf[year]) >= self.batch:
            self._flush_year(spider, year)
        return item

    def _flush_year(self, spider, year):
        rows = self._buf.get(year) or []
        if not rows or self._client is None:
            return
        table = _year_table(self.prefix, year if year != 0 else None)
        sql = SQL_HISTORY_TLE_UPSERT.format(table=table)
        try:
            affected = self._client.executemany_commit(sql, list(rows), self.batch)
            self._written += affected
            spider.logger.info('HistoryTLEDB flush year=%s rows=%d -> %s (affected=%d total=%d)',
                              year, len(rows), table, affected, self._written)
        finally:
            self._buf[year].clear()

    def close_spider(self, spider):
        if self._closed:
            return
        self._closed = True
        if self.enabled:
            for year in sorted(self._buf.keys()):
                if self._buf[year]:
                    self._flush_year(spider, year)
        if self._client is not None:
            self._client.close()
        if self.enabled:
            spider.logger.info('HistoryTLEDBPipeline closed. written=%d prefix=%s',
                             self._written, self.prefix)


# ---------- 5. CSV export (optional) ----------

class CSVExportPipeline:
    FIELDS = [
        'NORAD_CAT_ID', 'OBJECT_ID', 'OBJECT_NAME', 'EPOCH', 'TLE_LINE1', 'TLE_LINE2',
        'MEAN_MOTION', 'ECCENTRICITY', 'PERIOD', 'PERIAPSIS', 'APOAPSIS',
        'SEMIMAJOR_AXIS', 'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER',
        'MEAN_ANOMALY', 'REV_AT_EPOCH', 'OBJECT_TYPE', 'RCS_SIZE', 'COUNTRY_CODE',
        'LAUNCH_DATE', 'SITE', 'DECAY_DATE',
    ]

    def __init__(self, settings):
        self.enabled = settings.getbool('CSV_EXPORT_ENABLED', False)
        self.out_dir = settings.get('CSV_OUTPUT_DIR', 'out')
        self.tpl = settings.get('CSV_NAME_TEMPLATE', 'FullCatalog-{date}.csv')
        self._fp = None
        self._writer = None
        self.path: Optional[str] = None
        self._count = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(settings=crawler.settings)

    def open_spider(self, spider):
        if not self.enabled:
            return
        os.makedirs(self.out_dir, exist_ok=True)
        date_str = datetime.datetime.now().strftime('%Y%m%d')
        self.path = os.path.join(self.out_dir, self.tpl.format(date=date_str))
        self._fp = open(self.path, 'w', newline='', encoding='utf-8')
        self._writer = csv.DictWriter(self._fp, fieldnames=self.FIELDS)
        self._writer.writeheader()
        spider.logger.info('CSV export enabled -> %s', self.path)

    def process_item(self, item, spider):
        if not self.enabled or item.__class__.__name__ != 'GPLatestItem':
            return item
        row = {
            'NORAD_CAT_ID': item.get('norad_id'),
            'OBJECT_ID': item.get('intldes'),
            'OBJECT_NAME': item.get('name'),
            'EPOCH': item.get('epoch'),
            'TLE_LINE1': item.get('tle1'),
            'TLE_LINE2': item.get('tle2'),
            'PERIOD': item.get('period'),
            'PERIAPSIS': item.get('perigee'),
            'APOAPSIS': item.get('apogee'),
            'SEMIMAJOR_AXIS': item.get('semimajor_axis'),
            'ECCENTRICITY': item.get('eccentricity'),
            'INCLINATION': item.get('inclination'),
            'RA_OF_ASC_NODE': item.get('raan'),
            'ARG_OF_PERICENTER': item.get('arg_perigee'),
            'MEAN_ANOMALY': item.get('mean_anomaly'),
            'REV_AT_EPOCH': item.get('rev_at_epoch'),
            'OBJECT_TYPE': item.get('object_type'),
            'RCS_SIZE': item.get('rcs_size'),
            'COUNTRY_CODE': item.get('country_code'),
            'LAUNCH_DATE': item.get('launch_date'),
            'SITE': item.get('launch_site'),
            'DECAY_DATE': item.get('decay_date'),
            'MEAN_MOTION': '',
        }
        try:
            self._writer.writerow(row)
            self._count += 1
        except Exception as exc:
            spider.logger.debug('CSV write fail norad=%s err=%s', item.get('norad_id'), exc)
        return item

    def close_spider(self, spider):
        if self._fp is not None:
            try:
                self._fp.close()
            except Exception:
                pass
            finally:
                self._fp = None
        if self.enabled:
            spider.logger.info('CSV export closed. rows=%d path=%s', self._count, self.path or '')


# ---------- 6. Console print (standalone-test replacement for DB pipelines) ----------

class ConsolePrintPipeline:
    """
    Drop-in replacement for the three DB pipelines during isolated testing.
    Every Item is serialised as a JSON record and written either to stdout
    (legacy default) or to a file specified via ``CONSOLE_PRINT_OUTPUT_FILE``
    (or the ``--output`` CLI flag on the standalone entry).
    """

    def __init__(self, enabled: bool = True, pretty: bool = True, output_file: str = ''):
        self.enabled = enabled
        self.pretty = pretty
        self.output_file = output_file
        self._counts: Dict[str, int] = defaultdict(int)
        self._index = 0
        self._fp: Any = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            enabled=crawler.settings.getbool('CONSOLE_PRINT_ENABLED', True),
            pretty=crawler.settings.getbool('CONSOLE_PRINT_PRETTY', True),
            output_file=crawler.settings.get('CONSOLE_PRINT_OUTPUT_FILE', '') or '',
        )

    def _write(self, *lines: str) -> None:
        if self._fp is not None:
            for line in lines:
                self._fp.write(line + '\n')
        else:
            import sys as _sys
            for line in lines:
                _sys.stdout.write(line + '\n')

    def open_spider(self, spider):
        if not self.enabled:
            return
        if self.output_file:
            parent = os.path.dirname(os.path.abspath(self.output_file))
            if parent:
                os.makedirs(parent, exist_ok=True)
            try:
                self._fp = open(self.output_file, 'w', encoding='utf-8', newline='')
            except OSError as exc:
                spider.logger.error(
                    'ConsolePrintPipeline cannot open output file %r: %s. '
                    'Falling back to stdout.',
                    self.output_file, exc,
                )
                self._fp = None
        if self._fp is not None:
            spider.logger.info(
                'ConsolePrintPipeline enabled. Writing records to file: %s',
                self.output_file,
            )
        else:
            spider.logger.info(
                'ConsolePrintPipeline enabled. DB writes replaced with stdout JSON.'
            )
        banner_tag = f' (to: {self.output_file})' if self._fp is not None else ' (printed to stdout)'
        self._write(
            '',
            '=' * 80,
            ' ConsolePrintPipeline :: Scraped items (DB writes disabled)' + banner_tag,
            '=' * 80,
        )

    def process_item(self, item, spider):
        if not self.enabled:
            return item
        try:
            import json as _json
        except Exception:  # pragma: no cover
            return item
        kind = item.__class__.__name__
        self._index += 1
        self._counts[kind] += 1
        record = dict(item)
        payload = {
            'seq': self._index,
            'kind': kind,
            'data': record,
        }
        if self.pretty:
            line = _json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        else:
            line = _json.dumps(payload, ensure_ascii=False, default=str)
        self._write(line)
        return item

    def close_spider(self, spider):
        if not self.enabled:
            return
        lines = [
            '',
            '-' * 80,
            ' ConsolePrintPipeline summary:',
        ]
        for k, v in sorted(self._counts.items()):
            lines.append(f'   - {k}: {v}')
        lines.append(f'   Total records: {self._index}')
        lines.append('-' * 80)
        self._write(*lines)
        spider.logger.info('ConsolePrintPipeline closed. total=%d output=%s',
                           self._index, self.output_file or '(stdout)')
        if self._fp is not None:
            try:
                self._fp.close()
            finally:
                self._fp = None
