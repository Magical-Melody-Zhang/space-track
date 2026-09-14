import datetime
from typing import Optional, Dict, Any, Tuple

from pydantic import (
    BaseModel,
    field_validator,
    model_validator,
    ConfigDict,
)

try:
    from .tools.orbit import classify_orbit, normalize_object_type, should_filter_out
except ImportError:
    try:
        from tools.orbit import classify_orbit, normalize_object_type, should_filter_out
    except ImportError:
        try:
            from .config import (
                ORBIT_RULES,
                ORBIT_CLASS_GEO,
                ORBIT_CLASS_MEO,
                ORBIT_CLASS_LEO,
                ORBIT_CLASS_HEO,
                ORBIT_CLASS_OTHER,
                OBJECT_TYPE_MAP,
                OBJECT_TYPE_DEFAULT,
                FILTER_NORAD_MIN,
                FILTER_NAME_PREFIX_TBA,
            )
        except ImportError:
            from config import (
                ORBIT_RULES,
                ORBIT_CLASS_GEO,
                ORBIT_CLASS_MEO,
                ORBIT_CLASS_LEO,
                ORBIT_CLASS_HEO,
                ORBIT_CLASS_OTHER,
                OBJECT_TYPE_MAP,
                OBJECT_TYPE_DEFAULT,
                FILTER_NORAD_MIN,
                FILTER_NAME_PREFIX_TBA,
            )

        def classify_orbit(mean_motion: float, eccentricity: float) -> str:
            geo_mm_lo, geo_mm_hi = ORBIT_RULES['GEO_MEAN_MOTION']
            _, geo_ecc_hi = ORBIT_RULES['GEO_MAX_ECC']
            meo_p_lo, meo_p_hi = ORBIT_RULES['MEO_PERIOD']
            _, meo_ecc_hi = ORBIT_RULES['MEO_MAX_ECC']
            leo_mm_lo, _ = ORBIT_RULES['LEO_MIN_MEAN_MOTION']
            _, leo_ecc_hi = ORBIT_RULES['LEO_MAX_ECC']
            heo_ecc_lo, _ = ORBIT_RULES['HEO_MIN_ECC']
            period = 1440.0 / mean_motion if mean_motion > 0 else float('inf')
            if geo_mm_lo <= mean_motion <= geo_mm_hi and eccentricity < geo_ecc_hi:
                return ORBIT_CLASS_GEO
            if meo_p_lo <= period <= meo_p_hi and eccentricity < meo_ecc_hi:
                return ORBIT_CLASS_MEO
            if mean_motion > leo_mm_lo and eccentricity < leo_ecc_hi:
                return ORBIT_CLASS_LEO
            if eccentricity > heo_ecc_lo:
                return ORBIT_CLASS_HEO
            return ORBIT_CLASS_OTHER

        def normalize_object_type(raw: Optional[str]) -> str:
            if not raw:
                return OBJECT_TYPE_DEFAULT
            return OBJECT_TYPE_MAP.get(raw.strip().upper(), OBJECT_TYPE_DEFAULT)

        def should_filter_out(norad_id: int, object_name: Optional[str]) -> bool:
            if norad_id >= FILTER_NORAD_MIN:
                return True
            if object_name and object_name.strip().startswith(FILTER_NAME_PREFIX_TBA):
                return True
            return False

# Always define orbit/object constants locally so downstream validators don't
# depend on which import path was selected.
ORBIT_CLASS_GEO = 'GEO'
ORBIT_CLASS_MEO = 'MEO'
ORBIT_CLASS_LEO = 'LEO'
ORBIT_CLASS_HEO = 'HEO'
ORBIT_CLASS_OTHER = 'OTHER'
OBJECT_TYPE_DEFAULT = 'UNK'
FILTER_NORAD_MIN = 90000
FILTER_NAME_PREFIX_TBA = 'TBA'

