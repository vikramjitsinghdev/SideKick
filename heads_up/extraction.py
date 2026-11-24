"""The JSON contract between the LLM and the rules engine.

The LLM only *reads* a text and fills in these fields. It never resolves dates,
picks events or decides actions; code does all of that. Anything that fails
validation is treated as unreadable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = {"ava_pickup", "noah_pickup", "ray_appointment", "choir", "garden_club"}
SCOPES = {"one_occurrence", "all_occurrences"}
CONFIDENCE = {"high", "low"}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

SCHEMA_DESCRIPTION = {
    "is_plan_change": "boolean: does the text ask Gloria to change an upcoming plan?",
    "event_hint": "string | null: the event in the sender's words, e.g. 'Ava pickup'",
    "category": "ava_pickup | noah_pickup | ray_appointment | choir | garden_club | null",
    "date_phrase": "string | null: the exact date words, e.g. 'tomorrow', 'Thursday', 'today'",
    "new_time": "HH:MM 24h | null: the new time, null if vague",
    "old_time": "HH:MM 24h | null: the time being replaced, if stated",
    "is_cancellation": "boolean: is the plan being cancelled rather than moved?",
    "scope": "one_occurrence | all_occurrences: does it ask to change every repeat of the event?",
    "change_count": "integer: how many separate plan changes the text asks for",
    "confidence": "high | low",
}


@dataclass(frozen=True)
class Extraction:
    is_plan_change: bool
    event_hint: str | None
    category: str | None
    date_phrase: str | None
    new_time: str | None
    old_time: str | None
    is_cancellation: bool
    scope: str
    change_count: int
    confidence: str


class ExtractionError(ValueError):
    pass


def validate(raw: object) -> Extraction:
    """Turn the LLM's JSON into an Extraction, or raise ExtractionError."""
    if not isinstance(raw, dict):
        raise ExtractionError("not a JSON object")
    missing = set(SCHEMA_DESCRIPTION) - set(raw)
    if missing:
        raise ExtractionError(f"missing fields: {sorted(missing)}")

    def opt_str(key: str) -> str | None:
        value = raw[key]
        if value is not None and not isinstance(value, str):
            raise ExtractionError(f"{key} must be a string or null")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def boolean(key: str) -> bool:
        if not isinstance(raw[key], bool):
            raise ExtractionError(f"{key} must be true or false")
        return raw[key]

    category = opt_str("category")
    if category is not None and category not in CATEGORIES:
        raise ExtractionError(f"unknown category {category!r}")
    for key in ("new_time", "old_time"):
        if opt_str(key) is not None and not HHMM.match(opt_str(key)):
            raise ExtractionError(f"{key} must be HH:MM (24h)")
    if raw["scope"] not in SCOPES:
        raise ExtractionError("scope must be one_occurrence or all_occurrences")
    if raw["confidence"] not in CONFIDENCE:
        raise ExtractionError("confidence must be high or low")
    count = raw["change_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ExtractionError("change_count must be a non-negative integer")

    return Extraction(
        is_plan_change=boolean("is_plan_change"),
        event_hint=opt_str("event_hint"),
        category=category,
        date_phrase=opt_str("date_phrase"),
        new_time=opt_str("new_time"),
        old_time=opt_str("old_time"),
        is_cancellation=boolean("is_cancellation"),
        scope=raw["scope"],
        change_count=count,
        confidence=raw["confidence"],
    )
