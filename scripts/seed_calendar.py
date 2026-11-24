"""Load sample_data/calendar_events.json onto the Gloria TEST Google Calendar.

Safe to run more than once. For each sample event it:
  1. updates the event it created before (found by its heads_up_id tag), or
  2. takes over the matching recurring event that setup_google.py created
     (same title, no tag) and brings it in line with the sample data, or
  3. creates it.
Nothing is ever deleted.

Usage (repo root, venv active, credentials.json present):
    python scripts/seed_calendar.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heads_up.config import load_sample  # noqa: E402
from heads_up.google_auth import calendar_service  # noqa: E402

TZ = "America/Halifax"


def google_body(ev: dict) -> dict:
    props = {k: str(v) for k, v in ev.get("extendedProperties", {}).get("private", {}).items()}
    props["heads_up_id"] = ev["id"]
    body = {
        "summary": ev["summary"],
        "location": ev.get("location"),
        "start": {"dateTime": ev["start"]["dateTime"], "timeZone": TZ},
        "end": {"dateTime": ev["end"]["dateTime"], "timeZone": TZ},
        "reminders": ev.get("reminders", {"useDefault": False, "overrides": []}),
        "extendedProperties": {"private": props},
    }
    if ev.get("recurrence"):
        body["recurrence"] = ev["recurrence"]
    return body


def find_tagged(service, heads_up_id: str):
    items = service.events().list(
        calendarId="primary", privateExtendedProperty=f"heads_up_id={heads_up_id}",
        singleEvents=False, maxResults=10).execute().get("items", [])
    return items[0] if items else None


def find_untagged_original(service, summary: str, recurring: bool):
    items = service.events().list(calendarId="primary", q=summary, singleEvents=False,
                                  maxResults=50).execute().get("items", [])
    for item in items:
        tagged = "heads_up_id" in item.get("extendedProperties", {}).get("private", {})
        if item.get("summary") == summary and not tagged and bool(item.get("recurrence")) == recurring:
            return item
    return None


def main() -> None:
    service = calendar_service()
    for ev in load_sample("calendar_events.json")["events"]:
        body = google_body(ev)
        existing = find_tagged(service, ev["id"])
        if existing:
            service.events().patch(calendarId="primary", eventId=existing["id"], body=body).execute()
            print(f"Updated   {ev['summary']}")
            continue
        original = find_untagged_original(service, ev["summary"], bool(ev.get("recurrence")))
        if original:
            service.events().patch(calendarId="primary", eventId=original["id"], body=body).execute()
            print(f"Adopted   {ev['summary']} (from setup_google.py, now matches sample data)")
            continue
        service.events().insert(calendarId="primary", body=body).execute()
        print(f"Created   {ev['summary']}")
    print("\nDone. Check the week of Oct 19-25, 2026 in the test account's Google Calendar.")


if __name__ == "__main__":
    main()
