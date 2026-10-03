"""Locks on the reconciliation of the two invariant sets.

`architecture/invariants.yaml` registers the EPISTEMIC layer. The
numbered set I1-I10 is about the CANONICAL-STATE/PROJECTION core. Both
this repository and a sibling's request treated the first as "STE's
invariant set"; neither contains the other, and citing the YAML alone
loses the canonical core entirely.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

REPO = pathlib.Path(__file__).resolve().parent.parent
RECONCILIATION = REPO / "architecture" / "canonical_state_invariants.yaml"
EPISTEMIC = REPO / "architecture" / "invariants.yaml"


def _ids(path):
    document = yaml.safe_load(path.read_text())
    return {e["id"] for e in (document.get("invariants") or [])}


def test_the_two_sets_are_disjoint_neither_contains_the_other():
    """The verdict, asserted rather than narrated. Containment fails in
    BOTH directions -- that is what makes 'superseded' and 'subset' both
    wrong answers."""
    canonical = _ids(RECONCILIATION)
    epistemic = _ids(EPISTEMIC)
    assert canonical and epistemic
    assert not (canonical & epistemic), (
        "an overlapping id would mean one set does contain part of the "
        "other, and the verdict would need restating")


def test_every_registered_recovery_names_its_numbered_origin():
    """Provenance, not adoption. This repository cannot verify what the
    brief said -- only what its own citations constrain -- so each entry
    records the number it was recovered FROM rather than taking the
    brief's numbering as its own id."""
    document = yaml.safe_load(RECONCILIATION.read_text())
    for entry in document["invariants"]:
        assert entry["numbered_as"], entry["id"]
        assert entry["recovery"].startswith(("fully", "partially")), entry["id"]
        assert not entry["id"].startswith("I"), (
            f"{entry['id']}: the brief's numbering is provenance, not an id")


def test_an_unrecoverable_invariant_is_not_registered_as_one():
    """A rule that cannot be stated cannot be declared.

    I1 and I2 are cited only inside a range whose referent is not in this
    repository; I9 and I10 are cited nowhere at all. None is registered
    -- they are recorded under `unrecovered` so the gap is visible rather
    than inferred from absence.
    """
    document = yaml.safe_load(RECONCILIATION.read_text())
    registered = {e["numbered_as"] for e in document["invariants"]}
    unrecovered = document["unrecovered"]
    assert set(unrecovered) == {"I1", "I2", "I9", "I10"}
    for number in unrecovered:
        assert number not in registered
    assert {unrecovered[n]["status"] for n in ("I1", "I2")} == {"UNRECOVERABLE"}
    assert {unrecovered[n]["status"] for n in ("I9", "I10")} == {"NO_REFERENT"}


def test_the_cardinality_is_retracted_not_replaced():
    """Swapping one unsupported number for another would look like a fix.

    Ten is unsupported; eight is a single citation to an absent referent
    and is not established either. The claim is retracted and the floor
    that IS established is stated instead.
    """
    document = yaml.safe_load(RECONCILIATION.read_text())
    cardinality = document["the_cardinality"]
    assert "RETRACTED" in cardinality["verdict"]
    assert "eight" in cardinality["verdict"], (
        "the verdict must say explicitly why eight is not the answer either")
    assert "floor" in cardinality["what_is_established"]


def test_no_numbered_invariant_list_exists_in_the_tree():
    """The measurement behind the retraction, re-run rather than
    remembered. If someone adds an enumeration later this fails, which is
    the correct outcome: the retraction would then be stale."""
    import re

    pattern = re.compile(r"^\s*\|?\s*I(10|[1-9])\s*[|:.]", re.MULTILINE)
    for path in sorted((REPO / "docs").glob("*.md")):
        assert not pattern.search(path.read_text()), (
            f"{path.name} now contains a numbered invariant list -- the "
            f"cardinality retraction must be revisited")


@pytest.mark.parametrize("invariant_id", sorted(_ids(RECONCILIATION)))
def test_every_registered_invariant_is_cited_by_a_test_that_enforces_it(invariant_id):
    """The citation bar, met by evidence rather than by lowering it.

    Before this reconciliation only I5 was cited by a test; I3, I6, I7
    and I8 appeared in implementation docstrings and nowhere else, and I4
    in prose only. Enforcement was real throughout and the machine-
    checkable link was absent -- the sibling's own recorded defect,
    arriving here by the opposite route: not a claim without enforcement,
    but enforcement without a claim.
    """
    document = yaml.safe_load(RECONCILIATION.read_text())
    entry = next(e for e in document["invariants"] if e["id"] == invariant_id)
    locks = [p.strip() for p in str(entry["enforcement"]["locks"]).split(",")]
    assert locks, invariant_id
    cited_by = [lock for lock in locks
                if invariant_id in (REPO / lock).read_text(errors="replace")]
    assert cited_by, (
        f"{invariant_id} claims enforcement by {locks} and no named lock "
        f"mentions it -- a cited file that never names the id is not "
        f"evidence for it")
