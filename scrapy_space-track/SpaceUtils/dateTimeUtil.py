"""
Standalone-test mock: SpaceUtils.dateTimeUtil.TTimeToYMDHMS.

The enterprise version wraps a C++ extension; for isolated testing we use the
same fallback already present in schemas.py.  This module is only imported by
schemas.py and only when present, so replicate that fallback and this mock must agree
stay behaviour-identical.
"""
import datetime


def TTimeToYMDHMS(epoch_str: str) -> str:
    if not epoch_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(epoch_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError, TypeError):
        return str(epoch_str)
