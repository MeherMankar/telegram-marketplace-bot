"""Timezone-aware datetime utilities"""
from datetime import datetime, timezone

def utc_now() -> datetime:
    """Get current UTC time with timezone info"""
    return datetime.now(timezone.utc)

def utc_timestamp() -> float:
    """Get current UTC timestamp"""
    return utc_now().timestamp()