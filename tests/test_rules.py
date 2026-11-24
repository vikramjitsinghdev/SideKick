"""The 22 labelled texts from sample_data/test_messages.json, run through the rules engine.

The LLM is replaced by the gold extraction for each case, so these tests check
the code's decisions exactly. Texts whose gold extraction is null must never be
sent to the LLM at all.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from heads_up import dates
from heads_up.extraction import ExtractionError, validate
from heads_up.rules import ASK, EDIT, NONE, Message, apply, decide
from heads_up.timeutil import HALIFAX
from conftest import load, with_overrides

CASES = load("test_messages.json")["cases"]
GOLD = json.loads((Path(__file__).parent / "fixtures" / "gold_extractions.json").read_text(encoding="utf-8"))
EDIT_FIELDS = ("event_id", "occurrence_date", "new_start", "new_end", "alert_at", "summary_label")


def gold_extractor(case_id):
    def extract(msg):
        gold = GOLD[case_id]
        if gold is None:
            raise AssertionError(f"{case_id}: this text must never reach the LLM")
        return gold
    return extract


def run(case, profile, calendar):
    msg = Message(case["id"], case["from_phone"], case["sent_at"], case["body"])
    prof = with_overrides(profile, case.get("context_overrides"))
    return decide(msg, prof, calendar, gold_extractor(case["id"]))


# Why each case should stop. Checking the reason, not just the action, stops a
# case from passing by luck (e.g. a wrong date that happens to have zero matches).
EXPECTED_CODE = {
    "T01": "edit", "T02": "unclear_date", "T03": "edit", "T04": "unknown_sender",
    "T05": "series_request", "T06": "vague_time", "T07": "match_count", "T08": "match_count",
    "T09": "not_a_change", "T10": "not_a_change", "T11": "category_not_allowed",
    "T12": "cancellation", "T13": "edit", "T14": "unknown_sender", "T15": "unknown_sender",
    "T16": "unclear_date", "T17": "edit", "T18": "multiple_changes", "T19": "edit",
    "T20": "not_a_change", "T21": "paused", "T22": "unknown_sender",
}


def test_every_case_has_an_expected_code():
    assert set(EXPECTED_CODE) == {c["id"] for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case, profile, calendar):
    expected = case["expected"]
    # Extensions (pharmacy deadline, suspicious text) aren't built yet: core must do nothing.
    want = expected.get("core_only_expected_action", expected["action"])
    decision = run(case, profile, calendar)
    assert decision.action == want, f"{case['id']}: {decision.reason}"
    assert decision.code == EXPECTED_CODE[case["id"]], f"{case['id']}: {decision.reason}"
    if want == EDIT:
        for key in EDIT_FIELDS:
            assert getattr(decision, key) == expected[key], f"{case['id']} {key}"


def test_pass_targets(profile, calendar):
    """The headline numbers from the pitch, computed over the whole set."""
    edits_when_unclear = edits_from_unknown = 0
    trusted = {c["phone"] for c in profile["trusted_contacts"]}
    for case in CASES:
        d = run(case, profile, calendar)
        if d.action == EDIT and case["expected"]["action"] != EDIT:
            edits_when_unclear += 1
        if d.action == EDIT and case["from_phone"] not in trusted:
            edits_from_unknown += 1
    assert edits_when_unclear == 0
    assert edits_from_unknown == 0


# --- Calendar: only ever one occurrence ------------------------------------

def test_apply_moves_only_that_thursday(profile, calendar):
    case = next(c for c in CASES if c["id"] == "T01")
    d = run(case, profile, calendar)
    moved = apply(d, calendar, profile)
    assert moved.start.isoformat() == "2026-10-22T14:30:00-03:00"
    assert moved.alert_minutes == [30]
    assert "CHANGED by Michelle, was 3:15" in moved.summary
    # Tuesday before and Thursday after are untouched; the series itself is unchanged.
    for day in (date(2026, 10, 20), date(2026, 10, 27), date(2026, 10, 29)):
        (ava,) = [o for o in calendar.occurrences_on(day) if o.category == "ava_pickup"]
        assert ava.start.strftime("%H:%M") == "15:15" and not ava.changed
    assert calendar.events[0]["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=TU,TH"]


def test_dst_occurrence_after_fall_back(calendar):
    """Nov 3 2026 is after clocks fall back: 3:15 PM must stay 3:15 PM local (AST, -04:00)."""
    (ava,) = [o for o in calendar.occurrences_on(date(2026, 11, 3)) if o.category == "ava_pickup"]
    assert ava.start.isoformat() == "2026-11-03T15:15:00-04:00"


# --- Fail-safe behaviour ---------------------------------------------------

T01 = next(c for c in CASES if c["id"] == "T01")
MICHELLE_MSG = Message("x", T01["from_phone"], T01["sent_at"], T01["body"])


def test_broken_llm_json_asks_gloria(profile, calendar):
    d = decide(MICHELLE_MSG, profile, calendar, lambda m: {"is_plan_change": "yes"})
    assert d.action == ASK


def test_llm_outage_asks_gloria(profile, calendar):
    def down(m):
        raise ConnectionError("groq down")
    assert decide(MICHELLE_MSG, profile, calendar, down).action == ASK


def test_misread_am_time_is_not_applied(profile, calendar):
    bad = dict(GOLD["T01"], new_time="02:30")
    assert decide(MICHELLE_MSG, profile, calendar, lambda m: bad).action == ASK


def test_old_time_mismatch_asks(profile, calendar):
    bad = dict(GOLD["T01"], old_time="16:00")
    assert decide(MICHELLE_MSG, profile, calendar, lambda m: bad).action == ASK


def test_ray_cannot_change_ava_pickup(profile, calendar):
    msg = Message("x", "+19025550102", T01["sent_at"], T01["body"])
    assert decide(msg, profile, calendar, lambda m: GOLD["T01"]).action == ASK


# --- Dates -----------------------------------------------------------------

def at(s):
    return datetime.fromisoformat(s).astimezone(HALIFAX)


@pytest.mark.parametrize("phrase,sent,want", [
    ("tomorrow", "2026-10-21T22:48:00-03:00", date(2026, 10, 22)),
    ("tomorrow", "2026-10-22T05:00:00-03:00", date(2026, 10, 23)),
    ("Thursday", "2026-10-19T09:12:00-03:00", date(2026, 10, 22)),
    ("on Friday", "2026-10-21T18:20:00-03:00", date(2026, 10, 23)),
    ("today", "2026-10-22T13:30:00-03:00", date(2026, 10, 22)),
    ("Oct 23", "2026-10-20T11:30:00-03:00", date(2026, 10, 23)),
    ("Fri Oct 23", "2026-10-20T11:30:00-03:00", date(2026, 10, 23)),
])
def test_dates_resolve(phrase, sent, want):
    assert dates.resolve(phrase, at(sent)) == want


@pytest.mark.parametrize("phrase,sent", [
    ("tomorrow", "2026-10-22T00:30:00-03:00"),
    ("tomorrow", "2026-10-22T04:59:00-03:00"),
    ("Thursday", "2026-10-22T09:00:00-03:00"),
    ("next Thursday", "2026-10-19T09:00:00-03:00"),
    ("one day next week", "2026-10-19T20:00:00-03:00"),
    (None, "2026-10-19T20:00:00-03:00"),
])
def test_dates_unclear(phrase, sent):
    with pytest.raises(dates.UnclearDate):
        dates.resolve(phrase, at(sent))


# --- Schema ----------------------------------------------------------------

@pytest.mark.parametrize("patch", [
    {"category": "dentist"},
    {"new_time": "2:30pm"},
    {"scope": "some"},
    {"change_count": True},
    {"is_plan_change": "true"},
])
def test_schema_rejects(patch):
    with pytest.raises(ExtractionError):
        validate(dict(GOLD["T01"], **patch))


def test_schema_rejects_missing_field():
    raw = dict(GOLD["T01"])
    del raw["scope"]
    with pytest.raises(ExtractionError):
        validate(raw)
