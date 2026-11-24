"""Turn the sender's date words into a calendar date, or say it's unclear.

Rules (from the approved pitch):
- Dates are worked out from when the text was SENT, in Halifax time.
- "tomorrow" sent between midnight and 5 AM is unclear (could mean today or the next day).
- A weekday name means the next one within 7 days; the same weekday as today is unclear.
- "next <weekday>", "one day next week" and anything else vague is unclear.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

WEEKDAY_NAMES = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
UNCLEAR_TOMORROW = (time(0, 0), time(5, 0))


class UnclearDate(ValueError):
    pass


def resolve(phrase: str | None, sent: datetime) -> date:
    if not phrase:
        raise UnclearDate("no date given")
    words = re.sub(r"[^\w\s-]", " ", phrase.lower()).split()
    words = [w for w in words if w not in {"on", "this", "the", "at"}]
    today = sent.date()

    if words == ["today"] or words == ["tonight"]:
        return today
    if words in (["tomorrow"], ["tmrw"], ["tmr"]):
        if UNCLEAR_TOMORROW[0] <= sent.time() < UNCLEAR_TOMORROW[1]:
            raise UnclearDate("'tomorrow' sent between midnight and 5 AM")
        return today + timedelta(days=1)
    if len(words) == 1 and words[0] in WEEKDAY_NAMES:
        ahead = (WEEKDAY_NAMES[words[0]] - today.weekday()) % 7
        if ahead == 0:
            raise UnclearDate("weekday named is today; could mean today or next week")
        return today + timedelta(days=ahead)

    # "Oct 22", "october 22", "22 oct"; also "Fri Oct 23"
    words = [w for w in words if w not in WEEKDAY_NAMES]
    if len(words) == 2:
        for m, d in (words, words[::-1]):
            if m[:3] in MONTHS and d.isdigit():
                return date(today.year, MONTHS[m[:3]], int(d))
    if len(words) == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", words[0]):
        return date.fromisoformat(words[0])

    raise UnclearDate(f"can't pin down a date from {phrase!r}")
