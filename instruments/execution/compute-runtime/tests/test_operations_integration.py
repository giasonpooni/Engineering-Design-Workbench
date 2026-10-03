"""Phase 125: the operation instrument attached to the real seam.

Integration only -- no semantic audit. Every case below goes through the
actual `run_experiment_step(...)` -> `ActionDispatcher.dispatch(...)` path.
No execution objects are constructed outside the seam.

THE SEAM: `experiment/step.py`, the one `dispatcher.dispatch(...)` call.
There is no second execution boundary to invent.
"""

from __future__ import annotations

import dataclasses
from typing import Dict

import pytest

from evidence.admission import admit_document, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_referent, make_source
from experiment.interface import DispatchedMeasurement
from experiment.policy import ExperimentPolicy
from experiment.session import make_experiment_session
from experiment.step import DISPATCH_OPERATION, run_experiment_step
from materials.candidates import generate_candidates
from materials.iteration import reevaluate_program
from materials.optimization import OptimizationPolicy
from materials.program import make_material_program_query
from materials.selection import SelectionPolicy
from materials.utility import ExperimentUtilityInput
from operations.trace import (
    FAILED,
    INVOKED,
    NEVER_STARTED,
    REJECTED,
    STARTED,
    SUCCEEDED,
    OperationTrace,
)
from retrieval.engine import DeterministicRetrievalEngine

FIXED = "2026-08-24T03:00:00Z"


@dataclasses.dataclass
class _Dispatcher:
    """A scripted dispatcher whose behaviour each test chooses. Declares
    what it is (Phase 120), never a measurement."""

    value: float = 90.0
    raises: BaseException | None = None
    property_name: str = "tensile_strength"

    def dispatch(self, candidate) -> DispatchedMeasurement:
        if self.raises is not None:
            raise self.raises
        return DispatchedMeasurement(
            content={"property": self.property_name, "value": self.value, "unit": "MPa"},
            record_locator=f"scripted-{candidate.id[:8]}-{self.value}",
            record_raw_content=f"scripted measurement: {self.property_name}={self.value}",
            extracted_at=FIXED,
            extraction_method="simulation:scripted_fixture",
        )


def _clock():
    n = [0]

    def c():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    return c


@pytest.fixture
def workflow():
    """The real bootstrap the experiment tests already use."""
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="session log",
                             retrieval_method="manual_entry", retrieved_at=FIXED)
    admit_document(pool, document)
    pool.put_document(document)
    for key, kind in (("process-std-190c", "process"), ("formulation-a", "material")):
        referent = make_referent(natural_key=key, kind=kind)
        admit_referent(pool, referent)
        pool.put_referent(referent)

    engine = DeterministicRetrievalEngine()
    query = make_material_program_query(
        formulation_natural_keys=("formulation-a",),
        process_natural_key="process-std-190c", properties=("tensile_strength",))
    from materials.decision import make_criterion
    criteria = (make_criterion("tensile_strength", ">=", 75.0),)
    iteration = reevaluate_program(pool, engine, query, criteria)
    candidates = generate_candidates(iteration.specification)
    session = make_experiment_session(pool=pool, engine=engine, iteration=iteration,
                                      document_id=document.id)
    policy = ExperimentPolicy(
        selection_policy=SelectionPolicy(
            allowed_action_classes=None, allow_already_represented_context=True,
            allow_redundant=True, allow_not_determinable_feasibility=True,
            max_selected=None),
        optimization_policy=OptimizationPolicy(
            max_candidates=1, allowed_action_classes=None,
            allow_indeterminate_utility=True),
        utility_input_source=lambda estimate: ExperimentUtilityInput(
            benefit=estimate.estimate if estimate.estimate is not None else 1.0,
            cost=1.0),
    )
    return session, candidates, policy


# -- A: dispatch succeeds -> evidence admitted --------------------------------------------------------


def test_a_successful_dispatch_records_invoked_started_succeeded(workflow):
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())

    step = run_experiment_step(session, candidates, _Dispatcher(), policy,
                               confidence=1.0, trace=trace)

    assert len(trace.occurrences()) == 1
    occurrence = trace.occurrences()[0]
    assert occurrence.operation == DISPATCH_OPERATION
    assert occurrence.input_ref == step.chosen_candidate_id
    assert [t.to_state for t in trace.transitions_of(0)] == [INVOKED, STARTED, SUCCEEDED]
    # sec.6: the occurrence points at the evidence. One direction only.
    assert trace.transitions_of(0)[-1].output_ref == step.observation.id


# -- B: dispatcher raises ------------------------------------------------------------------------------


def test_a_raising_dispatch_records_failure_and_re_raises_unchanged(workflow):
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())
    boom = RuntimeError("instrument offline")

    with pytest.raises(RuntimeError) as caught:
        run_experiment_step(session, candidates, _Dispatcher(raises=boom), policy,
                            confidence=1.0, trace=trace)

    assert caught.value is boom                       # the SAME exception object
    assert [t.to_state for t in trace.transitions_of(0)] == [INVOKED, STARTED, FAILED]
    last = trace.transitions_of(0)[-1]
    assert last.failure_type == "RuntimeError"
    assert session.pool.all_observations() == ()      # nothing admitted


