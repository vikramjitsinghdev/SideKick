"""GoogleCalendarStore against a fake Google Calendar service (no network, no sign-in).

The fake expands the sample calendar into per-occurrence items the way Google
does with singleEvents=True, and records every call, so we can check exactly
what would be sent to Google.
"""
import importlib.util
from datetime import date, timedelta

import pytest

from heads_up.calendar_store import CalendarStore
from heads_up.google_calendar import GoogleCalendarStore
from heads_up.rules import EDIT, Message, apply, decide
from heads_up.timeutil import parse_dt
from conftest import load
from test_rules import CASES, GOLD


class _Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeEvents:
    def __init__(self, items, masters):
        self.items, self.masters, self.calls = items, masters, []

    def list(self, **kw):
        self.calls.append(("list", kw))
        lo, hi = parse_dt(kw["timeMin"]), parse_dt(kw["timeMax"])
        hits = [i for i in self.items.values()
                if "dateTime" not in i["start"] or lo <= parse_dt(i["start"]["dateTime"]) < hi]
        return _Call(lambda: {"items": [dict(i) for i in hits]})

    def get(self, calendarId, eventId):
        self.calls.append(("get", eventId))
        return _Call(lambda: self.masters[eventId])

    def patch(self, calendarId, eventId, body):
        self.calls.append(("patch", eventId, body))
        def run():
            self.items[eventId].update(body)
            return dict(self.items[eventId])
        return _Call(run)


class FakeService:
    def __init__(self, items, masters):
        self._events = FakeEvents(items, masters)

    def events(self):
        return self._events


def fake_google(drop_props_for=()):
    """Expand Oct 19-25 + Nov 3 of the sample calendar into Google-style occurrence items."""
    sample = load("calendar_events.json")["events"]
    masters = {e["id"]: e for e in sample}
    local = CalendarStore(sample)
    items = {}
    days = [date(2026, 10, 19) + timedelta(days=i) for i in range(7)] + [date(2026, 11, 3)]
    for day in days:
        for o in local.occurrences_on(day):
            recurring = bool(masters[o.event_id].get("recurrence"))
            iid = f"{o.event_id}_{day:%Y%m%d}" if recurring else o.event_id
            item = {"id": iid, "summary": o.summary, "location": o.location, "status": "confirmed",
                    "start": {"dateTime": o.start.isoformat()}, "end": {"dateTime": o.end.isoformat()},
                    "reminders": {"useDefault": False, "overrides": []}}
            if recurring:
                item["recurringEventId"] = o.event_id
            if o.event_id not in drop_props_for:
                item["extendedProperties"] = masters[o.event_id]["extendedProperties"]
            items[iid] = item
    items["allday"] = {"id": "allday", "summary": "Holiday", "start": {"date": "2026-10-22"},
                       "end": {"date": "2026-10-23"}}
    items["gone"] = {"id": "gone", "summary": "Old", "status": "cancelled",
                     "start": {"dateTime": "2026-10-22T09:00:00-03:00"},
                     "end": {"dateTime": "2026-10-22T10:00:00-03:00"}}
    return FakeService(items, masters)


def test_lists_one_halifax_day_as_single_occurrences():
    svc = fake_google()
    occs = GoogleCalendarStore(svc).occurrences_on(date(2026, 10, 22))
    (_, kw), = [c for c in svc.events().calls if c[0] == "list"]
    assert kw["singleEvents"] is True
    assert kw["timeMin"] == "2026-10-22T00:00:00-03:00" and kw["timeMax"] == "2026-10-23T00:00:00-03:00"
    assert [(o.summary, o.start.strftime("%H:%M"), o.category) for o in occs] == [
        ("Pick up Ava", "15:15", "ava_pickup")]          # all-day and cancelled are skipped
    assert occs[0].event_id == "evt_ava_pickup_20261022" and occs[0].series_id == "evt_ava_pickup"


def test_day_window_after_clocks_fall_back():
    svc = fake_google()
    occs = GoogleCalendarStore(svc).occurrences_on(date(2026, 11, 3))
    (_, kw), = [c for c in svc.events().calls if c[0] == "list"]
    assert kw["timeMin"] == "2026-11-03T00:00:00-04:00"
    assert occs[0].start.isoformat() == "2026-11-03T15:15:00-04:00"


def test_category_falls_back_to_the_series():
    svc = fake_google(drop_props_for={"evt_ava_pickup"})
    store = GoogleCalendarStore(svc)
    assert store.occurrences_on(date(2026, 10, 22))[0].category == "ava_pickup"
    store.occurrences_on(date(2026, 10, 20))
    gets = [c for c in svc.events().calls if c[0] == "get"]
    assert gets == [("get", "evt_ava_pickup")]           # looked up once, then cached


def test_t01_end_to_end_moves_only_thursday(profile):
    svc = fake_google()
    store = GoogleCalendarStore(svc)
    case = next(c for c in CASES if c["id"] == "T01")
    msg = Message(case["id"], case["from_phone"], case["sent_at"], case["body"])
    decision = decide(msg, profile, store, lambda m: GOLD["T01"])
    assert decision.action == EDIT and decision.event_id == "evt_ava_pickup_20261022"
    moved = apply(decision, store, profile)

    patches = [c for c in svc.events().calls if c[0] == "patch"]
    assert len(patches) == 1
    _, event_id, body = patches[0]
    assert event_id == "evt_ava_pickup_20261022"          # the occurrence, never the series
    assert body["start"] == {"dateTime": "2026-10-22T14:30:00-03:00", "timeZone": "America/Halifax"}
    assert body["end"]["dateTime"] == "2026-10-22T15:00:00-03:00"
    assert body["summary"] == "Pick up Ava — CHANGED by Michelle, was 3:15"
    assert body["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
    assert "recurrence" not in body
    assert moved.changed and moved.alert_minutes == [30]
    (tue,) = [o for o in store.occurrences_on(date(2026, 10, 20)) if o.category == "ava_pickup"]
    assert tue.start.strftime("%H:%M") == "15:15" and not tue.changed


def test_refuses_if_google_reports_a_series_edit(profile):
    svc = fake_google()
    store = GoogleCalendarStore(svc)
    occ = store.occurrences_on(date(2026, 10, 22))[0]
    svc.events().items[occ.event_id]["recurrence"] = ["RRULE:FREQ=WEEKLY"]   # simulate the wrong target
    with pytest.raises(RuntimeError):
        store.move_occurrence(occ, parse_dt("2026-10-22T14:30:00-03:00"), "x", 30)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_body_tags_events_and_keeps_series():
    seed = _load_script("seed_calendar")
    ava = next(e for e in load("calendar_events.json")["events"] if e["id"] == "evt_ava_pickup")
    body = seed.google_body(ava)
    props = body["extendedProperties"]["private"]
    assert props["heads_up_id"] == "evt_ava_pickup" and props["category"] == "ava_pickup"
    assert all(isinstance(v, str) for v in props.values())
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=TU,TH"]
    assert body["start"]["timeZone"] == "America/Halifax"
    assert body["reminders"] == {"useDefault": False, "overrides": []}
