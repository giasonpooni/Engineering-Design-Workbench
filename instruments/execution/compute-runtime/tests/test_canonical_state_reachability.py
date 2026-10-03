"""Locks on the canonical-state reachability probe.

A sibling reported `bent: zero` over this repository's declared
canonical-state set as SILENCE -- "no authored package imports core.* at
all", so a zero over it is not a measurement. The rule is this
repository's and it is right. The premise is not true here, and these
pin both halves of the answer.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.canonical_state_reachability import (
    GATE, MALFORMED, PROPERTY, REACHED, STRUCTURAL, SUBJECTS,
    importers_of, probe,
)


def test_the_premise_does_not_hold_in_this_repository():
    """Four authored packages import core.*, and every named subject is
    reached. The sibling measured which of ITS packages reach a vendored
    copy -- a different question about a different tree, and both
    answers are right about their own subject. Same shape as the
    disjoint gate sets."""
    importers = importers_of()
    assert importers, "an empty result would make the sibling's premise hold here"
    assert {"morpho", "backends", "runtime", "adapters"} <= set(importers)


def test_every_gate_is_reached_by_a_planted_violation():
    """AN IMPORT EDGE IS AN INFERENCE -- this repository's other rule --
    so the edge is not the answer either. The violation is planted at
    `validate_candidate`, which adapters/interface declares the sole
    entry point and which an adapter feeds from external data."""
    for subject in probe():
        if subject.kind == GATE:
            assert subject.verdict == REACHED, (
                f"{subject.invariant_id}: {subject.verdict} -- {subject.detail}")


def test_a_malformed_plant_is_never_counted_as_a_hit():
    """THE GUARD THIS PROBE SHIPPED WITHOUT, and paid for immediately.

    On the first run two plants crashed on their OWN construction --
    `Operation.ADD` does not exist, and the Version signature was wrong
    -- and an exception handler that could not tell a gate firing from a
    plant failing to build scored both REACHED. Four separate corrections
    to one plant followed, each caught here rather than reported as a
    measurement: the wrong operation type, the wrong EdgeRecord fields, a
    missing timestamp, and an unindexed path.

    A hit requires the GATE's own refusal, identified by a fragment
    specific enough to be one -- `"EDGE"` was not: it matched
    `EdgeRecord` inside a TypeError from the plant's construction. A
    fragment loose enough to match the subject does not identify the
    refusal.
    """
    from scripts.canonical_state_reachability import Subject, GATE as _G

    misaimed = Subject(
        "planted_malformed", _G, "nowhere",
        plant=lambda: (_ for _ in ()).throw(TypeError("built wrong")),
        fragment="THE_REFUSAL_CODE")
    SUBJECTS.append(misaimed)
    try:
        probe()
        assert misaimed.verdict == MALFORMED
        assert "measured the plant" in misaimed.detail
    finally:
        SUBJECTS.remove(misaimed)
        probe()  # restore the real verdicts for any later reader


def test_the_three_shapes_are_not_collapsed_into_one_verdict():
    """Reporting one verdict over five subjects would repeat the error
    the chemistry probe exists to avoid.

    A structural absence called "unreachable" reads as a hole; a
    determinism property called "reachable" reads as a gate nobody
    trips. Neither is true, and each is recorded as what it is.
    """
    kinds = {s.kind for s in SUBJECTS}
    assert kinds == {GATE, STRUCTURAL, PROPERTY}
    for subject in probe():
        if subject.kind == STRUCTURAL:
            assert subject.verdict == "NO_VIOLATING_PATH_EXISTS"
        elif subject.kind == PROPERTY:
            assert subject.verdict == "HOLDS_OVER_EXECUTION"
