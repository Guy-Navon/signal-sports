"""Shared normalization helpers (issue #178) — timestamps and score parsing.

Provider-SPECIFIC field mapping lives in each adapter; these helpers are the
provider-agnostic pieces (UTC timestamp handling, int coercion) so every
adapter normalizes time and scores identically.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_timestamp(
    timestamp: Optional[str] = None,
    date_event: Optional[str] = None,
    time_event: Optional[str] = None,
) -> Optional[str]:
    """Best-effort UTC ISO-8601 string from a provider's time fields.

    Prefers a full timestamp; otherwise composes date + time. Provider times are
    UTC; a naive value is treated as UTC (matching the rest of the schema).
    Returns None when nothing usable is present.
    """
    if timestamp:
        raw = timestamp.strip().replace("Z", "+00:00")
        try:
            return _to_utc_iso(datetime.fromisoformat(raw))
        except ValueError:
            pass

    if date_event:
        t = (time_event or "").strip() or "00:00:00"
        # Some feeds carry "+00:00" or "Z" suffixes on the time.
        t = t.replace("Z", "").split("+")[0].strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return _to_utc_iso(datetime.strptime(f"{date_event.strip()} {t}", fmt))
            except ValueError:
                continue
        try:
            return _to_utc_iso(datetime.strptime(date_event.strip(), "%Y-%m-%d"))
        except ValueError:
            return None
    return None


def parse_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s == "" or s.lower() in {"null", "none"}:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def starts_in_future(start_time_iso: Optional[str], now: Optional[datetime] = None) -> bool:
    if not start_time_iso:
        return False
    now = now or datetime.now(tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(start_time_iso)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt > now
