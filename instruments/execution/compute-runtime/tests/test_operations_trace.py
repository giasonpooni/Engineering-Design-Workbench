"""Phase 124: the operation trace instrument.

Built to the Phase 124 spec sec.1-sec.4. It records execution occurrences
WITHOUT imposing an equivalence relation on them -- Phase 123 found that
relation underdetermined, and this instrument is what a future consumer's
question would be answered from, not the answer.

WHAT IT CLOSES, AND WHAT IT DOES NOT
-------------------------------------
Phase 121 found "never invoked" and "invoked and crashed" BYTE-IDENTICAL,
and Phase 122 found six of eight execution facts UNRECOVERABLE. Those are
INTERNAL OPERATIONAL FACTS, and they are now observable.

Phases 111/111b/119 are untouched. Recording that a call happened is not
a witness that anything real happened. The locks below assert both halves.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from operations.trace import (
    ALL_LIFECYCLE_STATES,
    FAILED,
    INVOKED,
    LEGAL_TRANSITIONS,
    NEVER_STARTED,
    REJECTED,
    STARTED,
    SUCCEEDED,
    TERMINAL_STATES,
    TERMINATED,
    LifecycleTransition,
    OperationOccurrence,
    OperationTrace,
)

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def trace():
    n = [0]

    def clock():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    return OperationTrace(clock=clock)


# -- 1. the seven recordable occurrences ---------------------------------------------------------------


def test_invocation_is_recordable(trace):
    occurrence = trace.invoke("dispatch", input_ref="cand-1")
    assert trace.state_of(occurrence) == INVOKED
    assert len(trace.occurrences()) == 1


def test_start_is_recordable(trace):
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    assert trace.state_of(occurrence) == STARTED


def test_successful_return_is_recordable(trace):
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    trace.succeeded(occurrence, output_ref="rec-1")
    assert trace.state_of(occurrence) == SUCCEEDED
    assert trace.transitions_of(occurrence)[-1].output_ref == "rec-1"


def test_failure_is_recordable_with_a_normalised_code(trace):
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    trace.failed(occurrence, failure_type="RuntimeError",
                 failure_code="INSTRUMENT_OFFLINE", detail="load frame not responding")
    last = trace.transitions_of(occurrence)[-1]
    assert (last.to_state, last.failure_type, last.failure_code) == (
        FAILED, "RuntimeError", "INSTRUMENT_OFFLINE")


def test_rejection_by_a_downstream_boundary_is_recordable(trace):
    """Phase 121's world C' -- previously an unenumerable, unreliable
    orphan Record -- turned from an accident into an observation."""
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    trace.succeeded(occurrence, output_ref="rec-1")
    trace.rejected(occurrence, failure_code="PROPERTY_MISMATCH")
    assert trace.state_of(occurrence) == REJECTED


def test_termination_without_a_result_is_recordable(trace):
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    trace.terminated(occurrence, detail="cancelled by operator")
    assert trace.state_of(occurrence) == TERMINATED


def test_a_retry_is_recorded_only_when_the_caller_supplies_it(trace):
    """Nothing is inferred. A retry the instrumentation cannot observe is
    two unrelated occurrences, which is the honest record."""
    first = trace.invoke("dispatch")
    trace.started(first)
    trace.failed(first, failure_type="TimeoutError")
    second = trace.invoke("dispatch", retry_of=first)
    assert trace.occurrences()[second].retry_of == first

    unlinked = trace.invoke("dispatch")
    assert trace.occurrences()[unlinked].retry_of is None


def test_a_lineage_that_was_not_observed_cannot_be_invented(trace):
    with pytest.raises(ValueError, match="never invents a lineage"):
        trace.invoke("dispatch", retry_of=999)
    with pytest.raises(ValueError, match="never invents a lineage"):
        trace.invoke("dispatch", parent=999)


# -- 2. occurrence identity preserves multiplicity ------------------------------------------------------


def test_identical_invocations_are_distinct_occurrences(trace):
    """THE POINT OF THE LEDGER. Same operation, same input, same output,
    same clock discipline -- still two occurrences."""
    first = trace.invoke("dispatch", input_ref="cand-1")
    trace.started(first)
    trace.succeeded(first, output_ref="rec-1")

    second = trace.invoke("dispatch", input_ref="cand-1")
    trace.started(second)
    trace.succeeded(second, output_ref="rec-1")

    assert first != second
    assert len(trace.occurrences()) == 2
    assert trace.state_of(first) == trace.state_of(second) == SUCCEEDED


def test_occurrence_identity_is_not_content_addressed():
    """Content-addressing would collapse exactly the multiplicity this
    ledger exists to preserve."""
    source = inspect.getsource(inspect.getmodule(OperationTrace))
    assert "content_hash" not in source
    assert "from evidence" not in source
    assert "import evidence" not in source


def _code_names(module):
    """Identifiers that are actually CODE. The module docstring says
    "NOT a UUID" and "put_*" in prose; prose is not machinery."""
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[0])
    return names


def test_occurrence_identity_is_not_a_uuid_or_a_timestamp():
    module = inspect.getmodule(OperationTrace)
    names = {n.lower() for n in _code_names(module)}
    assert "uuid" not in names and "uuid4" not in names
    # the sequence is len(self._occurrences) -- nothing else mints an id
    assert "occurrence = len(self._occurrences)" in inspect.getsource(module)


def test_two_traces_both_start_at_zero_and_make_no_cross_process_claim():
    """Stated plainly in the module docstring, and true."""
    a, b = OperationTrace(clock=lambda: "t"), OperationTrace(clock=lambda: "t")
    assert a.invoke("dispatch") == b.invoke("dispatch") == 0
    flat = " ".join(inspect.getsource(inspect.getmodule(OperationTrace)).split())
    assert "MEANINGFUL ONLY WITHIN ONE `OperationTrace`" in flat


# -- 3. facts, never interpretations --------------------------------------------------------------------


def test_no_field_can_hold_a_claim_about_the_external_world():
    for cls in (OperationOccurrence, LifecycleTransition):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("extraction_method", "confidence", "content", "value",
                       "measured", "observed", "verified", "witness"):
            assert absent not in fields


def test_the_trace_stores_a_reference_never_an_output_value():
    """So it can never become a second place where results live."""
    fields = {f.name for f in dataclasses.fields(LifecycleTransition)}
    assert "output_ref" in fields
    assert "output" not in fields and "result" not in fields


def test_the_module_cannot_reach_an_evidence_pool():
    names = _code_names(inspect.getmodule(OperationTrace))
    for absent in ("EvidencePool", "make_observation", "make_record", "content_hash"):
        assert absent not in names
    assert not any(n.startswith(("put_", "admit_")) for n in names)


def test_the_observed_versus_claimed_boundary_is_documented():
    flat = " ".join(inspect.getsource(inspect.getmodule(OperationTrace)).split())
    assert '"the dispatcher was called" is recordable' in flat
    assert '"the physical experiment occurred" is NOT' in flat


# -- 4. the lifecycle is an explicit state machine ------------------------------------------------------


def test_the_state_machine_is_written_down_once():
    assert set(LEGAL_TRANSITIONS) == set(ALL_LIFECYCLE_STATES)
    assert LEGAL_TRANSITIONS[INVOKED] == (STARTED, NEVER_STARTED)
    assert LEGAL_TRANSITIONS[STARTED] == (SUCCEEDED, FAILED, TERMINATED)
    assert LEGAL_TRANSITIONS[SUCCEEDED] == (REJECTED,)
    assert set(TERMINAL_STATES) == {NEVER_STARTED, FAILED, TERMINATED, REJECTED}


def test_state_is_expressed_as_transitions_not_a_mutable_field():
    for cls in (OperationOccurrence, LifecycleTransition):
        assert cls.__dataclass_params__.frozen
    assert "state" not in {f.name for f in dataclasses.fields(OperationOccurrence)}


@pytest.mark.parametrize("first,second", [
    ("succeeded", "started"),
    ("rejected", "started"),
    ("started", "started"),
    ("never_started", "started"),
])
def test_an_illegal_transition_raises_rather_than_being_absorbed(trace, first, second):
    occurrence = trace.invoke("dispatch")
    if first != "started":
        if first in ("succeeded", "rejected"):
            trace.started(occurrence)
            trace.succeeded(occurrence)
            if first == "rejected":
                trace.rejected(occurrence)
        else:
            getattr(trace, first)(occurrence)
    else:
        trace.started(occurrence)
    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        getattr(trace, second)(occurrence)


def test_rejection_is_reachable_only_from_succeeded(trace):
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        trace.rejected(occurrence)


def test_a_terminal_state_has_no_successor(trace):
    for terminal, reach in (("never_started", lambda o: None),
                            ("failed", lambda o: trace.started(o)),
                            ("terminated", lambda o: trace.started(o))):
        occurrence = trace.invoke("dispatch")
        reach(occurrence)
        getattr(trace, terminal)(occurrence)
        assert LEGAL_TRANSITIONS[trace.state_of(occurrence)] == ()


# -- what it closes, and what it deliberately does not ---------------------------------------------------


def test_worlds_b_and_c_are_now_distinguishable(trace):
    """Phase 121 found these byte-identical. They no longer are."""
    never = trace.invoke("dispatch")
    trace.never_started(never, detail="dispatcher not configured")

    crashed = trace.invoke("dispatch")
    trace.started(crashed)
    trace.failed(crashed, failure_type="RuntimeError")

    assert trace.state_of(never) != trace.state_of(crashed)
    assert trace.occurrences_in_state(NEVER_STARTED) != trace.occurrences_in_state(FAILED)


def test_retries_are_now_countable(trace):
    """Phase 122 Q4: UNRECOVERABLE. Now observed -- but only as
    occurrences, never as a judgement that they were 'the same'."""
    for _ in range(3):
        occurrence = trace.invoke("dispatch", input_ref="cand-1")
        trace.started(occurrence)
        trace.succeeded(occurrence, output_ref="rec-1")
    assert len(trace.occurrences_in_state(SUCCEEDED)) == 3


def test_no_equivalence_relation_is_imposed():
    """Phase 123's finding, respected. The instrument answers 'what
    happened'; it does not answer 'was that the same operation'."""
    module = inspect.getmodule(OperationTrace)
    names = {n.name for n in ast.walk(ast.parse(inspect.getsource(module)))
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for absent in ("same_operation", "equivalent", "deduplicate", "canonical",
                   "merge", "collapse", "is_retry_of"):
        assert absent not in names


def test_the_ledger_supplies_no_witness(trace):
    """Phases 111/111b/119 stand. A recorded call is not evidence that
    anything real happened."""
    occurrence = trace.invoke("dispatch")
    trace.started(occurrence)
    trace.succeeded(occurrence, output_ref="rec-1")
    fields = {f.name for f in dataclasses.fields(LifecycleTransition)}
    assert not (fields & {"witness", "attested_by", "signature", "verified"})
    flat = " ".join(inspect.getsource(inspect.getmodule(OperationTrace)).split())
    assert "recording that a call happened is not a witness" in flat


# -- the two ledgers stay separate -------------------------------------------------------------------------


def test_exactly_one_seam_references_the_operation_trace_and_only_for_typing():
    """PHASE 125 attached it. `experiment/step.py` is the one seam, and it
    imports the trace under TYPE_CHECKING only -- so the runtime coupling
    from the scientific layers to the instrument is still ZERO, and a
    caller that passes no trace runs exactly the code it ran before."""
    importers = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                # real imports only -- "operations" also occurs as prose
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("operations"):
                    importers.append(str(path.relative_to(REPO)))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("operations"):
                            importers.append(str(path.relative_to(REPO)))
    assert importers == ["experiment/step.py"]

    # ...and that single import is annotation-only
    step = ast.parse((REPO / "experiment" / "step.py").read_text())
    guarded = [n for n in ast.walk(step)
               if isinstance(n, ast.If)
               and getattr(n.test, "id", "") == "TYPE_CHECKING"]
    assert any(
        isinstance(inner, ast.ImportFrom) and (inner.module or "").startswith("operations")
        for block in guarded for inner in block.body
    )


def test_the_operation_trace_imports_nothing_from_the_scientific_layers():
    imported = set()
    for node in ast.walk(ast.parse(inspect.getsource(inspect.getmodule(OperationTrace)))):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
    assert imported == {"__future__", "dataclasses", "datetime", "types", "typing"}


def test_the_contradictory_identity_rules_are_documented():
    flat = " ".join(inspect.getsource(inspect.getmodule(OperationTrace)).split())
    assert "a repeat is a NO-OP" in flat
    assert "a repeat is a SECOND EVENT" in flat
