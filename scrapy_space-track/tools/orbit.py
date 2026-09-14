import re
from typing import Optional, Tuple, Any, Dict

try:
    from ..config import (
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
