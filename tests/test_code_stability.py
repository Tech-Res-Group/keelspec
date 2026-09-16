"""The code-stability rule, exercised without a network.

`scripts/check_code_stability.py` needs PyPI to find out what "released" means.
The rule it applies does not, so it lives in a pure function and is tested here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_code_stability.py"

_spec = importlib.util.spec_from_file_location("check_code_stability", SCRIPT)
assert _spec is not None and _spec.loader is not None
stability = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stability)

compare = stability.compare


def test_an_unchanged_table_is_clean():
    released = {"PAC-001": "missing field", "PAC-020": "dangling reference"}
    outcome = compare(released, dict(released), {})
    assert outcome.broken == []
    assert outcome.notices == []


def test_a_vanished_code_breaks_the_build():
    released = {"PAC-001": "missing field", "PAC-020": "dangling reference"}
    current = {"PAC-001": "missing field"}
    outcome = compare(released, current, {})
    assert len(outcome.broken) == 1
    assert "PAC-020" in outcome.broken[0]


def test_a_vanished_code_is_fine_once_it_is_declared_retired():
    released = {"PAC-001": "missing field", "PAC-020": "dangling reference"}
    current = {"PAC-001": "missing field"}
    outcome = compare(released, current, {"PAC-020": "references are checked by the index now"})
    assert outcome.broken == []
    assert any("PAC-020 retired" in n for n in outcome.notices)


def test_reassigning_a_retired_number_breaks_the_build():
    """The expensive one. A consumer's allowlist still matches, and now suppresses
    a rule it was never meant to."""
    released = {"PAC-020": "dangling reference"}
    current = {"PAC-020": "something else entirely"}
    outcome = compare(released, current, {"PAC-020": "withdrawn in 0.8"})
    assert len(outcome.broken) == 1
    assert "never reassigned" in outcome.broken[0]


def test_a_reworded_message_is_reported_and_not_failed():
    released = {"PAC-001": "artifact is missing a required field"}
    current = {"PAC-001": "artifact is missing a required frontmatter field"}
    outcome = compare(released, current, {})
    assert outcome.broken == []
    assert any("message changed" in n for n in outcome.notices)


def test_new_codes_are_reported_and_not_failed():
    released = {"PAC-001": "missing field"}
    current = {"PAC-001": "missing field", "PAC-070": "a brand new rule"}
    outcome = compare(released, current, {})
    assert outcome.broken == []
    assert any("PAC-070 is new" in n for n in outcome.notices)


def test_the_shipped_table_declares_nothing_retired_twice():
    """Guards the table itself, not the comparison: a number cannot be both live
    and burned."""
    from keelspec.diagnostics import CODES, RETIRED

    assert set(CODES) & set(RETIRED) == set()
