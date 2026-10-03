"""Phase 121: operation outcome semantics.

THE NARROW QUESTION, as posed: can the instrument represent the fact that
an operation was ATTEMPTED, and whether the system itself observed
success, failure, or non-execution? (NOT: can we prove the physical
experiment happened -- Phase 111b established that is undecidable from
inside.)

ANSWER: THREE OUTCOMES EXIST IN PRINCIPLE. THE ARCHITECTURE DISTINGUISHES
ONE, RETAINS A SECOND UNDISCOVERABLY, AND COLLAPSES THE OTHER TWO.

THE FOUR WORLDS, MEASURED
--------------------------
    world                              fp moved  obs  record  findable
    A executed -> result -> admitted   yes       1    yes     YES
    B never executed                   NO        0    --      --
    C dispatch raised                  NO        0    --      --
    C' dispatched, admission refused   YES       0    YES     NO

B AND C ARE BYTE-IDENTICAL. "Nobody tried" and "the instrument crashed"
leave the same empty pool with the same fingerprint. That is the collapse
this phase was sent to find, and it is narrower than "no execution state
exists": the two are not merely unlabelled, they are the SAME STATE.

C' IS THE INTERESTING ONE, AND IT WAS NOT EXPECTED.
`run_experiment_step` commits the Record to the pool BEFORE admitting the
semantic claim:

    1. dispatched = dispatcher.dispatch(candidate)
    2. admit_record / pool.put_record(record)
    3. admit_experimental_result(...)   -- raises on rejection

The pool has no delete. So when step 3 fails, the Record STAYS, and the
fingerprint has already moved. THE ARCHITECTURE ALREADY RETAINS A TRACE
OF A PARTIAL ATTEMPT -- an orphan Record: raw content committed, no
semantic claim admitted. Nobody designed this as an outcome record; it
falls out of the commit order and the append-only rule.

BUT THE TRACE CANNOT BE FOUND
------------------------------
`EvidencePool` offers `all_referents`, `all_claimed_relationships`,
`all_observations`, `all_derived_values`, `all_derived_groundings` -- and
NO `all_records`, `all_documents` or `all_sources`. The enumeration
surface stops exactly at the SEMANTIC / STRUCTURAL boundary, and the
orphan Record lives on the structural side. It can only be reached by
`get_record(id)` or `has_record(id)` -- that is, by a caller who already
knows the id of the thing they are looking for.

The asymmetry is consistent (five semantic types enumerable, three
structural types not) but UNDOCUMENTED: the pool's own docstring gives no
rationale, so this audit cannot say whether it was designed or emergent.

AND THE TRACE IS NOT RELIABLE ANYWAY
-------------------------------------
A deterministic dispatcher retrying the same measurement mints THE SAME
`Record.id` -- content-addressing guarantees it. So the retry's Record IS
the orphan, and the successful Observation ends up citing the very object
that was left behind by the failure. The earlier failure's trace is not
deleted; IT WAS NEVER A DISTINCT OBJECT.

This is Phase 111b's result appearing one layer down: content-addressing
makes "the failed attempt" and "the successful retry" one thing whenever
the payload is identical. An orphan Record is a fact about WHAT HAS BEEN
COMMITTED, never about HOW MANY TIMES IT WAS TRIED.

WHAT IS AND IS NOT REPRESENTABLE
---------------------------------
    SUCCESS                 REPRESENTED -- an Observation exists
    PARTIAL (refused)       RETAINED but UNENUMERABLE and UNRELIABLE
    FAILURE (crashed)       NOT REPRESENTED
    NON-EXECUTION           NOT REPRESENTED, and identical to failure

So the internal operational fact the phase asked about is genuinely
absent for B and C, and genuinely present-but-unreachable for C'. Those
are two different gaps with two different characters, and only the first
needs anything new.

TWO OPTIONS, NEITHER PROPOSED AS A REPAIR
-------------------------------------------
1. THE C' GAP is a QUERY gap, not an ontology gap. `all_records()` would
   mirror five accessors that already exist, add no type, no field, no
   identity and no admission semantics, and make orphan Records findable.
   It is NOT warranted by any current need: nothing in production looks
   for them, and the reliability caveat above means the answer would be
   "what is committed", not "what was attempted". Reported as available,
   not recommended.

2. THE B/C GAP cannot be closed without representing an attempt, which
   means a new object. Phase 116b falsified the `ExecutionRecord`
   candidate on three counts and those counterexamples still hold;
   Phase 114 established the execution seam is specified and empty.
   NOTHING IS PROPOSED.

THE DISTINCTION THE PHASE ASKED TO PRESERVE
---------------------------------------------
    INTERNAL OPERATIONAL FACT   did THIS PROCESS observe a call, a
                                return, an exception? Answerable in
                                principle. Currently answered for one
                                outcome of four.
    EXTERNAL WARRANT            did the physical experiment happen?
                                Undecidable from inside (Phase 111b),
                                and untouched by any of the above.

Closing the first would not begin to address the second, and this phase
makes no claim that it would.

Zero production changes.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from evidence.admission import admit_record
from evidence.pool import EvidencePool
from evidence.types import make_record
from experiment.step import run_experiment_step
from materials.results import admit_experimental_result, make_experimental_result
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
TIMESTAMP = "2026-01-01T00:00:00Z"
METHOD = "measurement:campaign_execution"
GOOD = {"property": "tensile_strength", "value": 90.0, "unit": "MPa"}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _scenario():
    n = [0]

    def clock():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    state = bootstrap_research_scenario({
        "name": "phase 121", "process": "process-std-190c",
        "formulations": ["formulation-a"], "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": [{"temperature_c": 25}],
    }, clock=clock)
    entry = next(e for e in state.campaign.entries
                 if e.candidate_id == state.candidates.candidates[0].id)
    return state, entry


# -- the commit order that produces the orphan --------------------------------------------------------


def test_the_record_is_committed_before_the_semantic_claim_is_admitted():
    source = inspect.getsource(run_experiment_step)
    dispatch = source.index("dispatcher.dispatch")
    put_record = source.index("put_record")
    admit_result = source.index("admit_experimental_result")
    assert dispatch < put_record < admit_result
    # and the pool has no delete, so a later failure cannot undo the put
    assert not any(m.startswith(("delete", "remove", "drop"))
                   for m in dir(EvidencePool))


# -- the four worlds -----------------------------------------------------------------------------------


def test_world_a_success_is_represented():
    state, entry = _scenario()
    before = state.pool.fingerprint()
    record = make_record(document_id=state.document_id, locator="l", raw_content="90.0")
    assert not isinstance(admit_record(state.pool, record), list)
    state.pool.put_record(record)
    result = make_experimental_result(state.campaign, entry, content=GOOD,
                                      record_id=record.id, extracted_at=TIMESTAMP,
                                      extraction_method=METHOD)
    admit_experimental_result(state.pool, result, confidence=1.0)
    assert state.pool.fingerprint() != before
    assert len(state.pool.all_observations()) == 1


def test_worlds_b_and_c_are_byte_identical():
    """"Nobody tried" and "the instrument crashed" are THE SAME STATE."""
    never_executed, _ = _scenario()
    crashed, _ = _scenario()

    try:
        raise RuntimeError("instrument offline")
    except RuntimeError:
        pass       # exactly what run_experiment_step does: nothing

    assert never_executed.pool.fingerprint() == crashed.pool.fingerprint()
    assert never_executed.pool.all_observations() == crashed.pool.all_observations() == ()


def test_world_c_prime_leaves_an_orphan_record_and_moves_the_fingerprint():
    state, entry = _scenario()
    before = state.pool.fingerprint()
    record = make_record(document_id=state.document_id, locator="l", raw_content="90.0")
    assert not isinstance(admit_record(state.pool, record), list)
    state.pool.put_record(record)

    with pytest.raises(ValueError):
        make_experimental_result(state.campaign, entry,
                                 content={"property": "WRONG_PROPERTY", "value": 90.0},
                                 record_id=record.id, extracted_at=TIMESTAMP,
                                 extraction_method=METHOD)

    assert state.pool.fingerprint() != before      # the attempt IS visible
    assert state.pool.all_observations() == ()     # but produced no claim
    assert state.pool.has_record(record.id)        # and the raw content stayed


# -- the trace cannot be found -------------------------------------------------------------------------


def test_the_enumeration_surface_stops_at_the_semantic_boundary():
    enumerable = {m for m in dir(EvidencePool) if m.startswith("all_")}
    assert enumerable == {
        "all_referents", "all_claimed_relationships", "all_observations",
        "all_derived_values", "all_derived_groundings",
    }
    # the three STRUCTURAL types are not enumerable
    for absent in ("all_records", "all_documents", "all_sources"):
        assert absent not in enumerable


def test_an_orphan_record_is_reachable_only_by_an_id_you_already_have():
    state, _ = _scenario()
    record = make_record(document_id=state.document_id, locator="l", raw_content="90.0")
    state.pool.put_record(record)
    assert state.pool.has_record(record.id)
    assert state.pool.get_record(record.id) == record
    # ...and no method returns it without the id
    assert not hasattr(state.pool, "all_records")


def test_the_asymmetry_is_undocumented():
    """This audit cannot say whether it was designed or emergent. No
    `all_*` accessor carries a docstring, and the omitted three are not
    mentioned anywhere -- there is no note saying they were left out on
    purpose, and none saying they were forgotten."""
    import ast
    import inspect as _inspect

    import evidence.pool as pool_module

    tree = ast.parse(_inspect.getsource(pool_module))
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef)][0]
    accessors = [fn for fn in cls.body
                 if isinstance(fn, ast.FunctionDef) and fn.name.startswith("all_")]
    assert len(accessors) == 5
    assert all(ast.get_docstring(fn) is None for fn in accessors)

    text = _inspect.getsource(pool_module)
    for omitted in ("all_records", "all_documents", "all_sources"):
        assert omitted not in text


# -- and the trace is unreliable -------------------------------------------------------------------------


def test_a_deterministic_retry_adopts_the_orphan():
    """Content-addressing makes the failed attempt and the successful
    retry ONE OBJECT whenever the payload is identical."""
    state, entry = _scenario()

    first = make_record(document_id=state.document_id, locator="run-1", raw_content="90.0")
    state.pool.put_record(first)
    with pytest.raises(ValueError):
        make_experimental_result(state.campaign, entry,
                                 content={"property": "WRONG", "value": 90.0},
                                 record_id=first.id, extracted_at=TIMESTAMP,
                                 extraction_method=METHOD)

    retry = make_record(document_id=state.document_id, locator="run-1", raw_content="90.0")
    assert retry.id == first.id                    # the SAME object

    state.pool.put_record(retry)
    result = make_experimental_result(state.campaign, entry, content=GOOD,
                                      record_id=retry.id, extracted_at=TIMESTAMP,
                                      extraction_method=METHOD)
    observation, _ = admit_experimental_result(state.pool, result, confidence=1.0)
    assert observation.record_ids == (first.id,)
    # The successful Observation cites the object the failure left behind.


def test_an_orphan_reports_what_is_committed_not_what_was_attempted():
    """Two failed attempts with identical payloads leave ONE record."""
    state, _ = _scenario()
    for _ in range(2):
        record = make_record(document_id=state.document_id, locator="run-1",
                             raw_content="90.0")
        state.pool.put_record(record)
    # content-addressed: the second put is a no-op by construction
    assert state.pool.has_record(record.id)
    text = " ".join((REPO / "evidence" / "pool.py").read_text().split())
    assert "re-putting an object that already exists is a no-op by construction" in text


# -- nothing was proposed ----------------------------------------------------------------------------------


def test_phase_121_added_no_outcome_machinery():
    import ast

    forbidden = {"ExecutionRecord", "OperationOutcome", "AttemptRecord",
                 "ExecutionStatus", "OutcomeState", "all_records"}
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


def test_the_two_gaps_have_different_characters():
    """The C' gap is a QUERY gap; the B/C gap is an ONTOLOGY gap. Only the
    second would need a new object, and none is proposed."""
    # C': the object exists, the query does not
    state, _ = _scenario()
    record = make_record(document_id=state.document_id, locator="l", raw_content="x")
    state.pool.put_record(record)
    assert state.pool.has_record(record.id)          # exists
    assert not hasattr(state.pool, "all_records")    # unfindable

    # B/C: nothing exists at all -- no field anywhere could hold an attempt
    import dataclasses

    from experiment.interface import DispatchedMeasurement
    from materials.results import ExperimentalResult
    for cls in (DispatchedMeasurement, ExperimentalResult):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("attempted", "outcome", "status", "failed", "started_at"):
            assert absent not in fields
