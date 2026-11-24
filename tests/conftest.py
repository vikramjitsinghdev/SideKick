import pytest

from heads_up.calendar_store import CalendarStore
from heads_up.config import load_sample as load, with_overrides  # noqa: F401  (re-exported for tests)


@pytest.fixture
def profile() -> dict:
    return load("gloria_profile.json")


@pytest.fixture
def calendar() -> CalendarStore:
    return CalendarStore.from_sample(load("calendar_events.json"))