try:
    from SpaceUtils.dateTimeUtil import TTimeToYMDHMS as _ttime
except ImportError:
    def _ttime(epoch_str: str) -> str:
        if not epoch_str:
            return ''
        try:
            dt = datetime.datetime.fromisoformat(epoch_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError, TypeError):
            return str(epoch_str)


class SpaceTrackGPRow(BaseModel):
    model_config = ConfigDict(extra='allow', populate_by_name=True)

    NORAD_CAT_ID: Any
    OBJECT_ID: Optional[str] = ''
    OBJECT_NAME: Optional[str] = ''
    EPOCH: Optional[str] = ''
    TLE_LINE1: Optional[str] = ''
    TLE_LINE2: Optional[str] = ''
    MEAN_MOTION: Any
    ECCENTRICITY: Any
    PERIOD: Optional[Any] = None
    PERIAPSIS: Optional[Any] = None
    APOAPSIS: Optional[Any] = None
    SEMIMAJOR_AXIS: Optional[Any] = None
    INCLINATION: Optional[Any] = None
    RA_OF_ASC_NODE: Optional[Any] = None
    ARG_OF_PERICENTER: Optional[Any] = None
    MEAN_ANOMALY: Optional[Any] = None
    REV_AT_EPOCH: Optional[Any] = None
    OBJECT_TYPE: Optional[str] = None
    RCS_SIZE: Optional[str] = ''
    COUNTRY_CODE: Optional[str] = ''
    LAUNCH_DATE: Optional[str] = ''
    SITE: Optional[str] = ''
    DECAY_DATE: Optional[str] = ''

    @field_validator('NORAD_CAT_ID', mode='before')
    @classmethod
    def _parse_norad(cls, v: Any) -> int:
        return int(v)

    @field_validator('MEAN_MOTION', 'ECCENTRICITY', mode='before')
    @classmethod
    def _parse_float_req(cls, v: Any) -> float:
        return float(v) if v is not None and v != '' else 0.0

    @field_validator(
        'PERIOD', 'PERIAPSIS', 'APOAPSIS', 'SEMIMAJOR_AXIS',
        'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER',
        'MEAN_ANOMALY', 'REV_AT_EPOCH',
        mode='before',
    )
    @classmethod
    def _parse_float_opt(cls, v: Any) -> Optional[float]:
        if v is None or v == '':
            return None
        return float(v)

    @model_validator(mode='after')
    def _apply_filters(self) -> 'SpaceTrackGPRow':
        if should_filter_out(int(self.NORAD_CAT_ID), self.OBJECT_NAME or ''):
            raise ValueError('filtered')
        return self


class GPLatestModel(BaseModel):
    norad_id: int
    intldes: str
    name: str
    epoch: str
    tle1: str
    tle2: str
    orbit_class: str
    period: Optional[float] = None
    perigee: Optional[float] = None
    apogee: Optional[float] = None
    semimajor_axis: Optional[float] = None
    eccentricity: Optional[float] = None
    inclination: Optional[float] = None
    raan: Optional[float] = None
    arg_perigee: Optional[float] = None
    mean_anomaly: Optional[float] = None
    rev_at_epoch: Optional[float] = None
    object_type: str
    rcs_size: str
    country_code: str
    launch_date: str
    launch_site: str
    decay_date: str

    @field_validator('orbit_class')
    @classmethod
    def _orbit_class_set(cls, v: str) -> str:
        allowed = {ORBIT_CLASS_GEO, ORBIT_CLASS_MEO, ORBIT_CLASS_LEO,
                   ORBIT_CLASS_HEO, ORBIT_CLASS_OTHER}
        return v if v in allowed else ORBIT_CLASS_OTHER

    @field_validator('object_type')
    @classmethod
    def _object_type_set(cls, v: str) -> str:
        return v or OBJECT_TYPE_DEFAULT

    def to_db_tuple(self) -> Tuple[Any, ...]:
        return (
            self.norad_id, self.intldes, self.name, self.epoch,
            self.tle1, self.tle2, self.orbit_class, self.period,
            self.perigee, self.apogee, self.semimajor_axis,
            self.eccentricity, self.inclination, self.raan,
            self.arg_perigee, self.mean_anomaly, self.rev_at_epoch,
            self.object_type, self.rcs_size, self.country_code,
            self.launch_date, self.launch_site, self.decay_date,
        )


