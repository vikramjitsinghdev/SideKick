"""Loading sample data and applying per-case profile overrides.

Shared by the app, scripts and tests, so none of them depend on pytest.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_data"


def load_sample(name: str) -> dict:
    return json.loads((SAMPLE / name).read_text(encoding="utf-8"))


def with_overrides(profile: dict, overrides: dict | None) -> dict:
    """Apply dotted-path overrides like {'consent.agent_paused': true} to a copy."""
    profile = copy.deepcopy(profile)
    for path, value in (overrides or {}).items():
        node = profile
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return profile
