"""Run Michelle's real 10:48 PM text (T01) against the Gloria TEST Google Calendar.

Shows Thursday Oct 22 before, the decision and its log, then moves ONLY that
Thursday's "Pick up Ava" to 2:30 with a 30-minute alert, and shows it after.

Usage (repo root, venv active, after scripts/seed_calendar.py):
    python scripts/try_google_edit.py             # reads the text with the real LLM (Groq)
    python scripts/try_google_edit.py --offline   # uses the known correct reading instead
    python scripts/try_google_edit.py --reset     # puts Thursday back to 3:15, no alert
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heads_up.config import load_sample  # noqa: E402
from heads_up.google_auth import calendar_service  # noqa: E402
from heads_up.google_calendar import TZ_NAME, GoogleCalendarStore  # noqa: E402
from heads_up.rules import EDIT, Message, apply, decide  # noqa: E402
from heads_up.timeutil import local_dt  # noqa: E402

THURSDAY = date(2026, 10, 22)
T01_READING = {  # what a correct reading of Michelle's text looks like (for --offline)
    "is_plan_change": True, "event_hint": "Ava pickup", "category": "ava_pickup",
    "date_phrase": "tomorrow", "new_time": "14:30", "old_time": "15:15", "is_cancellation": False,
    "scope": "one_occurrence", "change_count": 1, "confidence": "high",
}


def show(store: GoogleCalendarStore, title: str) -> None:
    print(f"\n{title}: {THURSDAY:%a %b %d}")
    for o in store.occurrences_on(THURSDAY):
        alert = f"alert {o.alert_minutes[0]} min before" if o.alert_minutes else "alert: none"
        print(f"  {o.start:%H:%M}-{o.end:%H:%M}  {o.summary}  ({alert})  [{o.category}]")


def ava_on_thursday(store: GoogleCalendarStore):
    matches = [o for o in store.occurrences_on(THURSDAY) if o.category == "ava_pickup"]
    if len(matches) != 1:
        sys.exit(f"Expected one 'Pick up Ava' on {THURSDAY}, found {len(matches)}. "
                 "Run scripts/seed_calendar.py first.")
    return matches[0]


def reset(store: GoogleCalendarStore) -> None:
    occ = ava_on_thursday(store)
    start = local_dt(THURSDAY, datetime.strptime("15:15", "%H:%M").time())
    end = local_dt(THURSDAY, datetime.strptime("15:45", "%H:%M").time())
    store.service.events().patch(calendarId=store.calendar_id, eventId=occ.event_id, body={
        "start": {"dateTime": start.isoformat(), "timeZone": TZ_NAME},
        "end": {"dateTime": end.isoformat(), "timeZone": TZ_NAME},
        "summary": "Pick up Ava",
        "reminders": {"useDefault": False, "overrides": []},
    }).execute()
    show(store, "Reset")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="skip the LLM; use the known reading")
    parser.add_argument("--reset", action="store_true", help="put Thursday's pickup back to 3:15")
    parser.add_argument("--yes", action="store_true", help="don't ask before editing")
    args = parser.parse_args()

    store = GoogleCalendarStore(calendar_service())
    if args.reset:
        return reset(store)

    profile = load_sample("gloria_profile.json")
    case = next(c for c in load_sample("test_messages.json")["cases"] if c["id"] == "T01")
    msg = Message(case["id"], case["from_phone"], case["sent_at"], case["body"])
    if args.offline:
        extract = lambda m: T01_READING  # noqa: E731
    else:
        from heads_up.extractor import LLMExtractor
        extract = LLMExtractor.from_env(profile, env_path=str(ROOT / ".env"))

    show(store, "Before")
    print(f"\nText from Michelle, {msg.sent_at}:\n  \"{msg.body}\"")
    decision = decide(msg, profile, store, extract)
    print("\nDecision log:")
    for line in decision.log:
        print("  " + line)
    if decision.action != EDIT:
        sys.exit(f"\nNo edit ({decision.code}). Nothing changed.")

    if not args.yes and input("\nApply this edit to the TEST calendar? [y/N] ").strip().lower() != "y":
        sys.exit("Cancelled. Nothing changed.")
    apply(decision, store, profile)
    show(store, "After")
    print("\nOnly this Thursday moved. Check Tue Oct 20 and Tue/Thu Oct 27/29 in Google Calendar: still 3:15.")
    print("Undo with: python scripts/try_google_edit.py --reset")


if __name__ == "__main__":
    main()
