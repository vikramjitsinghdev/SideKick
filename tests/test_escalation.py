"""Call-first ladder and "Got it" links, checked against the sample data.

- T01 / T13 timings come from expected.*_at in test_messages.json.
- The Thursday run is compared with replay_timeline.json, both branches:
  Gloria doesn't answer (with_heads_up) and Gloria presses 1 (alt_branch_confirmed).
"""
from datetime import datetime, timedelta

import pytest

from heads_up.confirm import TokenStore
from heads_up.escalation import (
    CALENDAR_ALERT, EVENT_START, FAMILY_REQUEST, FIRST_CALL, NO_ANSWER, PRESSED_1,
    RECORD_EMAIL, RETRY_CALL, VOICEMAIL, Ladder, plan_ladder,
)
from heads_up.rules import EDIT, Decision, Message, decide
from heads_up.timeutil import parse_dt
from conftest import load
from test_rules import CASES, GOLD

REPLAY = load("replay_timeline.json")


def case_decision(case_id, profile, calendar):
    case = next(c for c in CASES if c["id"] == case_id)
    msg = Message(case["id"], case["from_phone"], case["sent_at"], case["body"])
    decision = decide(msg, profile, calendar, lambda m: GOLD[case_id])
    assert decision.action == EDIT
    return case, decision


def times(steps, kind):
    found = [s.at.isoformat() for s in steps if s.kind == kind]
    return found[0] if found else None


@pytest.mark.parametrize("case_id", ["T01", "T13"])
def test_ladder_timings_match_test_messages(case_id, profile, calendar):
    case, decision = case_decision(case_id, profile, calendar)
    steps = plan_ladder(decision, profile)
    e = case["expected"]
    assert times(steps, FIRST_CALL) == e["first_call_at"]
    assert times(steps, RECORD_EMAIL) == e["record_email_at"]
    assert times(steps, RETRY_CALL) == e["retry_call_at"]
    assert times(steps, FAMILY_REQUEST) == e["family_request_at"]
    assert times(steps, CALENDAR_ALERT) == e["alert_at"]
    assert times(steps, EVENT_START) == e["new_start"]


# ---- Thursday replay ---------------------------------------------------------

def run_thursday(profile, calendar, answers):
    _, decision = case_decision("T01", profile, calendar)
    ladder = Ladder.start("chg_T01", decision, profile)
    ladder.advance(parse_dt("2026-10-22T23:59:00-03:00"), answer=lambda step: answers[step.kind])
    return ladder


def test_replay_gloria_never_answers(profile, calendar):
    ladder = run_thursday(profile, calendar, {FIRST_CALL: NO_ANSWER, RETRY_CALL: VOICEMAIL})
    want = {e["type"]: e for e in REPLAY["with_heads_up"]}
    calls = [e for e in REPLAY["with_heads_up"] if e["type"] == "call_to_gloria"]
    outbox = ladder.notifier.outbox

    # Calls: 8:00 (no answer) then 10:00 (voicemail), with the replay's exact script.
    got_calls = [o for o in outbox if o.channel == "call"]
    assert [c.at.isoformat() for c in got_calls] == [c["at"] for c in calls]
    assert got_calls[0].body == calls[0]["script"]
    assert [s.outcome for s in ladder.steps if s.kind in (FIRST_CALL, RETRY_CALL)] == [NO_ANSWER, VOICEMAIL]

    # Record email at 8:00 with the link; family request at 1:30 with the replay's exact words.
    (email,) = [o for o in outbox if o.channel == "email"]
    assert email.at.isoformat() == "2026-10-22T08:00:00-03:00"
    assert "PICK UP AVA AT 2:30 TODAY (not 3:15)" in email.body
    assert email.body.startswith("Good morning Gloria.")
    assert email.meta["link"].endswith(ladder.token)
    (family,) = [o for o in outbox if o.channel == "family_message"]
    assert family.at.isoformat()[:16] == want["family_request"]["at"][:16]   # 13:30 (replay logs :01)
    assert family.body == want["family_request"]["message"]
    assert family.to == "+19025550123"

    assert ladder.status == "ended_unconfirmed"
    assert ladder.confirmed_at is None


def test_replay_gloria_presses_1(profile, calendar):
    ladder = run_thursday(profile, calendar, {FIRST_CALL: PRESSED_1, RETRY_CALL: NO_ANSWER})
    alt = {e["type"]: e for e in REPLAY["alt_branch_confirmed"]["events"]}
    outbox = ladder.notifier.outbox

    assert ladder.status == "confirmed" and ladder.confirmed_via == "press_1_on_call"
    assert len([o for o in outbox if o.channel == "call"]) == 1            # no retry
    (status,) = [o for o in outbox if o.channel == "family_message"]       # no family request
    assert status.body == alt["status_to_sender"]["body"]
    cancelled = {s.kind for s in ladder.steps if s.status == "cancelled"}
    assert cancelled == {RETRY_CALL, FAMILY_REQUEST}


def test_voicemail_never_confirms(profile, calendar):
    ladder = run_thursday(profile, calendar, {FIRST_CALL: VOICEMAIL, RETRY_CALL: VOICEMAIL})
    assert ladder.status == "ended_unconfirmed"
    assert any(o.channel == "family_message" and "hasn't confirmed" in o.body for o in ladder.notifier.outbox)


