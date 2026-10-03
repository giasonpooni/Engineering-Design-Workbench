"""The STE vertical end-to-end: computed results through the EXISTING seam.

    candidates -> policy decision -> SpecificationDispatcher
        -> ExecutionSpecification -> Rust engine (separate process)
        -> checked ExecutionResult -> DispatchedMeasurement
        -> run_experiment_step admission -> EvidencePool
    with the Phase 125 OperationTrace recording the dispatch.

The decisive audits: evidence identity is NOT contaminated by execution
history (two complete loops in two sessions admit the SAME observation
id), and operation identity is (two dispatches are two occurrences).
"""

from __future__ import annotations

import struct

import pytest

from evidence.admission import admit_document, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_referent, make_source
from execution.dispatcher import SpecificationDispatcher
from execution.engine import default_cli_path
from execution.specification import (
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)
from experiment.policy import ExperimentPolicy
from experiment.session import make_experiment_session
from experiment.step import run_experiment_step
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import InformationValueEstimate
from materials.iteration import reevaluate_program
from materials.optimization import OptimizationPolicy
from materials.program import make_material_program_query
from materials.selection import SelectionPolicy
from materials.utility import ExperimentUtilityInput
from operations.trace import SUCCEEDED, OperationTrace
from retrieval.engine import DeterministicRetrievalEngine

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine binary not built; environment gap, not an architectural pass",
)

ENGINE = DeterministicRetrievalEngine()
CRITERION = make_criterion("interaction_energy", "<=", 0)
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)
DECIDE_ONE = OptimizationPolicy(
    max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=True
)


def _benefit(estimate: InformationValueEstimate) -> ExperimentUtilityInput:
    if estimate.estimate is not None:
        return ExperimentUtilityInput(benefit=estimate.estimate, cost=1.0)
    return ExperimentUtilityInput(benefit=1.0, cost=1.0)


def _setup():
    pool = EvidencePool()
    source = make_source(kind="computational_campaign", name="STE")
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content="ste execution session",
        retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z",
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    for key, kind in (("process-lj-cell", "process"), ("formulation-argon-pair", "formulation")):
        referent = make_referent(natural_key=key, kind=kind)
        admit_referent(pool, referent)
        pool.put_referent(referent)
    query = make_material_program_query(
        ["formulation-argon-pair"], "process-lj-cell", ("interaction_energy",)
    )
    iteration = reevaluate_program(pool, ENGINE, query, (CRITERION,))
    session = make_experiment_session(pool, ENGINE, iteration, document_id=doc.id)
    return pool, session


def _dispatcher() -> SpecificationDispatcher:
    def spec_for(candidate) -> ExecutionSpecification:
        # The candidate's cell decides the system; here, one fixed
        # particle arrangement per formulation.
        return ExecutionSpecification(
            program=PAIRWISE_ENERGY_DESCRIPTOR,
            configuration=b"",
            input_payload=encode_positions([(0, 0, 0), (5, 0, 0), (0, 5, 0)]),
        )

    def interpret(candidate, result):
        (energy,) = struct.unpack("<16s", result.output)
        value = int.from_bytes(energy, "little", signed=True)
        # The semantic content carries the COMPUTED VALUE and its
        # meaning -- and none of the execution bookkeeping: no
        # occurrence, no specification id, no computation id. Those live
        # in the Record's raw content. That exclusion is what the
        # contamination test below turns into a checked property.
        return {"property": candidate.property, "value": value, "unit": "lj_integer_units"}

    return SpecificationDispatcher(
        spec_for=spec_for, interpret=interpret, extracted_at="2026-08-25T00:00:00Z",
    )


def _run_loop(trace=None):
    pool, session = _setup()
    candidates = generate_candidates(session.iteration.specification)
    policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL, optimization_policy=DECIDE_ONE,
        utility_input_source=_benefit,
    )
    step = run_experiment_step(
        session, candidates, _dispatcher(), policy, confidence=1.0, trace=trace
    )
    return pool, step


def test_computed_result_is_admitted_through_the_existing_boundary():
    pool, step = _run_loop()
    assert pool.has_observation(step.observation.id)
    assert step.observation.extraction_method == "simulation:deterministic_native_execution"
    # The record carries the execution transcript; the observation does not.
    assert "computation" in step.dispatched.record_raw_content
    assert "computation" not in step.observation.content
    assert "occurrence" not in step.observation.content


def test_evidence_identity_is_not_contaminated_by_execution_history():
    """Two COMPLETE loops -- two engine processes, two admissions, two
    pools: the admitted observation ids are IDENTICAL. Execution
    happened twice; the evidence is one fact, twice reproduced. This is
    invariant 8 of the STE directive as a checked property."""
    _, first = _run_loop()
    _, second = _run_loop()
    assert first.observation.id == second.observation.id
    assert first.result.candidate_id == second.result.candidate_id


def test_the_operation_ledger_records_the_dispatch_as_an_occurrence():
    trace = OperationTrace()
    _, step = _run_loop(trace=trace)
    occurrences = trace.occurrences()
    assert len(occurrences) == 1
    assert trace.state_of(0) == SUCCEEDED
    transitions = trace.transitions_of(0)
    assert transitions[-1].output_ref == step.observation.id
    # And the two ledgers stay orthogonal: rerunning yields occurrence 1
    # in the SAME trace while the evidence id (previous test) collapses.
    _, step2 = _run_loop(trace=trace)
    assert len(trace.occurrences()) == 2
    assert step2.observation.id == step.observation.id


def test_a_halting_execution_admits_nothing_and_is_recorded_failed():
    from operations.trace import FAILED

    pool, session = _setup()
    candidates = generate_candidates(session.iteration.specification)
    policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL, optimization_policy=DECIDE_ONE,
        utility_input_source=_benefit,
    )
    dispatcher = _dispatcher()
    # Coincident particles: the kernel faults, no output exists, the
    # dispatcher refuses to fabricate a measurement.
    broken = SpecificationDispatcher(
        spec_for=lambda c: ExecutionSpecification(
            program=PAIRWISE_ENERGY_DESCRIPTOR, configuration=b"",
            input_payload=encode_positions([(1, 1, 1), (1, 1, 1)]),
        ),
        interpret=dispatcher.interpret, extracted_at=dispatcher.extracted_at,
    )
    trace = OperationTrace()
    fingerprint_before = pool.fingerprint()
    with pytest.raises(RuntimeError, match="no output, no measurement"):
        run_experiment_step(session, candidates, broken, policy, confidence=1.0, trace=trace)
    assert pool.fingerprint() == fingerprint_before, "nothing entered the pool"
    assert trace.state_of(0) == FAILED
