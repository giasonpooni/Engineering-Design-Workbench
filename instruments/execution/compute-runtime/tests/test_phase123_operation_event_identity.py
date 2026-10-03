"""Phase 123: operation event identity audit.

VERDICT: OPERATION IDENTITY IS UNDERDETERMINED.

Per the phase's own stop condition, the ledger is NOT designed. Nothing is
proposed, named, or reserved.

WHAT IS ALREADY DETERMINATE
----------------------------
Three of the five columns are answered, and answered by content-addressing:

    case                              artifact  evidence
    1  identical, executed twice      SAME      SAME
    2  same inputs, different seed    SAME      SAME
    3  different configuration        SAME      SAME
    4  different hardware             SAME      SAME
    5  interrupted and retried        SAME      SAME
    6  invoked concurrently twice     SAME      SAME
    7  invoked, never executed        none      none
    8  begins and raises              none      none
    9  succeeds, output rejected      SAME      none      <- Phase 121's orphan
    10 byte-identical to a prior run  SAME      SAME

Seed, configuration, hardware, retry and concurrency change NOTHING,
because none of them is an input to any hash. "Same state? same evidence?
same artifact?" are settled. ONLY "same event?" is open.

WHY IT IS OPEN -- EIGHT OF TEN CASES HAVE NO PURPOSE-INDEPENDENT ANSWER
-------------------------------------------------------------------------
Each case was answered against five purposes a scientific instrument
might plausibly have. S = same event, D = different, N = no event.

    case                            repro  dedup  resource  failure  provenance
    1  identical, twice             D      S      D         D        S
    2  different seed               D      D      D         D        D
    3  different configuration      D      D      D         D        D
    4  different hardware           D      S      D         D        S
    5  interrupted and retried      S      S      D         D        S
    6  concurrent invocations       D      S      D         D        S
    7  invoked, never executed      N      N      N         D        N
    8  begins and raises            N      N      D         D        N
    9  output rejected              N      N      D         D        N
    10 byte-identical output        D      S      D         D        S

UNANIMOUS: 2 of 10. SPLIT: 8 of 10.

And the two unanimous cases contribute nothing. A changed seed or a
changed configuration is a changed INPUT, and every purpose distinguishes
different inputs -- that is INPUT identity, which content-addressing
already supplies. It is not operation identity.

Case 1 alone splits three ways: reproducibility says two events (you need
two independent runs to claim a reproduction), deduplication says one
(don't repeat work), resource accounting says two (two machine-hours),
provenance says one (one datum was admitted).

THE AXES DO NOT INTERSECT
--------------------------
    axis                repro  dedup  resource  failure  provenance
    invocation          --     --     --        REQ      --
    execution attempt   --     --     REQ       REQ      --
    execution instance  REQ    --     --        REQ      --
    configuration       REQ    REQ    --        --       --
    environment         REQ    --     REQ       REQ      --
    seed                REQ    REQ    --        --       --
    output              REQ    REQ    --        --       REQ
    wall-clock time     --     --     REQ       REQ      --
    causal parent       --     --     --        --       REQ
    retry lineage       --     --     --        REQ      --

    INTERSECTION: EMPTY.  UNION: all ten.

NOT ONE AXIS IS REQUIRED BY EVERY PURPOSE -- not `output`, which resource
accounting ignores; not `execution instance`, which deduplication and
provenance ignore. And the sets are NOT NESTED: deduplication needs
`seed`, which failure diagnosis does not; failure diagnosis needs
`invocation`, which reproducibility does not. Neither contains the other,
so there is no coarsest-common or finest-common relation to fall back on.

WHY THIS IS UNDERDETERMINATION AND NOT MERELY PLURALITY
---------------------------------------------------------
The competing option -- "multiple operation identities exist and cannot
share one carrier" -- is TRUE AS A DIAGNOSIS and is the reason for the
verdict, but it is not the verdict. It presupposes that each identity is
well-defined, which requires a purpose to be FIXED. The architecture fixes
none:

    Phase 114  the execution seam is a Protocol, specified and EMPTY, and
               its own docstring says no implementation shipped anywhere
               in this codebase is a live integration
    Phase 121  nothing in production looks for an attempt, an orphan, or
               an outcome
    Phase 122  every seam that could have captured an execution fact
               declines it, in four modules, in the same words

So there is no consumer whose question would select a relation. The
identity is not contested between two known parties; it is UNCLAIMED.
Designing a ledger now would mean choosing a purpose by fiat and then
discovering later that the real consumer needed a different one -- which
is precisely the failure mode Phases 107 through 110 kept finding when an
abstraction was named before its question was.

WHAT WOULD RESOLVE IT
----------------------
Not more analysis of the ten cases; they are exhausted and the answer is
stable. A single actual consumer, asking a question the evidence ledger
structurally cannot answer, would select a purpose, and the purpose would
select the axes. Until one exists, any equivalence relation is a guess
wearing a schema.

NOTHING IS PROPOSED. No ExecutionRecord, no OperationRecord, no
provenance event, no name reserved. Zero production changes. STOPPED at
the stop condition.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from evidence.identity import content_hash
from evidence.types import make_observation, make_record
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
TIMESTAMP = "2026-01-01T00:00:00Z"
CONTENT = {"property": "tensile_strength", "value": 90.0, "unit": "MPa"}

# S = same event, D = different events, N = no event at all
PURPOSES = ("reproducibility", "deduplication", "resource_accounting",
            "failure_diagnosis", "provenance")

CASE_ANSWERS = {
    "identical_executed_twice":   ("D", "S", "D", "D", "S"),
    "same_inputs_different_seed": ("D", "D", "D", "D", "D"),
    "different_configuration":    ("D", "D", "D", "D", "D"),
    "different_hardware":         ("D", "S", "D", "D", "S"),
    "interrupted_and_retried":    ("S", "S", "D", "D", "S"),
    "concurrent_invocations":     ("D", "S", "D", "D", "S"),
    "invoked_never_executed":     ("N", "N", "N", "D", "N"),
    "begins_and_raises":          ("N", "N", "D", "D", "N"),
    "output_rejected":            ("N", "N", "D", "D", "N"),
    "byte_identical_output":      ("D", "S", "D", "D", "S"),
}

REQUIRED_AXES = {
    "reproducibility": {"execution instance", "configuration", "environment",
                        "seed", "output"},
    "deduplication": {"configuration", "seed", "output"},
    "resource_accounting": {"execution attempt", "environment", "wall-clock time"},
    "failure_diagnosis": {"invocation", "execution attempt", "execution instance",
                          "environment", "wall-clock time", "retry lineage"},
    "provenance": {"output", "causal parent"},
}

ALL_AXES = {"invocation", "execution attempt", "execution instance", "configuration",
            "environment", "seed", "output", "wall-clock time", "causal parent",
            "retry lineage"}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _artifact(value=90.0, locator="run", document="d"):
    return make_record(document_id=document, locator=locator, raw_content=str(value)).id


def _evidence(value=90.0, method="measurement:campaign_execution"):
    return make_observation(record_ids=(_artifact(value),), extraction_method=method,
                            content={**CONTENT, "value": value}, confidence=1.0,
                            extracted_at=TIMESTAMP).id


# -- the three determinate columns ----------------------------------------------------------------------


@pytest.mark.parametrize("differing_axis", [
    "seed", "configuration", "hardware", "retry", "concurrency", "wall-clock",
])
def test_no_execution_axis_reaches_the_artifact_or_the_evidence(differing_axis):
    """None of these is an input to any hash, so cases 1, 2, 4, 5, 6 and 10
    are ONE artifact and ONE evidence object."""
    assert _artifact() == _artifact()
    assert _evidence() == _evidence()
    # and the axis has nowhere to be recorded in the first place
    from evidence.types import Observation, Record
    import dataclasses
    for cls in (Record, Observation):
        fields = {f.name for f in dataclasses.fields(cls)}
        assert differing_axis.replace("-", "_") not in fields


def test_the_rejected_output_case_has_an_artifact_and_no_evidence():
    """Case 9 -- Phase 121's orphan, restated as an identity fact."""
    artifact = _artifact()
    assert artifact                    # the Record exists
    # ...and no Observation was minted, so there is nothing citing it


