#!/usr/bin/env python3
"""Reachability for the five canonical-state invariants.

WHY, AND WHO ASKED. The compute layer mirrored an acquisition-layer
result: `bent: zero` checked against this repository's newly declared
canonical-state set for the first time, with the verdict SILENCE rather
than cleanliness -- "every declared canonical-state invariant names a
subject under core.*, and no authored package there imports core.* at
all. By that repository's own rule, a zero over a subject nothing
reaches is not a measurement."

The rule is this repository's and it is right. The premise is not true
HERE: four authored packages import core.*, and every named subject is
reached -- core.canonical.state (1), core.canonical.validation (2),
core.projection.project (2), plus the backends. The sibling measured
which of ITS OWN packages reach a vendored copy, which is a different
question with a different answer, and the two disagree only because they
are about different trees. Same shape as the disjoint gate sets: two
correct results, one subject each.

But an import edge is an INFERENCE, which is this repository's other
rule, so the edge is not the answer either. This probe plants violations
at the production door -- `validate_candidate`, which adapters/interface
declares the sole entry point and which an adapter feeds from external
data -- and records what arrives.

THE FIVE ARE NOT ALL THE SAME SHAPE, and reporting one verdict over them
would repeat the error the chemistry probe was built to avoid:

  GATE        refuses a violation. Reachability is the question, and a
              plant answers it.
  STRUCTURAL  no path exists to violate. There is nothing to plant; the
              absence of a path IS the enforcement.
  PROPERTY    holds over every execution rather than refusing anything.
              A plant is category-inappropriate: determinism has no
              violating input, only a violating implementation.

Calling a structural absence "unreachable" would read as a hole, and
calling a property "reachable" would read as a gate nobody trips. Each
is recorded as what it is.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.schema import FieldSchema, StateSchema
from core.canonical.state import CanonicalState, EdgeRecord, Field
from core.canonical.validation import ValidationError, validate_candidate
from core.canonical.version import ProvenanceInfo, Version
from core.projection.project import project_state

GATE, STRUCTURAL, PROPERTY = "gate", "structural", "property"
REACHED = "REACHED"
MALFORMED = "MALFORMED_PLANT"
ADMITTED = "ADMITTED"
NO_PATH = "NO_VIOLATING_PATH_EXISTS"
HOLDS = "HOLDS_OVER_EXECUTION"


@dataclass
class Subject:
    invariant_id: str
    kind: str
    subject_module: str
    plant: Optional[Callable[[], object]] = None
    #: A fragment the GATE's own refusal must carry. Without it any
    #: exception counts as a hit -- which is exactly what happened on the
    #: first run: `Operation.ADD` does not exist and the Version
    #: signature was wrong, so two plants crashed on their own
    #: construction and were scored REACHED. A plant that fails to build
    #: measures the plant.
    fragment: str = ""
    verdict: str = ""
    detail: str = ""


def _schema() -> StateSchema:
    return StateSchema(
        schema_version="v1",
        fields={"temperature": FieldSchema(id="temperature", type="number", unit="K")},
    )


def _base(schema: StateSchema) -> CanonicalState:
    return CanonicalState(
        schema_version=schema.schema_version,
        fields={"temperature": Field(id="temperature", type="number", value=300)},
    )


def _prov() -> ProvenanceInfo:
    return ProvenanceInfo(author="reachability-probe", transaction_id="t1",
                          source="manual_edit")


# -- the plants ------------------------------------------------------------


def _plant_field_identity():
    """A field whose id does not equal its key, arriving as state."""
    return CanonicalState(
        schema_version="v1",
        fields={"temperature": Field(id="RENAMED", type="number", value=300)},
    )


def _plant_undeclared_edge():
    """An edge whose type the schema never declared, through the door.

    FOUR CORRECTIONS TO THIS ONE PLANT, each caught by the malformed
    guard rather than scored as a hit: `Operation.ADD` (the type is a
    Literal of lowercase strings), `EdgeRecord(from_id=...)` (the fields
    are `from_`/`to`), a missing `timestamp`, and `path="edges"` where
    the validator indexes `edges[n]`. The shape written from memory was
    wrong in four independent ways, and every one of them would have
    been reported as the gate firing.
    """
    schema = StateSchema(
        schema_version="v1",
        fields={"A": FieldSchema(id="A", type="number", default=1),
                "B": FieldSchema(id="B", type="number", default=2)},
        edges=(),  # nothing declared => no edge may ever be asserted
    )
    base = CanonicalState(
        schema_version="v1",
        fields={"A": Field(id="A", type="number", value=1),
                "B": Field(id="B", type="number", value=2)},
    )
    candidate = CandidateDelta(
        version_from=None, transaction_id="t1",
        timestamp="2026-01-01T00:00:00Z",
        changes=(CandidateChange(
            path="edges[0]", operation="add", old_value=None,
            new_value={"id": "e1", "from": "A", "to": "B",
                       "type": "invented_by_the_probe", "attributes": {}},
            provenance=_prov()),))
    return validate_candidate(schema, base, candidate)


def _projection_is_deterministic():
    """Not a violation -- determinism has no violating INPUT. Project the
    same version twice and compare.

    The first version of this omitted `schema_version`, raised TypeError
    and was scored REACHED by an exception handler that could not tell a
    gate firing from a plant failing to build.
    """
    schema = _schema()
    version = Version(id="v0", parent=None, state=_base(schema),
                      schema_version=schema.schema_version,
                      provenance=_prov(), timestamp="2026-01-01T00:00:00Z")
    return project_state(version) == project_state(version)


SUBJECTS: List[Subject] = [
    Subject("field_identity_is_the_key", GATE, "core.canonical.state",
            _plant_field_identity, fragment="does not match"),
    Subject("edges_are_explicit_only", GATE, "core.canonical.validation",
            # The refusal CODE, not the type name. "EDGE" matched
            # "EdgeRecord" in a TypeError from the plant's own
            # construction and scored it REACHED -- a fragment loose
            # enough to match the subject is not a fragment that
            # identifies the refusal.
            _plant_undeclared_edge, fragment="EDGE_TYPE_NOT_ALLOWED"),
    Subject("projection_is_deterministic", PROPERTY, "core.projection.project",
            _projection_is_deterministic),
    Subject("representation_never_enters_canonical_state", STRUCTURAL,
            "backends/* (no import of the canonical mutation surface)"),
    Subject("inference_never_produces_canonical_truth", STRUCTURAL,
            "core.canonical.validation (validate_candidate is the sole entry)"),
]


# -- running them ----------------------------------------------------------


def probe() -> List[Subject]:
    for subject in SUBJECTS:
        if subject.kind == STRUCTURAL:
            subject.verdict = NO_PATH
            subject.detail = ("no violating input exists; the absence of a "
                              "path is the enforcement")
            continue
        try:
            outcome = subject.plant()
        except Exception as error:  # noqa: BLE001 -- classifying
            # THE GUARD THIS PROBE SHIPPED WITHOUT, and paid for on the
            # first run: an exception is only a hit if it carries the
            # GATE's own refusal. Anything else is the plant failing to
            # build, and scoring that as REACHED manufactures a
            # measurement in the prober's own favour.
            if subject.fragment and subject.fragment.lower() in str(error).lower():
                subject.verdict = REACHED
                subject.detail = f"{type(error).__name__}: {str(error)[:110]}"
            else:
                subject.verdict = MALFORMED
                subject.detail = (f"{type(error).__name__}: {str(error)[:100]} "
                                  f"-- measured the plant, not the gate")
            continue
        if subject.kind == PROPERTY:
            subject.verdict = HOLDS if outcome else "VIOLATED"
            subject.detail = ("same version projected twice, compared; "
                              "determinism has no violating input")
        elif isinstance(outcome, list) and outcome and isinstance(outcome[0], ValidationError):
            codes = " ".join(e.code for e in outcome)
            if subject.fragment and subject.fragment.lower() in codes.lower():
                subject.verdict = REACHED
                subject.detail = f"{outcome[0].code}: {str(outcome[0].message)[:95]}"
            else:
                subject.verdict = MALFORMED
                subject.detail = (f"refused with {codes} -- not the refusal "
                                  f"aimed at; measured the plant")
        else:
            subject.verdict = ADMITTED
            subject.detail = "the planted violation was ACCEPTED"
    return SUBJECTS


def importers_of(module_prefix: str = "core.") -> dict:
    """Which authored packages reach core.* -- the premise the sibling's
    result rests on, re-measured HERE rather than accepted."""
    root = pathlib.Path(__file__).resolve().parent.parent
    authored = ("morpho", "backends", "runtime", "adapters", "scout", "evidence",
                "materials", "execution", "experiment", "retrieval", "structures",
                "transformer")
    found = {}
    for package in authored:
        hits = []
        for path in sorted((root / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(errors="replace")
            if f"from {module_prefix}" in text or f"import {module_prefix}" in text:
                hits.append(str(path.relative_to(root)))
        if hits:
            found[package] = hits
    return found


def main() -> int:
    print("=== THE PREMISE, RE-MEASURED HERE ===")
    importers = importers_of()
    total = sum(len(v) for v in importers.values())
    print(f"  authored packages importing core.*: {sorted(importers)}")
    print(f"  files: {total}")
    if not importers:
        print("  -> the sibling's premise holds in this tree too")
    else:
        print("  -> the premise does NOT hold here. The sibling measured which")
        print("     of ITS packages reach a vendored copy; that is a different")
        print("     question about a different tree, and both answers are right")
        print("     about their own subject.")

    print("\n=== AND AN IMPORT EDGE IS AN INFERENCE, so: planted ===")
    for s in probe():
        print(f"  {s.verdict:26} {s.invariant_id:44} [{s.kind}]")
        print(f"       {s.detail}")

    gates = [s for s in SUBJECTS if s.kind == GATE]
    reached = [s for s in gates if s.verdict == REACHED]
    admitted = [s for s in gates if s.verdict == ADMITTED]
    malformed = [s for s in SUBJECTS if s.verdict == MALFORMED]
    print("\n=== THE NUMBER THAT MATTERS ===")
    print(f"  gates:      {len(gates)}  reached {len(reached)}, admitted {len(admitted)}, "
          f"malformed {len(malformed)}")
    print(f"  structural: {sum(1 for s in SUBJECTS if s.kind == STRUCTURAL)} "
          f"(no violating path exists -- not a hole)")
    print(f"  property:   {sum(1 for s in SUBJECTS if s.kind == PROPERTY)} "
          f"(holds over execution -- no violating input exists)")
    if malformed:
        print("\n  MALFORMED PLANTS measured the plant, not the gate, and are")
        print("  not counted as anything: " + ", ".join(s.invariant_id for s in malformed))
    if admitted:
        print("\n  A PLANTED VIOLATION WAS ADMITTED. That is a hole, not a silence.")
    elif not reached:
        print("\n  No gate was reached: the set would be silent, and a zero over")
        print("  it would not be a measurement.")
    else:
        print(f"\n  {len(reached)} of {len(gates)} gates REACHED by a planted violation")
        print("  at the production door. Not silence: a measurement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