class HistoryTLEModel(BaseModel):
    norad_id: int
    sate_name: str
    epoch: str
    tle1: str
    tle2: str
    orbit_class: str
    period: Optional[float] = None
    sate_type: str = ''
    fixed_lon: float = 0.0
    update_time: str = ''

    def to_db_tuple(self) -> Tuple[Any, ...]:
        return (
            self.norad_id, self.sate_name, self.epoch, self.tle1, self.tle2,
            self.orbit_class, self.period, self.sate_type,
            self.fixed_lon, self.update_time,
        )

    @property
    def epoch_year(self) -> Optional[int]:
        try:
            return int(self.epoch[:4])
        except (ValueError, IndexError, TypeError):
            return None


class SatCatTLEModel(BaseModel):
    norad_id: int
    epoch: str
    tle1: str
    tle2: str
    update_time: str = ''

    def to_db_tuple(self) -> Tuple[Any, ...]:
        return self.norad_id, self.epoch, self.tle1, self.tle2, self.update_time


def build_models(
    raw: Dict[str, Any],
    update_time: Optional[str] = None,
) -> Optional[Tuple[GPLatestModel, HistoryTLEModel, SatCatTLEModel]]:
    try:
        row = SpaceTrackGPRow(**raw)
    except (ValueError, TypeError):
        return None

    epoch_formatted = _ttime(row.EPOCH or '')
    orbit_class = classify_orbit(float(row.MEAN_MOTION), float(row.ECCENTRICITY))
    obj_type = normalize_object_type(row.OBJECT_TYPE)
    if update_time is None:
        update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    gp = GPLatestModel(
        norad_id=row.NORAD_CAT_ID,
        intldes=row.OBJECT_ID or '',
        name=(row.OBJECT_NAME or '').strip(),
        epoch=epoch_formatted,
        tle1=row.TLE_LINE1 or '',
        tle2=row.TLE_LINE2 or '',
        orbit_class=orbit_class,
        period=row.PERIOD,
        perigee=row.PERIAPSIS,
        apogee=row.APOAPSIS,
        semimajor_axis=row.SEMIMAJOR_AXIS,
        eccentricity=row.ECCENTRICITY,
        inclination=row.INCLINATION,
        raan=row.RA_OF_ASC_NODE,
        arg_perigee=row.ARG_OF_PERICENTER,
        mean_anomaly=row.MEAN_ANOMALY,
        rev_at_epoch=row.REV_AT_EPOCH,
        object_type=obj_type,
        rcs_size=row.RCS_SIZE or '',
        country_code=row.COUNTRY_CODE or '',
        launch_date=row.LAUNCH_DATE or '',
        launch_site=row.SITE or '',
        decay_date=row.DECAY_DATE or '',
    )

    hist = HistoryTLEModel(
        norad_id=row.NORAD_CAT_ID,
        sate_name=(row.OBJECT_NAME or '').strip(),
        epoch=epoch_formatted,
        tle1=row.TLE_LINE1 or '',
        tle2=row.TLE_LINE2 or '',
        orbit_class=orbit_class,
        period=row.PERIOD,
        sate_type='',
        fixed_lon=0.0,
        update_time=update_time,
    )

    sat = SatCatTLEModel(
        norad_id=row.NORAD_CAT_ID,
        epoch=epoch_formatted,
        tle1=row.TLE_LINE1 or '',
        tle2=row.TLE_LINE2 or '',
        update_time=update_time,
    )

    return gp, hist, sat
