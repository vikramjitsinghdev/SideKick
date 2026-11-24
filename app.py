"""Heads-Up entry point: builds the agent and runs the backend.

The frontend (ui.py, coming next) only needs:

    from app import build_agent
    agent = build_agent(scenario="no_answer")   # or "press_1"
    agent.step()                                # next thing that happens
    state = agent.snapshot()                    # everything to draw

From the terminal you can replay Thursday without any UI:

    python app.py                    # offline: saved readings + in-memory calendar
    python app.py --press-1          # Gloria answers the 8 AM call and presses 1
    python app.py --live             # read texts with the real LLM (Groq)
    python app.py --google           # use the TEST Google Calendar (run try_google_edit.py --reset first)
    python app.py --json out.json    # also save the final snapshot for the frontend
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from heads_up.agent import HeadsUpAgent, OfflineExtractor  # noqa: E402
from heads_up.calendar_store import CalendarStore  # noqa: E402
from heads_up.config import load_sample  # noqa: E402
from heads_up.escalation import NO_ANSWER, PRESSED_1, VOICEMAIL  # noqa: E402
from heads_up.timeutil import parse_dt  # noqa: E402

SCENARIOS = {
    "no_answer": {"first": NO_ANSWER, "retry": VOICEMAIL},  # what really happens to Gloria's phone
    "press_1": {"first": PRESSED_1, "retry": NO_ANSWER},     # she answers the 8 AM call
}


def build_agent(scenario: str = "no_answer", live: bool = False, google: bool = False,
                start: str | None = None) -> HeadsUpAgent:
    """Fresh agent with Gloria's profile, calendar and replay inbox, clock at the replay start."""
    profile = load_sample("gloria_profile.json")
    inbox = load_sample("sms_inbox_replay.json")

    if google:
        from heads_up.google_auth import calendar_service
        from heads_up.google_calendar import GoogleCalendarStore
        calendar = GoogleCalendarStore(calendar_service())
    else:
        calendar = CalendarStore.from_sample(load_sample("calendar_events.json"))

    if live:
        from heads_up.extractor import LLMExtractor
        extractor = LLMExtractor.from_env(profile, env_path=str(ROOT / ".env"))
    else:
        extractor = OfflineExtractor(load_sample("offline_readings.json")["readings"])

    agent = HeadsUpAgent(profile, calendar, extractor, clock=parse_dt(profile["consent"]["opted_in_at"]))
    agent.set_call_policy(**SCENARIOS[scenario])
    agent.load_inbox(inbox["messages"])
    # Texts from before the replay window (Mon-Wed afternoon) are handled straight away.
    agent.advance_to(parse_dt(start or inbox["_meta"]["replay_window"]["start"]))
    return agent


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Replay Oct 21-22 through the Heads-Up backend")
    parser.add_argument("--press-1", action="store_true", help="Gloria answers the 8 AM call and presses 1")
    parser.add_argument("--live", action="store_true", help="read texts with the real LLM")
    parser.add_argument("--google", action="store_true", help="use the TEST Google Calendar")
    parser.add_argument("--json", metavar="FILE", help="save the final snapshot as JSON")
    args = parser.parse_args()

    agent = build_agent("press_1" if args.press_1 else "no_answer", live=args.live, google=args.google)
    end = parse_dt(load_sample("sms_inbox_replay.json")["_meta"]["replay_window"]["end"])
    agent.advance_to(end)

    print(f"\nHeads-Up replay ({'Gloria presses 1' if args.press_1 else 'Gloria never answers'})\n")
    last_day = None
    for e in agent.timeline:
        day = e.at.strftime("%a %b %d")
        if day != last_day:
            print(f"\n{day}")
            last_day = day
        print(f"  {e.at:%H:%M}  {e.kind:<9} {e.text}")

    thursday = parse_dt("2026-10-22T12:00:00-03:00").date()
    print("\nThursday's calendar now:")
    for o in agent.calendar.occurrences_on(thursday):
        alert = f"alert {o.alert_minutes[0]} min" if o.alert_minutes else "no alert"
        print(f"  {o.start:%H:%M}-{o.end:%H:%M}  {o.summary} ({alert})")
    for cid, lad in agent.ladders.items():
        print(f"\n{cid}: {lad.status}" + (f" via {lad.confirmed_via}" if lad.confirmed_via else ""))

    if args.json:
        Path(args.json).write_text(agent.snapshot_json(), encoding="utf-8")
        print(f"\nSnapshot saved to {args.json}")


if __name__ == "__main__":
    run_cli()