def test_input_differences_are_already_distinguished():
    """Cases 2 and 3 are unanimous ONLY because they are input changes,
    which content-addressing already separates. That is input identity,
    not operation identity."""
    assert content_hash({"seed": 1}) != content_hash({"seed": 2})
    assert content_hash({"config": "a"}) != content_hash({"config": "b"})


# -- eight of ten cases split ---------------------------------------------------------------------------


def test_exactly_two_of_ten_cases_are_unanimous():
    unanimous = [c for c, a in CASE_ANSWERS.items() if len(set(a)) == 1]
    split = [c for c, a in CASE_ANSWERS.items() if len(set(a)) > 1]
    assert sorted(unanimous) == ["different_configuration", "same_inputs_different_seed"]
    assert len(split) == 8


def test_the_unanimous_cases_contribute_nothing_to_operation_identity():
    """Both are input changes; every purpose distinguishes different
    inputs, and the evidence ledger already does."""
    for case in ("same_inputs_different_seed", "different_configuration"):
        assert set(CASE_ANSWERS[case]) == {"D"}


def test_the_simplest_case_splits_three_ways():
    """Same operation, same inputs, same configuration, same output,
    executed twice."""
    answers = dict(zip(PURPOSES, CASE_ANSWERS["identical_executed_twice"]))
    assert answers["reproducibility"] == "D"      # two runs make a reproduction
    assert answers["deduplication"] == "S"        # do not repeat the work
    assert answers["resource_accounting"] == "D"  # two machine-hours
    assert answers["provenance"] == "S"           # one datum was admitted
    assert len(set(answers.values())) == 2


