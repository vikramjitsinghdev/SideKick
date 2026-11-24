"""Time helpers. Everything the agent reasons about is in Halifax local time."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# On Windows, zoneinfo needs the `tzdata` package (see requirements.txt).
HALIFAX = ZoneInfo("America/Halifax")


def parse_dt(value: str) -> datetime:
    """Parse an ISO timestamp and convert it to Halifax time."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HALIFAX)
    return dt.astimezone(HALIFAX)


def local_dt(day: date, at: time) -> datetime:
    """Combine a date and a wall-clock time into an aware Halifax datetime (DST-safe)."""
    return datetime.combine(day, at, tzinfo=HALIFAX)


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def short_time(t: time) -> str:
    """15:15 -> '3:15', 17:00 -> '5:00' (Gloria's calendar style, no am/pm)."""
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d}"
