"""Run the REAL LLM on the 22 test texts and score it.

Two scores:
  1. Reading accuracy: does the model's JSON match the gold reading, field by field?
  2. End-to-end: with the model's real reading, does decide() still take the
     expected action for the expected reason?

The headline safety numbers (edits when unclear, edits from unknown senders)
come from score 2. Score 1 shows where the prompt needs work.

Usage (from the repo root, with GROQ_API_KEY in .env):
    python scripts/eval_llm.py
    python scripts/eval_llm.py --only T01 T05 T17
Results are written to results/llm_eval.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heads_up.calendar_store import CalendarStore  # noqa: E402
from heads_up.extraction import ExtractionError, validate  # noqa: E402
from heads_up.extractor import LLMExtractor  # noqa: E402
from heads_up.rules import EDIT, Message, decide  # noqa: E402
from heads_up.config import with_overrides  # noqa: E402

FIELDS = ["is_plan_change", "category", "date_phrase", "new_time", "old_time",
          "is_cancellation", "scope", "change_count", "confidence"]


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def same(field: str, got, want) -> bool:
    if field == "date_phrase":
        norm = lambda v: " ".join(str(v).lower().replace("on ", "").split()) if v else None  # noqa: E731
        return norm(got) == norm(want)
    if field == "change_count":  # what matters to the rules is 0, 1 or "more than one"
        return min(got or 0, 2) == min(want or 0, 2)
    return got == want


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="case ids to run, e.g. T01 T05")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between calls (rate limits)")
    args = parser.parse_args()

    profile = load("sample_data/gloria_profile.json")
    events = load("sample_data/calendar_events.json")
    cases = load("sample_data/test_messages.json")["cases"]
    gold = load("tests/fixtures/gold_extractions.json")
    extractor = LLMExtractor.from_env(profile, env_path=str(ROOT / ".env"))
    trusted = {c["phone"] for c in profile["trusted_contacts"]}

    rows, field_hits, field_total = [], 0, 0
    edits_when_unclear = edits_from_unknown = llm_calls = 0

    for case in cases:
        if args.only and case["id"] not in args.only:
            continue
        msg = Message(case["id"], case["from_phone"], case["sent_at"], case["body"])
        prof = with_overrides(profile, case.get("context_overrides"))
        seen: dict = {}

        def recording_extractor(m):
            seen["called"] = True
            seen["raw"] = extractor(m)
            seen["provider"] = extractor.last_provider
            groq = extractor.providers[0]
            seen["mode"] = getattr(groq, "last_mode", None) if extractor.last_provider == "groq" else None
            seen["strict_error"] = getattr(groq, "last_strict_error", None)
            return seen["raw"]

        decision = decide(msg, prof, CalendarStore(events["events"]), recording_extractor)
        expected = case["expected"]
        want_action = expected.get("core_only_expected_action", expected["action"])

        mismatched = []
        if seen.get("called"):
            llm_calls += 1
            if "raw" not in seen:
                mismatched.append("LLM call failed: " + "; ".join(extractor.last_errors))
            elif gold[case["id"]] is not None:
                try:
                    reading = validate(seen["raw"]).__dict__
                except ExtractionError as err:
                    reading = {}
                    mismatched.append(f"invalid JSON: {err}")
                for f in FIELDS:
                    field_total += 1
                    if reading and same(f, reading.get(f), gold[case["id"]][f]):
                        field_hits += 1
                    elif reading:
                        mismatched.append(f"{f}: got {reading.get(f)!r}, want {gold[case['id']][f]!r}")
            time.sleep(args.pause)

        want_code = expected["code"]
        ok = decision.action == want_action and decision.code == want_code
        if decision.action == EDIT and expected["action"] != EDIT:
            edits_when_unclear += 1
        if decision.action == EDIT and case["from_phone"] not in trusted:
            edits_from_unknown += 1
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "expected": f"{want_action} [{want_code}]",
            "actual": f"{decision.action} [{decision.code}]",
            "pass": ok,
            "llm_called": bool(seen.get("called")),
            "provider": seen.get("provider"),
            "mode": seen.get("mode"),
            "strict_error": seen.get("strict_error"),
            "reading_mismatches": mismatched,
            "reason": decision.reason,
            "llm_raw": seen.get("raw"),
        })

    # ---- print the expected-vs-actual table
    print(f"\n{'ID':<5}{'Pass':<6}{'Expected':<40}{'Actual':<40}LLM")
    for r in rows:
        llm = r["provider"] or ("-" if not r["llm_called"] else "failed")
        if r.get("mode") and r["mode"] != "strict_schema":
            llm += f" ({r['mode']})"
        print(f"{r['id']:<5}{'yes' if r['pass'] else 'NO':<6}{r['expected']:<40}{r['actual']:<40}{llm}")
        for m in r["reading_mismatches"]:
            print(f"{'':<11}reading: {m}")

    passed = sum(r["pass"] for r in rows)
    summary = {
        "model": getattr(extractor.providers[0], "model", None),
        "cases": len(rows),
        "end_to_end_pass": passed,
        "reading_field_accuracy": round(field_hits / field_total, 3) if field_total else None,
        "llm_calls": llm_calls,
        "texts_kept_from_llm": len(rows) - llm_calls,
        "edits_when_unclear": edits_when_unclear,
        "edits_from_unknown_senders": edits_from_unknown,
        "strict_schema_calls": sum(1 for r in rows if r.get("mode") == "strict_schema"),
        "fallback_calls": sum(1 for r in rows if r.get("mode") in ("json_object", "json_object_retry")),
    }
    strict_errors = {r["strict_error"] for r in rows if r.get("strict_error")}
    if strict_errors:
        print("\nGroq refused strict mode; fell back to JSON mode. First error:\n  " + sorted(strict_errors)[0])
    print("\n" + json.dumps(summary, indent=2))

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "llm_eval.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nSaved {out / 'llm_eval.json'}")
    return 0 if passed == len(rows) and edits_when_unclear == edits_from_unknown == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