def test_advance_runs_only_what_is_due(profile, calendar):
    _, decision = case_decision("T01", profile, calendar)
    ladder = Ladder.start("chg", decision, profile)
    assert ladder.advance(parse_dt("2026-10-22T07:59:00-03:00")) == []
    ran = ladder.advance(parse_dt("2026-10-22T08:00:00-03:00"))
    assert [s.kind for s in ran] == [FIRST_CALL, RECORD_EMAIL]
    assert ladder.next_step().kind == RETRY_CALL
    assert "Quiet hours" in ladder.log[0][1]


# ---- "Got it" link -------------------------------------------------------------

def test_link_confirms_once_and_cancels_the_rest(profile, calendar):
    _, decision = case_decision("T01", profile, calendar)
    ladder = Ladder.start("chg", decision, profile)
    ladder.advance(parse_dt("2026-10-22T08:00:00-03:00"))
    assert ladder.tap_link(ladder.token, parse_dt("2026-10-22T09:15:00-03:00")) == "confirmed"
    assert ladder.status == "confirmed" and ladder.confirmed_via == "got_it_link"
    assert ladder.tap_link(ladder.token, parse_dt("2026-10-22T09:16:00-03:00")) == "already_used"
    ladder.advance(parse_dt("2026-10-22T23:00:00-03:00"))
    assert len([o for o in ladder.notifier.outbox if o.channel == "call"]) == 1
    assert ladder.status == "confirmed"


def test_link_rejects_fake_and_expired(profile, calendar):
    _, decision = case_decision("T01", profile, calendar)
    ladder = Ladder.start("chg", decision, profile)
    assert ladder.tap_link("guessed-token", parse_dt("2026-10-22T09:00:00-03:00")) == "unknown"
    assert ladder.tap_link(ladder.token, parse_dt("2026-10-22T14:30:00-03:00")) == "expired"
    assert ladder.status == "waiting"


def test_token_for_another_change_does_not_confirm(profile, calendar):
    _, decision = case_decision("T01", profile, calendar)
    tokens = TokenStore()
    ladder = Ladder.start("chg_a", decision, profile, tokens=tokens)
    other = tokens.make("chg_b", parse_dt(decision.new_start))
    assert ladder.tap_link(other, parse_dt("2026-10-22T09:00:00-03:00")) == "confirmed"  # valid for chg_b
    assert ladder.status == "waiting"                                                    # but not this one


def test_tokens_are_unique_and_long():
    store, expiry = TokenStore(), datetime(2030, 1, 1)
    tokens = {store.make("c", expiry) for _ in range(200)}
    assert len(tokens) == 200 and min(len(t) for t in tokens) >= 20


def test_confirm_twice_is_harmless(profile, calendar):
    _, decision = case_decision("T01", profile, calendar)
    ladder = Ladder.start("chg", decision, profile)
    at = parse_dt("2026-10-22T08:30:00-03:00")
    assert ladder.confirm(at, "press_1_on_call") is True
    assert ladder.confirm(at, "got_it_link") is False
    assert len(ladder.notifier.outbox) == 1  # one status message to Michelle, not two


# ---- Timing edge cases -----------------------------------------------------------

def fake_decision(sent: str, start: str) -> Decision:
    start_dt = parse_dt(start)
    return Decision(
        action=EDIT, code="edit", reason="test", sender="Michelle", event_id="evt_ava_pickup",
        occurrence_date=start_dt.date().isoformat(), old_start=start, new_start=start,
        new_end=(start_dt + timedelta(minutes=30)).isoformat(),
        alert_at=(start_dt - timedelta(minutes=30)).isoformat(),
        summary_label="CHANGED by Michelle, was 3:15", event_title="Pick up Ava",
        location="Oakwood Elementary", sent_at=sent)


@pytest.mark.parametrize("sent,first", [
    ("2026-10-21T20:59:00-03:00", "2026-10-21T20:59:00-03:00"),  # just before quiet hours
    ("2026-10-21T21:00:00-03:00", "2026-10-22T08:00:00-03:00"),  # quiet hours start
    ("2026-10-22T07:59:00-03:00", "2026-10-22T08:00:00-03:00"),  # still quiet
    ("2026-10-22T08:00:00-03:00", "2026-10-22T08:00:00-03:00"),  # quiet hours over
])
def test_quiet_hours_boundaries(sent, first, profile):
    steps = plan_ladder(fake_decision(sent, "2026-10-22T14:30:00-03:00"), profile)
    assert times(steps, FIRST_CALL) == first


def test_urgent_change_at_night_calls_now(profile):
    # 11 PM text about an 8:30 AM pickup: waiting until 8 AM would leave 30 min, so call now.
    steps = plan_ladder(fake_decision("2026-10-21T23:00:00-03:00", "2026-10-22T08:30:00-03:00"), profile)
    assert times(steps, FIRST_CALL) == "2026-10-21T23:00:00-03:00"


def test_event_under_an_hour_away_asks_family_with_first_call(profile):
    steps = plan_ladder(fake_decision("2026-10-22T14:00:00-03:00", "2026-10-22T14:45:00-03:00"), profile)
    assert times(steps, FIRST_CALL) == times(steps, FAMILY_REQUEST) == "2026-10-22T14:00:00-03:00"
    assert times(steps, RETRY_CALL) is None


def test_only_edits_get_a_ladder(profile):
    with pytest.raises(ValueError):
        plan_ladder(Decision(action="ask_gloria", code="unclear_date", reason="x"), profile)
