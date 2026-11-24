import copy
import json
from pathlib import Path

import pytest

from heads_up.calendar_store import CalendarStore

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_data"


def load(name: str) -> dict:
    return json.loads((SAMPLE / name).read_text(encoding="utf-8"))


@pytest.fixture
def profile() -> dict:
    return load("gloria_profile.json")


@pytest.fixture
def calendar() -> CalendarStore:
    return CalendarStore.from_sample(load("calendar_events.json"))


def with_overrides(profile: dict, overrides: dict | None) -> dict:
    """Apply dotted-path overrides like {'consent.agent_paused': true}."""
    profile = copy.deepcopy(profile)
    for path, value in (overrides or {}).items():
        node = profile
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return profile
