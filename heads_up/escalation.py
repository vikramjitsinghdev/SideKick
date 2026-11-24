"""The call-first contact ladder for one calendar change.

plan_ladder() works out WHEN each step happens. Ladder runs the steps on a
simulated clock and stops as soon as Gloria confirms (press 1 on a call, or
the "Got it" link). Voicemail never counts as confirmed.

Timing rules (all from agent_rules.contact_plan in gloria_profile.json):
- First call right away, unless it's quiet hours (9 PM-8 AM); then 8 AM.
  If waiting until 8 AM would leave less than 2 h before the event, call now.
- Large-print record email goes out with the first call.
- Retry call 2 h after the first, only if that's before the family request.
- Family request 60 min before the event (with the first call if the event
  is less than 60 min away). The family only learns whether this one change
  was confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable

from .confirm import TokenStore
from .notifier import SimulatedNotifier
from .rules import EDIT, Decision
from .timeutil import local_dt, parse_dt, parse_hhmm, short_time

# Step kinds, in the order they run when they share a time.
FIRST_CALL, RECORD_EMAIL, RETRY_CALL = "first_call", "record_email", "retry_call"
FAMILY_REQUEST, CALENDAR_ALERT, EVENT_START = "family_request", "calendar_alert", "event_start"
ORDER = [FIRST_CALL, RECORD_EMAIL, RETRY_CALL, FAMILY_REQUEST, CALENDAR_ALERT, EVENT_START]
CANCEL_ON_CONFIRM = {RETRY_CALL, FAMILY_REQUEST}

# Call outcomes. Only PRESSED_1 confirms.
PRESSED_1, NO_ANSWER, VOICEMAIL = "answered_pressed_1", "no_answer", "voicemail"
CALL_OUTCOMES = {PRESSED_1, NO_ANSWER, VOICEMAIL, "answered_no_keypress"}


@dataclass
class Step:
    at: datetime
    kind: str
    status: str = "pending"        # pending | done | cancelled
    outcome: str | None = None     # call outcome, or what happened
    done_at: datetime | None = None

    def sort_key(self):
        return (self.at, ORDER.index(self.kind))


def in_quiet_hours(t: datetime, quiet: dict) -> bool:
    start, end = parse_hhmm(quiet["start"]), parse_hhmm(quiet["end"])
    return t.time() >= start or t.time() < end


def next_end_of_quiet(t: datetime, quiet: dict) -> datetime:
    end = parse_hhmm(quiet["end"])
    day = t.date() if t.time() < end else t.date() + timedelta(days=1)
    return local_dt(day, end)


def plan_ladder(decision: Decision, profile: dict) -> list[Step]:
    if decision.action != EDIT:
        raise ValueError("Only edit decisions get a contact ladder")
    plan = profile["agent_rules"]["contact_plan"]
    alert_minutes = profile["agent_rules"]["alert_minutes_before"]
    sent = parse_dt(decision.sent_at)
    event = parse_dt(decision.new_start)
    urgent = timedelta(minutes=plan["call_immediately_if_event_within_minutes"])

    first = sent
    if in_quiet_hours(sent, plan["quiet_hours"]) and event - sent > urgent:
        morning = next_end_of_quiet(sent, plan["quiet_hours"])
        first = morning if event - morning >= urgent else sent

    family = max(event - timedelta(minutes=plan["family_request_minutes_before_event"]), first)
    retry = first + timedelta(minutes=plan["retry_call_after_minutes"])
    if plan.get("retry_only_if_before_family_request", True) and retry >= family:
        retry = None

    steps = [Step(first, FIRST_CALL), Step(first, RECORD_EMAIL)]
    if retry:
        steps.append(Step(retry, RETRY_CALL))
    steps += [
        Step(family, FAMILY_REQUEST),
        Step(event - timedelta(minutes=alert_minutes), CALENDAR_ALERT),
        Step(event, EVENT_START),
    ]
    return sorted(steps, key=Step.sort_key)


def lower_first(text: str) -> str:
    """'Pick up Ava' -> 'pick up Ava' (keeps names capitalised)."""
    return text[:1].lower() + text[1:]


def day_word(event: datetime, now: datetime) -> str:
    delta = (event.date() - now.date()).days
    return {0: "today", 1: "tomorrow"}.get(delta, event.strftime("on %A"))


@dataclass
class Ladder:
    """One change's ladder. `log` is the human-readable timeline for the demo."""
    change_id: str
    decision: Decision
    profile: dict
    steps: list[Step]
    tokens: TokenStore
    notifier: SimulatedNotifier
    token: str = ""
    status: str = "waiting"        # waiting | confirmed | family_asked | ended_unconfirmed
    confirmed_at: datetime | None = None
    confirmed_via: str | None = None
    log: list[tuple[datetime, str]] = field(default_factory=list)

    @classmethod
    def start(cls, change_id: str, decision: Decision, profile: dict,
              tokens: TokenStore | None = None, notifier: SimulatedNotifier | None = None) -> "Ladder":
        tokens = tokens or TokenStore()
        ladder = cls(change_id, decision, profile, plan_ladder(decision, profile),
                     tokens, notifier or SimulatedNotifier())
        ladder.token = tokens.make(change_id, expires_at=parse_dt(decision.new_start))
        first = ladder.steps[0]
        if first.at > parse_dt(decision.sent_at):
            ladder._note(parse_dt(decision.sent_at),
                         f"Quiet hours: first call scheduled for {first.at:%a %H:%M}")
        return ladder

    # ---- wording -------------------------------------------------------------
    @property
    def sender(self) -> dict:
        return next(c for c in self.profile["trusted_contacts"] if c["name"] == self.decision.sender)

    @property
    def gloria(self) -> dict:
        return self.profile["user"]

    def _change_sentence(self, now: datetime) -> str:
        d = self.decision
        new, old = parse_dt(d.new_start), parse_dt(d.old_start)
        where = f", at {d.location}" if d.location else ""
        return (f"Please {lower_first(d.event_title)} at {short_time(new.time())} {day_word(new, now)} "
                f"instead of {short_time(old.time())}{where}.")

    def call_script(self, now: datetime) -> str:
        alert = parse_dt(self.decision.alert_at)
        return self.profile["agent_rules"]["contact_plan"]["call_script"].format(
            sender=self.decision.sender, change_sentence=self._change_sentence(now),
            alert_time=short_time(alert.time()))

    def email_body(self, now: datetime) -> str:
        d = self.decision
        new, old = parse_dt(d.new_start), parse_dt(d.old_start)
        greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Hello"
        return (f"{greeting} Gloria.\n\n{d.sender} sent a change:\n\n"
                f"{d.event_title.upper()} AT {short_time(new.time())} {day_word(new, now).upper()} "
                f"(not {short_time(old.time())})\n{d.location or ''}\n\n"
                f"Your calendar is updated, and your phone will remind you at "
                f"{short_time(parse_dt(d.alert_at).time())}.\n\n"
                "We also called you about this. If you already pressed 1 on the call, you're all set. "
                f"Otherwise, please tap the button so {d.sender} knows you got it.")

    def _who(self) -> str:
        return "Your mom" if self.sender.get("relationship") in {"daughter", "son"} else "Gloria"

    # ---- running -------------------------------------------------------------
    def _note(self, at: datetime, text: str) -> None:
        self.log.append((at, text))

    def due(self, now: datetime) -> list[Step]:
        return [s for s in self.steps if s.status == "pending" and s.at <= now]

    def next_step(self) -> Step | None:
        return next((s for s in self.steps if s.status == "pending"), None)

    def advance(self, now: datetime, answer: Callable[[Step], str] = lambda step: NO_ANSWER) -> list[Step]:
        """Run every step due by `now`, in order. `answer` simulates Gloria picking up."""
        ran = []
        for step in sorted(self.due(now), key=Step.sort_key):
            if step.status != "pending":  # cancelled by a confirmation earlier in this loop
                continue
            self._run(step, answer)
            ran.append(step)
        return ran

    def _run(self, step: Step, answer: Callable[[Step], str]) -> None:
        d, at = self.decision, step.at
        step.status, step.done_at = "done", at
        if step.kind in (FIRST_CALL, RETRY_CALL):
            attempt = 1 if step.kind == FIRST_CALL else 2
            self.notifier.call(at, self.gloria["phone"], self.call_script(at), attempt)
            step.outcome = answer(step)
            if step.outcome not in CALL_OUTCOMES:
                raise ValueError(f"unknown call outcome {step.outcome!r}")
            self._note(at, f"Call {attempt} to Gloria: {step.outcome.replace('_', ' ')}")
            if step.outcome == PRESSED_1:
                self.confirm(at, via="press_1_on_call")
            elif step.outcome == VOICEMAIL:
                self._note(at, "Voicemail left; does not count as confirmed")
        elif step.kind == RECORD_EMAIL:
            new = parse_dt(d.new_start)
            subject = f"{d.event_title} changed to {short_time(new.time())} {day_word(new, at)}"
            self.notifier.email(at, self.gloria["email"], subject, self.email_body(at),
                                self.tokens.link(self.token))
            self._note(at, "Large-print record email sent with a 'Got it' link")
        elif step.kind == FAMILY_REQUEST:
            new = parse_dt(d.new_start)
            body = (f"Hi {d.sender}, this is Heads-Up. {self._who()} hasn't confirmed the change to "
                    f"{lower_first(d.event_title)} at {short_time(new.time())} {day_word(new, at)}. "
                    "Please give her a call.")
            self.notifier.family_message(at, self.sender["phone"], body)
            self.status = "family_asked"
            self._note(at, f"Not confirmed: asked {d.sender} to call Gloria")
        elif step.kind == CALENDAR_ALERT:
            self._note(at, f"Lock-screen alert: {d.event_title} — {d.summary_label}")
        elif step.kind == EVENT_START:
            if self.status != "confirmed":
                self.status = "ended_unconfirmed"
            self._note(at, "Event starts; the 'Got it' link expires")

    def confirm(self, at: datetime, via: str) -> bool:
        """Gloria confirmed. Cancels the retry call and family request. Idempotent."""
        if self.status == "confirmed":
            return False
        self.status, self.confirmed_at, self.confirmed_via = "confirmed", at, via
        self._note(at, f"Gloria confirmed ({via.replace('_', ' ')})")
        cancelled = []
        for step in self.steps:
            if step.status == "pending" and step.kind in CANCEL_ON_CONFIRM:
                step.status = "cancelled"
                cancelled.append(step.kind)
        if cancelled:
            self._note(at, "Cancelled: " + ", ".join(k.replace("_", " ") for k in cancelled))
        new = parse_dt(self.decision.new_start)
        title, when = self.decision.event_title, f"{short_time(new.time())}"
        if title.lower().startswith("pick up "):
            what = f"the {when} pickup for {title[len('pick up '):]} {day_word(new, at)}"
        else:
            what = f"{lower_first(title)} at {when} {day_word(new, at)}"
        # The family only learns that this one change was confirmed.
        self.notifier.family_message(at, self.sender["phone"], f"{self._who()} confirmed {what}.")
        return True

    def tap_link(self, token: str, now: datetime) -> str:
        """Gloria tapped 'Got it' in the email. Returns the redemption reason."""
        result = self.tokens.redeem(token, now)
        if result.ok and result.change_id == self.change_id:
            self.confirm(now, via="got_it_link")
        return result.reason
