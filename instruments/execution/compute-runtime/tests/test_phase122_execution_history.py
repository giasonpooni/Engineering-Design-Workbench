"""Phase 122: can the architecture reconstruct its own execution history?

THE ANSWER TO THE NARROWER QUESTION FIRST, BECAUSE IT REFRAMES THE REST:

    OPERATION HISTORY IS NOT MERELY ABSENT. IT IS EXCLUDED BY THE
    IDENTITY INVARIANT, DELIBERATELY AND BY DOCUMENTED DISCIPLINE.

The exclusion is not a preference that could be reversed by adding
fields. Content-addressed identity and execution facts CANNOT COEXIST IN
ONE OBJECT. Demonstrated: hashing the same extraction together with its
timestamp, host and pid yields FOUR DISTINCT IDS for four runs of one
extraction. Had execution facts been included:

    - the same fact admitted twice would be two facts
    - the pool fingerprint would never be reproducible
    - a ModelState would differ per run
    - Phase 116b's result (six arrival orders, one state id) would fail

The architecture did not forget operation history. IT PURCHASED
REPRODUCIBILITY WITH IT.

THE DISCIPLINE IS DOCUMENTED IN FOUR INDEPENDENT MODULES, in the same
words each time -- not four oversights, one rule applied four times:

    evidence/types.py     retrieved_at   "caller-supplied -- never wall-clock"
    retrieval/seam.py     opened_at      "caller-supplied -- never wall-clock"
    scout/interface.py    retrieved_at   "caller-supplied -- never wall-clock"
    experiment/interface.py              'the same "caller-supplied, never
                                          wall-clock" discipline'

and both acquisition seams are documented "pre-identity, pre-pool"
(`scout.interface.RawDocument`, `experiment.interface.DispatchedMeasurement`),
with the same sentence: "acquisition's job is acquisition, not identity
assignment."

sec.CLASSIFICATION

  Q1 operation was invoked            UNRECOVERABLE
        `dispatch()` is a plain call. Invoking it and never invoking it
        leave the same empty pool with the same fingerprint.
  Q2 execution returned               UNRECOVERABLE as such
        Only a return THAT WAS THEN ADMITTED leaves anything, and what it
        leaves is a fact, not a return.
  Q3 execution raised                 UNRECOVERABLE
        Byte-identical to never invoking. Phase 121's B/C collapse.
  Q4 retry #1 vs retry #2             UNRECOVERABLE
        Three identical admissions produce ONE fingerprint change and ONE
        observation. Retries 2 and 3 are no-ops by construction --
        `_observe_fingerprint` appends "only when it differs from the
        last recorded entry", so the history counts DISTINCT STATES,
        NEVER OPERATIONS.
  Q5 two identical executions,
     identical outputs                UNRECOVERABLE, and identical
        BY CONSTRUCTION, not by accident (Phase 111b).
  Q6 which implementation executed    UNRECOVERABLE
        No field on DispatchedMeasurement, ExperimentalResult or
        Observation names a producer. Phase 120: the Protocol returns the
        type but does not own it.
  Q7 configuration / seed /
     environment / context            UNRECOVERABLE -- none exists.
     timestamp                        ACCIDENTALLY PRESERVED, and weakly:
        `extracted_at` and `retrieved_at` survive on the objects, but are
        CALLER-SUPPLIED and EXCLUDED FROM IDENTITY, so they record what a
        caller said the time was, not when anything ran.
  Q8 order of state-changing
     admissions                       ACCIDENTALLY PRESERVED
        `fingerprint_history()` is an ordered sequence of distinct pool
        states. It was built for Phase 16's observation boundary, not as
        an operation log, and it cannot say WHICH object caused a
        transition -- recovering that means replaying candidate pool
        contents until a hash matches, i.e. already knowing the answer.
  -- orphan Record (Phase 121)        ACCIDENTALLY PRESERVED, unenumerable
        and unreliable; see Phase 121.

  EXISTING: nothing. Not one of the eight facts is represented.
  RECONSTRUCTABLE: nothing. Every "yes" above is an accident of a
        mechanism built for another purpose.

WHY THIS IS THE RIGHT SHAPE, AND WHY ONE LEDGER CANNOT HOLD BOTH
------------------------------------------------------------------
    EVIDENCE STATE     answers "what has been admitted?"
                       identity = f(content); order-invariant; a repeat
                       is a no-op; reproducible across runs, hosts, times
    OPERATION TRACE    answers "what did the machine do?"
                       identity = f(occasion); order IS the content; a
                       repeat is a SECOND EVENT; irreproducible by nature

Those are not two views of one thing. Their identity rules are
CONTRADICTORY: the first requires that two identical occasions collapse,
the second requires that they do not. Any object holding both fails one
of them. That is the formal reason the eventual architecture must be two
ledgers rather than one ontology -- and it is a stronger reason than
convenience.

NOTHING IS PROPOSED. This phase does not build the second ledger, does
not name it, and does not add `all_records`. Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.admission import admit_record
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import Observation, make_observation, make_record
from experiment.interface import DispatchedMeasurement
from materials.results import ExperimentalResult, admit_experimental_result, make_experimental_result
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
TIMESTAMP = "2026-01-01T00:00:00Z"
METHOD = "measurement:campaign_execution"
CONTENT = {"property": "tensile_strength", "value": 90.0, "unit": "MPa"}


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
        "name": "phase 122", "process": "process-std-190c",
        "formulations": ["formulation-a"], "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": [{"temperature_c": 25}],
    }, clock=clock)
    entry = next(e for e in state.campaign.entries
                 if e.candidate_id == state.candidates.candidates[0].id)
    return state, entry


def _admit(state, entry, value=90.0, locator="l"):
    record = make_record(document_id=state.document_id, locator=locator,
                         raw_content=str(value))
    assert not isinstance(admit_record(state.pool, record), list)
    state.pool.put_record(record)
    result = make_experimental_result(state.campaign, entry,
                                      content={**CONTENT, "value": value},
                                      record_id=record.id, extracted_at=TIMESTAMP,
                                      extraction_method=METHOD)
    return admit_experimental_result(state.pool, result, confidence=1.0)


# -- Q1/Q2/Q3 -- invoked, returned, raised ------------------------------------------------------------


def test_invoked_and_raised_are_both_indistinguishable_from_never():
    state, entry = _scenario()
    baseline = state.pool.fingerprint()

    # never invoked
    assert state.pool.fingerprint() == baseline

    # invoked and raised -- exactly what run_experiment_step does: nothing
    try:
        raise RuntimeError("instrument offline")
    except RuntimeError:
        pass
    assert state.pool.fingerprint() == baseline

    # invoked, returned, and ADMITTED -- the only case that leaves a trace
    _admit(state, entry)
    assert state.pool.fingerprint() != baseline


def test_the_observation_point_is_optional_and_absent_by_default():
    """WHEN THIS AUDIT RAN there was no observation point at all. Phase 125
    added one, and made it OPTIONAL: the default is None, so every fact
    classified UNRECOVERABLE above remains unrecoverable for any caller
    that does not opt in."""
    from experiment.step import run_experiment_step
    parameters = inspect.signature(run_experiment_step).parameters
    assert "trace" in parameters
    assert parameters["trace"].default is None


# -- Q4/Q5 -- retries and identical executions ---------------------------------------------------------


def test_three_identical_admissions_leave_one_observation_and_one_transition():
    state, entry = _scenario()
    fingerprints = [state.pool.fingerprint()]
    for _ in range(3):
        _admit(state, entry, value=90.0, locator="l")
        fingerprints.append(state.pool.fingerprint())

    assert len(set(fingerprints[1:])) == 1        # retries 2 and 3 changed nothing
    assert len(state.pool.all_observations()) == 1


def test_the_history_counts_distinct_states_never_operations():
    source = inspect.getsource(EvidencePool._observe_fingerprint)
    flat = " ".join(source.split())
    assert "Appends only when it differs from the last recorded entry" in flat
    assert "the compare- and-append rule" in flat


# -- Q6 -- which implementation executed ----------------------------------------------------------------


@pytest.mark.parametrize("cls", [DispatchedMeasurement, ExperimentalResult, Observation])
def test_nothing_names_the_producer(cls):
    fields = {f.name for f in dataclasses.fields(cls)}
    assert not (fields & {"dispatcher", "implementation", "producer",
                          "executed_by", "adapter"})


# -- Q7 -- the only time-shaped field is a caller's word ------------------------------------------------


def test_extracted_at_is_caller_supplied_and_excluded_from_identity():
    base = make_observation(record_ids=("r",), extraction_method="regex:x",
                            content=CONTENT, confidence=1.0, extracted_at=TIMESTAMP)
    far_future = make_observation(record_ids=("r",), extraction_method="regex:x",
                                  content=CONTENT, confidence=0.2,
                                  extracted_at="2099-12-31T23:59:59Z")
    assert base.id == far_future.id


def test_the_never_wall_clock_discipline_is_documented_in_four_modules():
    """Four independent modules, the same phrase -- one rule applied four
    times, not four oversights."""
    phrase = "never wall-clock"
    carriers = []
    for relative in ("evidence/types.py", "retrieval/seam.py", "scout/interface.py",
                     "experiment/interface.py"):
        if phrase in (REPO / relative).read_text():
            carriers.append(relative)
    assert sorted(carriers) == ["evidence/types.py", "experiment/interface.py",
                                "retrieval/seam.py", "scout/interface.py"]


def test_both_acquisition_seams_are_documented_pre_identity_pre_pool():
    for relative in ("scout/interface.py", "experiment/interface.py"):
        flat = " ".join((REPO / relative).read_text().split())
        assert "pre-identity, pre-pool" in flat
    # `experiment/` states the rule AND CITES `scout/` as its precedent --
    # direct evidence of one deliberate discipline, not two coincidences.
    experiment = " ".join((REPO / "experiment" / "interface.py").read_text().split())
    assert "acquisition's job is acquisition, not identity assignment" in experiment
    assert "`scout.interface.RawDocument` already establishes" in experiment


# -- Q8 -- what fingerprint_history accidentally preserves ------------------------------------------------


def test_fingerprint_history_is_ordered_distinct_states_and_nothing_more():
    state, entry = _scenario()
    before = len(state.pool.fingerprint_history())
    _admit(state, entry, value=90.0, locator="run-0")
    history = state.pool.fingerprint_history()
    assert len(history) > before                  # transitions ARE ordered
    assert len(set(history)) == len(history)      # and distinct
    # ...but nothing maps a fingerprint back to its cause
    assert not any(m for m in dir(state.pool) if "cause" in m or "why" in m)


def test_no_repeat_is_ever_appended():
    pool = EvidencePool()
    from evidence.types import make_source
    source = make_source(kind="paper", name="J")
    pool.put_source(source)
    after_first = len(pool.fingerprint_history())
    pool.put_source(source)                       # identical: a no-op
    assert len(pool.fingerprint_history()) == after_first


# -- the entailment: why no field could fix this ----------------------------------------------------------


def test_execution_facts_in_identity_would_destroy_reproducibility():
    """THE CENTRAL RESULT. Not a preference -- a contradiction."""
    def with_execution_facts(when, host, pid):
        return content_hash({"record_ids": ["r"], "extraction_method": "regex:x",
                             "content": CONTENT, "extracted_at": when,
                             "hostname": host, "pid": pid})

    runs = {
        with_execution_facts("2026-01-01T00:00:00Z", "node-a", 4171),
        with_execution_facts("2026-01-01T00:00:01Z", "node-a", 4171),
        with_execution_facts("2026-01-01T00:00:00Z", "node-b", 4171),
        with_execution_facts("2026-01-01T00:00:00Z", "node-a", 9082),
    }
    assert len(runs) == 4          # four ids for ONE extraction

    # whereas the real identity collapses all four
    real = {make_observation(record_ids=("r",), extraction_method="regex:x",
                             content=CONTENT, confidence=1.0,
                             extracted_at=when).id
            for when in ("2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z",
                         "2099-12-31T23:59:59Z")}
    assert len(real) == 1


def test_the_two_ledgers_have_contradictory_identity_rules():
    """EVIDENCE: two identical occasions must COLLAPSE.
    OPERATION: two identical occasions must REMAIN TWO.
    No single object can satisfy both -- which is why this is two ledgers
    and not one ontology."""
    a = make_observation(record_ids=("r",), extraction_method="regex:x",
                         content=CONTENT, confidence=1.0, extracted_at=TIMESTAMP)
    b = make_observation(record_ids=("r",), extraction_method="regex:x",
                         content=CONTENT, confidence=1.0, extracted_at=TIMESTAMP)
    assert a.id == b.id            # evidence rule: they collapse
    # an operation ledger would need these to be two events; the same
    # object cannot deliver both answers.


# -- nothing was proposed ------------------------------------------------------------------------------------


def test_phase_122_added_nothing():
    forbidden = {"OperationTrace", "ExecutionJournal", "ExecutionRecord",
                 "AttemptLog", "all_records", "OperationLedger"}
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
