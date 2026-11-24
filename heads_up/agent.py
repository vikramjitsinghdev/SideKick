"""HeadsUpAgent: the orchestrator. One object that runs the whole backend.

A frontend (Streamlit, CLI, tests) only talks to this class:

    agent.advance_to(t) / agent.step()   move the simulated clock forward
    agent.receive(...)                   a new text arrives (e.g. typed in the demo)
    agent.press_1() / agent.tap_link()   Gloria confirms
    agent.pause() / agent.resume()       Gloria's consent switch
    agent.snapshot()                     everything the UI needs, as plain JSON

Inside, it wires together the pieces built so far:
    text -> rules.decide (LLM reads, code decides) -> calendar apply
         -> escalation.Ladder (calls, email, family request) -> notifier outbox
Every step is written to one timeline, so the demo can show why things happened.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from .confirm import TokenStore
from .escalation import (FIRST_CALL, NO_ANSWER, RETRY_CALL, PRESSED_1, VOICEMAIL,
                         CALL_OUTCOMES, Ladder)
from .extractor import ExtractorUnavailable
from .notifier import SimulatedNotifier
from .rules import ASK, EDIT, Decision, Message, apply, decide
from .timeutil import parse_dt


# ---- readings without a network -------------------------------------------------

class OfflineExtractor:
    """Looks a text up in saved readings. Unknown text -> raises -> decide() asks Gloria."""
    name = "offline"

    def __init__(self, readings: list[dict]):
        self.by_body = {r["body"]: r["reading"] for r in readings}
        self.last_provider: str | None = None

    def __call__(self, msg: Message) -> dict:
        if msg.body not in self.by_body:
            self.last_provider = None
            raise ExtractorUnavailable("offline mode has no saved reading for this text")
        self.last_provider = self.name
        return dict(self.by_body[msg.body])


# ---- state the UI shows -----------------------------------------------------------

@dataclass
class InboxItem:
    id: str
    from_phone: str
    contact_name: str | None
    received_at: datetime
    body: str
    status: str = "scheduled"          # scheduled | processed
    decision: Decision | None = None
    change_id: str | None = None       # set when the text led to a calendar change


@dataclass
class TimelineEntry:
    at: datetime
    kind: str                          # text | decision | calendar | call | email | family | question | alert | confirm | info
    text: str
    ref: str | None = None


@dataclass
class HeadsUpAgent:
    profile: dict
    calendar: Any                       # CalendarStore or GoogleCalendarStore
    extractor: Callable[[Message], dict]
    clock: datetime
    notifier: SimulatedNotifier = field(default_factory=SimulatedNotifier)
    tokens: TokenStore = field(default_factory=TokenStore)
    # What simulated Gloria does when the phone rings, per call kind.
    call_policy: dict[str, str] = field(default_factory=lambda: {FIRST_CALL: NO_ANSWER, RETRY_CALL: VOICEMAIL})
    inbox: list[InboxItem] = field(default_factory=list)
    ladders: dict[str, Ladder] = field(default_factory=dict)
    timeline: list[TimelineEntry] = field(default_factory=list)

    # ---- setup -----------------------------------------------------------------
    def load_inbox(self, messages: list[dict]) -> None:
        """Schedule texts to arrive at their received_at time. Texts that only
        happened in the 'without Heads-Up' timeline are skipped."""
        for m in messages:
            if m.get("only_in_timeline") == "without_heads_up":
                continue
            self.inbox.append(InboxItem(m["id"], m["from_phone"], m.get("contact_name"),
                                        parse_dt(m["received_at"]), m["body"]))
        self.inbox.sort(key=lambda i: i.received_at)

    def set_call_policy(self, first: str = NO_ANSWER, retry: str = VOICEMAIL) -> None:
        for outcome in (first, retry):
            if outcome not in CALL_OUTCOMES:
                raise ValueError(f"unknown call outcome {outcome!r}")
        self.call_policy = {FIRST_CALL: first, RETRY_CALL: retry}

    def _log(self, at: datetime, kind: str, text: str, ref: str | None = None) -> None:
        self.timeline.append(TimelineEntry(at, kind, text, ref))

    # ---- the clock -----------------------------------------------------------
    def _pending_texts(self) -> list[InboxItem]:
        return [i for i in self.inbox if i.status == "scheduled"]

    def next_event_time(self) -> datetime | None:
        times = [i.received_at for i in self._pending_texts()]
        times += [s.at for lad in self.ladders.values() for s in lad.steps if s.status == "pending"]
        return min(times) if times else None

    def advance_to(self, t: datetime) -> None:
        """Run everything due up to time t, in time order, then set the clock to t."""
        if t < self.clock:
            raise ValueError("the clock only moves forward; rebuild the agent to restart")
        while True:
            nxt = self.next_event_time()
            if nxt is None or nxt > t:
                break
            self.clock = max(self.clock, nxt)
            for item in [i for i in self._pending_texts() if i.received_at <= nxt]:
                self._process(item)
            for ladder in self.ladders.values():
                self._run_ladder(ladder, nxt)
        self.clock = t

    def step(self) -> datetime | None:
        """Jump to the next thing that happens. Returns the new time, or None if nothing is left."""
        nxt = self.next_event_time()
        if nxt is not None:
            self.advance_to(max(nxt, self.clock))
        return nxt

    # ---- texts -----------------------------------------------------------------
    def receive(self, from_phone: str, body: str, contact_name: str | None = None,
                at: datetime | None = None) -> InboxItem:
        """A new text arrives now (or at `at`, if later). Used by the demo's 'send a text' box."""
        at = max(at or self.clock, self.clock)
        item = InboxItem(f"live_{len(self.inbox) + 1:03d}", from_phone, contact_name, at, body)
        self.inbox.append(item)
        self.advance_to(at)
        return item

    def _process(self, item: InboxItem) -> None:
        item.status = "processed"
        who = item.contact_name or item.from_phone
        self._log(item.received_at, "text", f"Text from {who}: \"{item.body}\"", item.id)
        msg = Message(item.id, item.from_phone, item.received_at.isoformat(), item.body)
        decision = decide(msg, self.profile, self.calendar, self.extractor)
        item.decision = decision
        self._log(item.received_at, "decision", f"{decision.action} [{decision.code}]: {decision.reason}", item.id)

        if decision.action == EDIT:
            moved = apply(decision, self.calendar, self.profile)
            change_id = f"chg_{item.id}"
            item.change_id = change_id
            self._log(item.received_at, "calendar",
                      f"Moved {moved.summary} to {moved.start:%a %b %d %H:%M} with a "
                      f"{moved.alert_minutes[0]}-minute alert (this occurrence only)", change_id)
            ladder = Ladder.start(change_id, decision, self.profile, tokens=self.tokens, notifier=self.notifier)
            self.ladders[change_id] = ladder
            self._run_ladder(ladder, item.received_at)
        elif decision.action == ASK:
            body = (f"{decision.sender or who} sent a text that might change your plans, but I wasn't sure, "
                    f"so I didn't change your calendar: \"{item.body}\" ({decision.reason}). "
                    f"You may want to call {decision.sender or 'them'}.")
            self.notifier.question_to_gloria(item.received_at, self.profile["user"]["phone"], body)
            self._log(item.received_at, "question", "Told Gloria about the text instead of editing", item.id)

    # ---- ladders -----------------------------------------------------------------
    def _run_ladder(self, ladder: Ladder, now: datetime) -> None:
        seen = len(ladder.log)
        out_before = len(self.notifier.outbox)
        ladder.advance(now, answer=lambda step: self.call_policy.get(step.kind, NO_ANSWER))
        for at, text in ladder.log[seen:]:
            self._log(at, self._kind_for(text), text, ladder.change_id)
        for item in self.notifier.outbox[out_before:]:
            if item.channel == "family_message" and "confirmed" in item.body and "hasn't" not in item.body:
                self._log(item.at, "family", f"Told {ladder.decision.sender}: \"{item.body}\"", ladder.change_id)

    @staticmethod
    def _kind_for(text: str) -> str:
        t = text.lower()
        if t.startswith("call") or t.startswith("voicemail"):
            return "call"
        if t.startswith("large-print"):
            return "email"
        if "asked" in t and "call gloria" in t:
            return "family"
        if "lock-screen" in t:
            return "alert"
        if "confirmed" in t or t.startswith("cancelled"):
            return "confirm"
        return "info"

    def _ladder_for(self, change_id: str | None) -> Ladder:
        if change_id:
            return self.ladders[change_id]
        active = [lad for lad in self.ladders.values() if lad.status not in ("confirmed", "ended_unconfirmed")]
        if len(active) != 1:
            raise ValueError(f"{len(active)} active changes; say which one")
        return active[0]

    # ---- Gloria's actions ------------------------------------------------------------
    def ringing_call(self) -> tuple[str, Any] | None:
        """The call happening right now (same minute as the clock), if any."""
        for change_id, ladder in self.ladders.items():
            for s in ladder.steps:
                if s.kind in (FIRST_CALL, RETRY_CALL) and s.status == "done" and s.done_at == self.clock:
                    return change_id, s
        return None

    def press_1(self, change_id: str | None = None) -> bool:
        """Gloria presses 1 on the call that is ringing now."""
        ringing = self.ringing_call()
        if ringing is None or (change_id and ringing[0] != change_id):
            raise ValueError("no call to Gloria is ringing at this moment")
        cid, step = ringing
        if self.ladders[cid].status == "confirmed":
            return False
        step.outcome = PRESSED_1
        before = len(self.ladders[cid].log)
        self.ladders[cid].confirm(self.clock, via="press_1_on_call")
        for at, text in self.ladders[cid].log[before:]:
            self._log(at, self._kind_for(text), text, cid)
        return True

    def tap_link(self, token: str) -> str:
        """Gloria taps 'Got it' in the email. Returns confirmed / unknown / expired / already_used."""
        for cid, ladder in self.ladders.items():
            if ladder.token == token:
                before = len(ladder.log)
                result = ladder.tap_link(token, self.clock)
                for at, text in ladder.log[before:]:
                    self._log(at, self._kind_for(text), text, cid)
                return result
        return self.tokens.redeem(token, self.clock).reason

    def pause(self) -> None:
        self.profile["consent"]["agent_paused"] = True
        self._log(self.clock, "info", "Gloria paused Heads-Up: new texts are logged only")

    def resume(self) -> None:
        self.profile["consent"]["agent_paused"] = False
        self._log(self.clock, "info", "Gloria turned Heads-Up back on")

    # ---- what the UI reads -----------------------------------------------------------
    def snapshot(self, days: list[date] | None = None) -> dict:
        """Everything a frontend needs, as JSON-safe dicts."""
        if days is None:
            days = sorted({parse_dt(l.decision.new_start).date() for l in self.ladders.values()}
                          | {self.clock.date()})
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        ringing = self.ringing_call()
        return {
            "clock": self.clock.isoformat(),
            "next_event_at": iso(self.next_event_time()),
            "consent": {k: v for k, v in self.profile["consent"].items()},
            "call_policy": dict(self.call_policy),
            "ringing_call": {"change_id": ringing[0], "kind": ringing[1].kind} if ringing else None,
            "inbox": [{
                "id": i.id, "from_phone": i.from_phone, "contact_name": i.contact_name,
                "received_at": iso(i.received_at), "body": i.body, "status": i.status,
                "change_id": i.change_id,
                "decision": None if i.decision is None else {
                    "action": i.decision.action, "code": i.decision.code,
                    "reason": i.decision.reason, "log": list(i.decision.log)},
            } for i in self.inbox if i.received_at <= self.clock],
            "calendar": {d.isoformat(): [{
                "event_id": o.event_id, "summary": o.summary, "category": o.category,
                "start": iso(o.start), "end": iso(o.end), "alert_minutes": o.alert_minutes,
                "location": o.location, "changed": o.changed,
            } for o in self.calendar.occurrences_on(d)] for d in days},
            "changes": [{
                "change_id": cid, "status": lad.status, "confirmed_at": iso(lad.confirmed_at),
                "confirmed_via": lad.confirmed_via, "link": self.tokens.link(lad.token),
                "steps": [{"at": iso(s.at), "kind": s.kind, "status": s.status, "outcome": s.outcome}
                          for s in lad.steps],
            } for cid, lad in self.ladders.items()],
            "outbox": [{"at": iso(o.at), "channel": o.channel, "to": o.to, "body": o.body, "meta": o.meta}
                       for o in self.notifier.outbox],
            "timeline": [{"at": iso(e.at), "kind": e.kind, "text": e.text, "ref": e.ref} for e in self.timeline],
        }

    def snapshot_json(self, **kwargs) -> str:
        return json.dumps(self.snapshot(**kwargs), indent=2, ensure_ascii=False)
