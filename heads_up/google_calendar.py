"""Google Calendar version of CalendarStore: same two methods, real calendar.

    occurrences_on(day)  -> every timed event on that Halifax day
    move_occurrence(...) -> moves ONE occurrence (never the series)

Listing with singleEvents=True makes Google expand each recurring series into
separate occurrences, each with its own id. Patching one of those ids changes
only that occurrence, which is exactly the "one occurrence, never the series"
rule. The series itself (the master event) is never returned, so it can't be
edited by mistake.

Events are matched by extendedProperties.private.category, which
scripts/seed_calendar.py sets when it loads the sample calendar.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .calendar_store import Occurrence
from .timeutil import HALIFAX, local_dt, parse_dt

TZ_NAME = "America/Halifax"


class GoogleCalendarStore:
    def __init__(self, service, calendar_id: str = "primary"):
        self.service = service
        self.calendar_id = calendar_id
        self._series_cache: dict[str, dict] = {}

    # ---- reading -----------------------------------------------------------
    def _category(self, item: dict) -> str | None:
        props = item.get("extendedProperties", {}).get("private", {})
        if "category" in props or not item.get("recurringEventId"):
            return props.get("category")
        # Some occurrences don't repeat the series' properties: look at the series once.
        series_id = item["recurringEventId"]
        if series_id not in self._series_cache:
            self._series_cache[series_id] = self.service.events().get(
                calendarId=self.calendar_id, eventId=series_id).execute()
        return self._series_cache[series_id].get("extendedProperties", {}).get("private", {}).get("category")

    def _to_occurrence(self, item: dict) -> Occurrence:
        overrides = item.get("reminders", {}).get("overrides", []) or []
        return Occurrence(
            event_id=item["id"],
            category=self._category(item),
            summary=item.get("summary", ""),
            start=parse_dt(item["start"]["dateTime"]),
            end=parse_dt(item["end"]["dateTime"]),
            alert_minutes=[o["minutes"] for o in overrides],
            changed="CHANGED by" in item.get("summary", ""),
            location=item.get("location"),
            series_id=item.get("recurringEventId"),
        )

    def occurrences_on(self, day: date) -> list[Occurrence]:
        start = local_dt(day, time(0, 0))
        end = local_dt(day + timedelta(days=1), time(0, 0))
        items, page = [], None
        while True:
            resp = self.service.events().list(
                calendarId=self.calendar_id, timeMin=start.isoformat(), timeMax=end.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=250, pageToken=page,
            ).execute()
            items += resp.get("items", [])
            page = resp.get("nextPageToken")
            if not page:
                break
        found = []
        for item in items:
            if item.get("status") == "cancelled" or "dateTime" not in item.get("start", {}):
                continue  # skip cancelled and all-day events
            occ = self._to_occurrence(item)
            if occ.start.astimezone(HALIFAX).date() == day:
                found.append(occ)
        return sorted(found, key=lambda o: o.start)

    # ---- writing -----------------------------------------------------------
    def move_occurrence(self, occ: Occurrence, new_start: datetime, summary: str,
                        alert_minutes: int) -> Occurrence:
        new_end = new_start + (occ.end - occ.start)
        body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": TZ_NAME},
            "end": {"dateTime": new_end.isoformat(), "timeZone": TZ_NAME},
            "summary": summary,
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": alert_minutes}]},
        }
        updated = self.service.events().patch(
            calendarId=self.calendar_id, eventId=occ.event_id, body=body).execute()
        if updated.get("recurrence"):
            raise RuntimeError("Refusing to continue: a whole series was edited, not one occurrence")
        moved = self._to_occurrence(updated)
        moved.category = moved.category or occ.category
        moved.changed = True
        return moved
