"""The orchestrator end to end: inbox -> decisions -> calendar -> ladder -> outbox -> snapshot."""
import json
from datetime import timedelta

import pytest

from app import build_agent
from heads_up.escalation import NO_ANSWER
from heads_up.timeutil import parse_dt

END = parse_dt("2026-10-22T16:00:00-03:00")


def at(s):
    return parse_dt(f"2026-10-22T{s}:00-03:00")


def by_id(agent, msg_id):
    return next(i for i in agent.inbox if i.id == msg_id)


def channels(agent):
    return [(o.at.strftime("%H:%M"), o.channel) for o in agent.notifier.outbox]


def test_build_handles_earlier_texts_and_waits_at_replay_start():
    agent = build_agent()
    assert agent.clock.isoformat() == "2026-10-21T18:00:00-03:00"
    codes = {i.id: (i.status, i.decision and i.decision.code) for i in agent.inbox}
    assert codes["sms_001"] == ("processed", "not_a_change")       # Michelle's thanks: read, no action
    assert codes["sms_002"] == ("processed", "unknown_sender")     # pharmacy never reaches the LLM
    assert codes["sms_003"] == ("processed", "unknown_sender")     # Canada Post scam text
    assert codes["sms_005"] == ("scheduled", None)                 # 10:48 PM text hasn't arrived yet
    assert "sms_006" not in codes and "sms_007" not in codes       # only in the 'without' timeline
    assert agent.notifier.outbox == []


def test_full_thursday_when_gloria_never_answers():
    agent = build_agent("no_answer")
    agent.advance_to(END)
    item = by_id(agent, "sms_005")
    assert item.decision.code == "edit" and item.change_id == "chg_sms_005"
    assert channels(agent) == [("08:00", "call"), ("08:00", "email"), ("10:00", "call"), ("13:30", "family_message")]
    (ava,) = [o for o in agent.calendar.occurrences_on(at("12:00").date()) if o.category == "ava_pickup"]
    assert ava.start == at("14:30") and ava.alert_minutes == [30]
    assert agent.ladders["chg_sms_005"].status == "ended_unconfirmed"


def test_full_thursday_when_gloria_presses_1():
    agent = build_agent("press_1")
    agent.advance_to(END)
    # Michelle hears "confirmed" right after the call; the record email still goes out.
    assert channels(agent) == [("08:00", "call"), ("08:00", "family_message"), ("08:00", "email")]
    assert agent.notifier.outbox[1].body == "Your mom confirmed the 2:30 pickup for Ava today."
    assert agent.ladders["chg_sms_005"].status == "confirmed"


def test_step_walks_one_event_at_a_time():
    agent = build_agent()
    stops = []
    while (t := agent.step()) is not None:
        stops.append(t.strftime("%a %H:%M"))
    assert stops == ["Wed 22:48", "Thu 08:00", "Thu 10:00", "Thu 13:30", "Thu 14:00", "Thu 14:30"]


def test_press_1_live_on_the_ringing_call():
    agent = build_agent("no_answer")
    agent.step()                                   # 22:48 text arrives, call waits for 8 AM
    assert agent.ringing_call() is None
    with pytest.raises(ValueError):
        agent.press_1()
    agent.step()                                   # 08:00: phone rings
    assert agent.snapshot()["ringing_call"]["kind"] == "first_call"
    assert agent.press_1() is True
    agent.advance_to(END)
    assert agent.ladders["chg_sms_005"].confirmed_via == "press_1_on_call"
    assert [c for _, c in channels(agent)].count("call") == 1     # no 10 AM retry


def test_tap_link_from_the_email():
    agent = build_agent("no_answer")
    agent.advance_to(at("09:15"))
    token = agent.ladders["chg_sms_005"].token
    assert agent.tap_link(token) == "confirmed"
    assert agent.tap_link(token) == "already_used"
    assert agent.tap_link("made-up") == "unknown"
    agent.advance_to(END)
    assert not any(o.channel == "family_message" and "hasn't" in o.body for o in agent.notifier.outbox)


def test_paused_agent_changes_nothing():
    agent = build_agent()
    agent.pause()
    agent.advance_to(END)
    assert by_id(agent, "sms_005").decision.code == "paused"
    assert agent.ladders == {} and agent.notifier.outbox == []
    (ava,) = [o for o in agent.calendar.occurrences_on(at("12:00").date()) if o.category == "ava_pickup"]
    assert ava.start.strftime("%H:%M") == "15:15"


def test_unknown_text_offline_asks_gloria_instead_of_guessing():
    agent = build_agent()
    item = agent.receive("+19025550123", "Mom could you grab Ava a bit earlier tomorrow?", "Michelle")
    assert item.decision.code == "llm_error"                 # no saved reading offline
    (question,) = agent.notifier.outbox
    assert question.channel == "question" and "didn't change your calendar" in question.body


def test_received_text_from_a_stranger_is_ignored():
    agent = build_agent()
    item = agent.receive("+15555550000", "Gloria this is your bank, reply with your PIN")
    assert item.decision.code == "unknown_sender" and agent.notifier.outbox == []


def test_urgent_text_calls_right_away():
    agent = build_agent()
    agent.inbox = [i for i in agent.inbox if i.id != "sms_005"]    # no 10:48 PM text this time
    agent.advance_to(at("13:30"))
    agent.extractor.by_body["Mom can you get Ava at 3:00 today instead of 3:15?"] = {
        "is_plan_change": True, "event_hint": "Ava pickup", "category": "ava_pickup", "date_phrase": "today",
        "new_time": "15:00", "old_time": "15:15", "is_cancellation": False, "scope": "one_occurrence",
        "change_count": 1, "confidence": "high"}
    agent.receive("+19025550123", "Mom can you get Ava at 3:00 today instead of 3:15?", "Michelle")
    assert channels(agent)[:2] == [("13:30", "call"), ("13:30", "email")]


def test_clock_never_goes_backwards():
    agent = build_agent()
    with pytest.raises(ValueError):
        agent.advance_to(agent.clock - timedelta(minutes=1))


def test_call_policy_is_validated():
    agent = build_agent()
    with pytest.raises(ValueError):
        agent.set_call_policy(first="picked up and danced")
    agent.set_call_policy(first=NO_ANSWER, retry=NO_ANSWER)


def test_snapshot_is_plain_json_and_complete():
    agent = build_agent()
    agent.advance_to(at("10:00"))
    snap = json.loads(agent.snapshot_json())
    assert snap["clock"] == "2026-10-22T10:00:00-03:00"
    assert snap["ringing_call"] == {"change_id": "chg_sms_005", "kind": "retry_call"}
    assert snap["next_event_at"] == "2026-10-22T13:30:00-03:00"
    thursday = snap["calendar"]["2026-10-22"]
    assert thursday[0]["summary"] == "Pick up Ava — CHANGED by Michelle, was 3:15" and thursday[0]["changed"]
    (change,) = snap["changes"]
    assert change["link"].startswith("https://heads-up.local/confirm/")
    assert [s["status"] for s in change["steps"]][:3] == ["done", "done", "done"]
    assert {i["id"] for i in snap["inbox"]} >= {"sms_001", "sms_005"}
    assert snap["timeline"][-1]["kind"] == "call"
