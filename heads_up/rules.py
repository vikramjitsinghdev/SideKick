"""The decision core. Plain code decides; the LLM only reads.

``decide`` is pure: it never changes the calendar. It returns a Decision that
says what to do and why, plus a step-by-step log for the demo.

Order matters. The consent and sender checks run BEFORE the text is sent to
the LLM, so a stranger's text (or an injection attempt) never reaches it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable

from . import dates
from .calendar_store import CalendarStore, Occurrence
from .extraction import Extraction, ExtractionError, validate
from .timeutil import local_dt, parse_dt, parse_hhmm, short_time

EDIT, ASK, NONE = "edit_one_occurrence", "ask_gloria", "no_action"
# A pickup or appointment outside these hours is far more likely a misread (2:30 AM vs PM).
SANE_HOURS = (time(7, 0), time(21, 0))


@dataclass
class Message:
    id: str
    from_phone: str
    sent_at: str
    body: str


@dataclass
class Decision:
    action: str
    code: str      # machine-readable reason, e.g. "unclear_date"; tests assert on it
    reason: str    # plain-English reason, shown in the decision log
    sender: str | None = None
    event_id: str | None = None
    occurrence_date: str | None = None
    old_start: str | None = None
    new_start: str | None = None
    new_end: str | None = None
    alert_at: str | None = None
    summary_label: str | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


Extractor = Callable[[Message], dict]


def decide(msg: Message, profile: dict, calendar: CalendarStore, extract: Extractor) -> Decision:
    log: list[str] = []

    def stop(action: str, code: str, reason: str, **extra) -> Decision:
        log.append(f"-> {action} [{code}]: {reason}")
        return Decision(action=action, code=code, reason=reason, log=log, **extra)

    # 1. Consent: nothing happens unless Gloria has opted in and not paused.
    consent = profile["consent"]
    if not consent.get("opted_in") or consent.get("agent_paused"):
        return stop(NONE, "paused", "Agent is paused or Gloria hasn't opted in; message logged only")
    log.append("consent ok")

    # 2. Sender: only trusted family contacts. Unknown texts never reach the LLM.
    sender = next((c for c in profile["trusted_contacts"] if c["phone"] == msg.from_phone), None)
    if sender is None:
        return stop(NONE, "unknown_sender", "Sender is not a trusted contact; the agent never acts on unknown senders")
    log.append(f"trusted sender: {sender['name']}")

    # 3. Ask the LLM to read the text, then check its JSON with code.
    try:
        ex: Extraction = validate(extract(msg))
    except ExtractionError as err:
        return stop(ASK, "unreadable", f"Couldn't read the text reliably ({err}); asking Gloria", sender=sender["name"])
    except Exception as err:  # network / API failure: fail safe, never guess
        return stop(ASK, "llm_error", f"Reading the text failed ({type(err).__name__}); asking Gloria", sender=sender["name"])
    log.append(f"extraction: {ex}")

    base = {"sender": sender["name"]}

    if not ex.is_plan_change:
        return stop(NONE, "not_a_change", "Not a change to an upcoming plan", **base)
    if ex.scope == "all_occurrences":
        return stop(NONE, "series_request", "Asks to change every repeat of an event; series edits are never allowed", **base)
    if ex.change_count > 1:
        return stop(ASK, "multiple_changes", "More than one change in a single text; asking Gloria", **base)
    if ex.is_cancellation:
        return stop(ASK, "cancellation", "A cancellation would need a delete; telling Gloria instead of editing", **base)
    if ex.category is None:
        return stop(ASK, "unknown_event", "Can't tell which event the text is about", **base)
    if ex.category not in consent["changeable_event_categories"]:
        return stop(ASK, "category_not_allowed", f"Gloria hasn't allowed changes to '{ex.category}'", **base)
    if ex.category not in sender.get("can_change", []):
        return stop(ASK, "sender_not_allowed", f"{sender['name']} isn't set up to change '{ex.category}'", **base)
    log.append(f"category '{ex.category}' is changeable by {sender['name']}")

    # 4. Date: code resolves the sender's words, relative to when the text was sent.
    sent = parse_dt(msg.sent_at)
    try:
        day = dates.resolve(ex.date_phrase, sent)
    except dates.UnclearDate as err:
        return stop(ASK, "unclear_date", f"Date is unclear: {err}", **base)
    if day < sent.date():
        return stop(NONE, "past_day", "Refers to a past day; nothing to change", **base)
    log.append(f"'{ex.date_phrase}' sent {sent:%a %b %d %H:%M} -> {day:%a %b %d}")

    # 5. Time: must be specific, confident and plausible.
    if ex.new_time is None:
        return stop(ASK, "vague_time", "New time is vague", **base)
    if ex.confidence != "high":
        return stop(ASK, "low_confidence", "The reading of the text is low-confidence", **base)
    new_time = parse_hhmm(ex.new_time)
    if not SANE_HOURS[0] <= new_time <= SANE_HOURS[1]:
        return stop(ASK, "implausible_time", f"New time {ex.new_time} is outside 7 AM-9 PM; likely a misread", **base)

    # 6. Exactly one matching occurrence, or no edit.
    matches = [o for o in calendar.occurrences_on(day) if o.category == ex.category]
    if len(matches) != 1:
        return stop(ASK, "match_count", f"{len(matches)} '{ex.category}' events on {day:%a %b %d}; need exactly one", **base)
    occ: Occurrence = matches[0]
    if ex.old_time and parse_hhmm(ex.old_time) != occ.start.time():
        return stop(ASK, "old_time_mismatch", f"Text says it was {ex.old_time}, calendar says {occ.start:%H:%M}", **base)
    log.append(f"one match: {occ.event_id} at {occ.start:%H:%M}")

    new_start = local_dt(day, new_time)
    if new_start <= sent:
        return stop(ASK, "time_passed", "The new time has already passed", **base)
    if new_start == occ.start:
        return stop(NONE, "already_set", "Calendar already has that time", **base)

    alert_minutes = profile["agent_rules"]["alert_minutes_before"]
    return stop(
        EDIT,
        "edit",
        "Trusted sender, clear date and time, exactly one matching occurrence",
        **base,
        event_id=occ.event_id,
        occurrence_date=day.isoformat(),
        old_start=occ.start.isoformat(),
        new_start=new_start.isoformat(),
        new_end=(new_start + (occ.end - occ.start)).isoformat(),
        alert_at=(new_start - timedelta(minutes=alert_minutes)).isoformat(),
        summary_label=f"CHANGED by {sender['name']}, was {short_time(occ.start.time())}",
    )


def apply(decision: Decision, calendar: CalendarStore, profile: dict) -> Occurrence | None:
    """Carry out an edit decision on the calendar. Only ever one occurrence."""
    if decision.action != EDIT:
        return None
    day = parse_dt(decision.new_start).date()
    occ = next(o for o in calendar.occurrences_on(day) if o.event_id == decision.event_id)
    base_summary = occ.summary.split(" (CHANGED")[0]
    return calendar.move_occurrence(
        occ,
        parse_dt(decision.new_start),
        summary=f"{base_summary} ({decision.summary_label})",
        alert_minutes=profile["agent_rules"]["alert_minutes_before"],
    )
