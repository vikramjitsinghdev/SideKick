"""In-memory calendar in the same shape as Google Calendar events.

Used by the tests and the offline demo. The Google adapter (later) implements
the same two methods: ``occurrences_on`` and ``move_occurrence``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .timeutil import local_dt, parse_dt

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclass
class Occurrence:
    event_id: str
    category: str | None
    summary: str
    start: datetime
    end: datetime
    alert_minutes: list[int] = field(default_factory=list)
    changed: bool = False
    location: str | None = None


def _parse_rrule(rule: str) -> dict[str, str]:
    body = rule.split(":", 1)[1] if rule.startswith("RRULE:") else rule
    return dict(part.split("=", 1) for part in body.split(";"))


def _series_hits(rule: dict[str, str], first: date, day: date) -> bool:
    """Does a WEEKLY or MONTHLY BYDAY series have an occurrence on ``day``?"""
    if day < first:
        return False
    freq, byday = rule.get("FREQ"), rule.get("BYDAY", "")
    if freq == "WEEKLY":
        return day.weekday() in {WEEKDAYS[d] for d in byday.split(",")}
    if freq == "MONTHLY":
        # e.g. 2MO = second Monday of the month
        for token in byday.split(","):
            nth, wd = int(token[:-2]), WEEKDAYS[token[-2:]]
            if day.weekday() == wd and (day.day - 1) // 7 + 1 == nth:
                return True
        return False
    raise ValueError(f"Unsupported recurrence: {rule}")


class CalendarStore:
    def __init__(self, events: list[dict]):
        self.events = copy.deepcopy(events)
        # Single-occurrence edits, keyed by (event_id, date). Never touches the series.
        self.overrides: dict[tuple[str, date], Occurrence] = {}

    @classmethod
    def from_sample(cls, data: dict) -> "CalendarStore":
        return cls(data["events"])

    def occurrences_on(self, day: date) -> list[Occurrence]:
        found = []
        for ev in self.events:
            if (ev["id"], day) in self.overrides:
                found.append(self.overrides[(ev["id"], day)])
                continue
            start, end = parse_dt(ev["start"]["dateTime"]), parse_dt(ev["end"]["dateTime"])
            rules = ev.get("recurrence")
            if rules:
                if not _series_hits(_parse_rrule(rules[0]), start.date(), day):
                    continue
                duration = end - start
                start = local_dt(day, start.timetz().replace(tzinfo=None))
                end = start + duration
            elif start.date() != day:
                continue
            found.append(Occurrence(
                event_id=ev["id"],
                category=ev.get("extendedProperties", {}).get("private", {}).get("category"),
                summary=ev["summary"],
                start=start,
                end=end,
                alert_minutes=[o["minutes"] for o in ev.get("reminders", {}).get("overrides", [])],
                location=ev.get("location"),
            ))
        return sorted(found, key=lambda o: o.start)

    def move_occurrence(self, occ: Occurrence, new_start: datetime, summary: str,
                        alert_minutes: int) -> Occurrence:
        """Move ONE occurrence, keeping its length. The series itself is never edited."""
        moved = Occurrence(
            event_id=occ.event_id,
            category=occ.category,
            summary=summary,
            start=new_start,
            end=new_start + (occ.end - occ.start),
            alert_minutes=[alert_minutes],
            changed=True,
            location=occ.location,
        )
        self.overrides[(occ.event_id, occ.start.date())] = moved
        return moved