def test_the_same_exception_reaches_a_caller_with_no_trace(workflow):
    session, candidates, policy = workflow
    boom = RuntimeError("instrument offline")
    with pytest.raises(RuntimeError) as caught:
        run_experiment_step(session, candidates, _Dispatcher(raises=boom), policy,
                            confidence=1.0)
    assert caught.value is boom


# -- C: dispatch succeeds, admission rejects -----------------------------------------------------------


def test_a_downstream_rejection_records_succeeded_then_rejected(workflow):
    """The dispatcher returns a property the campaign entry did not ask
    for, so `make_experimental_result` refuses it."""
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())

    with pytest.raises(ValueError):
        run_experiment_step(session, candidates,
                            _Dispatcher(property_name="WRONG_PROPERTY"), policy,
                            confidence=1.0, trace=trace)

    assert [t.to_state for t in trace.transitions_of(0)] == [
        INVOKED, STARTED, SUCCEEDED, REJECTED]
    assert session.pool.all_observations() == ()


# -- D: repeated identical dispatches -- THE TWO LEDGERS, SIMULTANEOUSLY -------------------------------


def test_identical_executions_are_many_occurrences_and_one_observation(workflow):
    """sec.8. The first demonstration of both ledgers operating at once."""
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())

    observations, fingerprints = [], []
    for _ in range(3):
        step = run_experiment_step(session, candidates, _Dispatcher(), policy,
                                   confidence=1.0, trace=trace)
        observations.append(step.observation.id)
        fingerprints.append(session.pool.fingerprint())

    # OPERATION LEDGER: multiplicity preserved
    assert len({o.occurrence for o in trace.occurrences()}) == 3
    assert len(trace.occurrences_in_state(SUCCEEDED)) == 3

    # EVIDENCE LEDGER: identical content collapses
    assert len(set(observations)) == 1
    assert len(set(fingerprints)) == 1
    assert len(session.pool.all_observations()) == 1

    # ...and every occurrence points at that one observation
    assert {trace.transitions_of(o.occurrence)[-1].output_ref
            for o in trace.occurrences()} == set(observations)


# -- 9: retry ------------------------------------------------------------------------------------------


def test_a_retry_is_linked_only_when_the_caller_says_so(workflow):
    """A failure, then a success. The seam does not infer the relation --
    a caller who wants it recorded links the occurrences itself."""
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())

    with pytest.raises(RuntimeError):
        run_experiment_step(session, candidates,
                            _Dispatcher(raises=RuntimeError("timeout")), policy,
                            confidence=1.0, trace=trace)
    assert trace.state_of(0) == FAILED

    run_experiment_step(session, candidates, _Dispatcher(), policy,
                        confidence=1.0, trace=trace)
    assert trace.state_of(1) == SUCCEEDED

    # the seam recorded NO relation between them
    assert trace.occurrences()[1].retry_of is None

    # a caller that observed the retry can record it, on its own occurrence
    linked = trace.invoke(DISPATCH_OPERATION, retry_of=0)
    assert trace.occurrences()[linked].retry_of == 0


# -- 5/6/10: nothing about the evidence ledger changed --------------------------------------------------


def test_the_evidence_fingerprint_is_identical_with_and_without_a_trace(workflow):
    session, candidates, policy = workflow
    untraced = run_experiment_step(session, candidates, _Dispatcher(), policy,
                                   confidence=1.0)
    without = (untraced.observation.id, untraced.result.id,
               untraced.session.pool.fingerprint(), untraced.session.state.id)

    session2, candidates2, policy2 = workflow
    traced = run_experiment_step(session2, candidates2, _Dispatcher(), policy2,
                                 confidence=1.0, trace=OperationTrace(clock=_clock()))
    with_trace = (traced.observation.id, traced.result.id,
                  traced.session.pool.fingerprint(), traced.session.state.id)

    assert without == with_trace


def test_the_trace_never_enters_the_evidence_pool(workflow):
    session, candidates, policy = workflow
    trace = OperationTrace(clock=_clock())
    run_experiment_step(session, candidates, _Dispatcher(), policy,
                        confidence=1.0, trace=trace)

    occurrence_ids = {str(o.occurrence) for o in trace.occurrences()}
    for observation in session.pool.all_observations():
        assert occurrence_ids.isdisjoint(set(observation.record_ids))
        assert "occurrence" not in observation.content
        assert DISPATCH_OPERATION not in repr(observation.content)


def test_no_evidence_object_learns_that_an_operation_exists(workflow):
    """sec.6: no inverse edge. The observation does not depend on
    operation identity, and could not."""
    from evidence.types import Observation
    from materials.results import ExperimentalResult
    for cls in (Observation, ExperimentalResult):
        fields = {f.name for f in dataclasses.fields(cls)}
        assert not (fields & {"occurrence", "operation", "trace", "execution"})


def test_a_workflow_with_no_trace_behaves_exactly_as_before(workflow):
    session, candidates, policy = workflow
    step = run_experiment_step(session, candidates, _Dispatcher(), policy, confidence=1.0)
    assert step.observation is not None
    assert len(session.pool.all_observations()) == 1
    import inspect
    assert inspect.signature(run_experiment_step).parameters["trace"].default is None