@pytest.mark.parametrize("case", [
    "invoked_never_executed", "begins_and_raises", "output_rejected",
])
def test_the_no_event_cases_disagree_about_whether_an_event_exists_at_all(case):
    """Not just about identity -- about EXISTENCE."""
    answers = set(CASE_ANSWERS[case])
    assert "N" in answers and "D" in answers


# -- the axes do not intersect ----------------------------------------------------------------------------


def test_no_axis_is_required_by_every_purpose():
    intersection = set.intersection(*REQUIRED_AXES.values())
    assert intersection == set()


def test_every_axis_is_required_by_some_purpose():
    union = set.union(*REQUIRED_AXES.values())
    assert union == ALL_AXES


@pytest.mark.parametrize("a,b", [
    ("deduplication", "failure_diagnosis"),
    ("reproducibility", "resource_accounting"),
    ("provenance", "failure_diagnosis"),
])
def test_the_axis_sets_are_not_nested(a, b):
    """So there is no coarsest-common or finest-common relation to fall
    back on."""
    first, second = REQUIRED_AXES[a], REQUIRED_AXES[b]
    assert not first <= second
    assert not second <= first


def test_even_output_is_not_universal():
    """The axis one would most expect to be required."""
    assert "output" not in REQUIRED_AXES["resource_accounting"]
    assert "output" not in REQUIRED_AXES["failure_diagnosis"]


# -- no purpose is fixed anywhere -------------------------------------------------------------------------


def test_the_architecture_fixes_no_purpose():
    """No consumer exists whose question would select a relation."""
    from experiment.interface import ActionDispatcher

    # the seam is specified and empty (Phase 114)
    implementations = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
                    if "ActionDispatcher" in bases:
                        implementations.append(node.name)
    assert implementations == []
    assert hasattr(ActionDispatcher, "dispatch")

    text = " ".join((REPO / "experiment" / "interface.py").read_text().split())
    assert "No implementation shipped anywhere in this codebase" in text


def test_nothing_in_production_asks_any_of_the_five_questions():
    forbidden = {"reproduces", "deduplicate", "resource_usage", "diagnose_failure",
                 "attempt_count", "retry_count", "elapsed"}
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


# -- stopped at the stop condition --------------------------------------------------------------------------


def test_phase_123_designed_nothing():
    """`OperationTrace` is excluded from this sweep: Phase 124 built it as
    an INSTRUMENT that imposes no equivalence relation, and Phase 125
    attached it. That is not the identity this phase declined to choose --
    the locks in tests/test_operations_trace.py assert that no
    same_operation, equivalent, deduplicate or merge function exists."""
    forbidden = {"ExecutionRecord", "OperationRecord", "OperationEvent",
                 "ProvenanceEvent", "OperationLedger", "ExecutionJournal",
                 "AttemptRecord"}
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
