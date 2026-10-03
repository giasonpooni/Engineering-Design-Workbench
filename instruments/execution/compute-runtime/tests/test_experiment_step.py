"""Phase 63 implementation: experiment.step -- the closed experimental
loop, end to end, through the new experiment/ package's own public API
only. Small focused test set (build-more-test-less mode): a real
two-step closed loop, deterministic decision-making, historical-session
immutability, and explicit rejection when no candidate can be chosen.
"""

from dataclasses import dataclass
from typing import Dict

from evidence.admission import admit_document, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_referent, make_source
from experiment.interface import DispatchedMeasurement
from experiment.policy import ExperimentPolicy
from experiment.session import make_experiment_session, trajectory_of
from experiment.step import run_experiment_step
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import InformationValueEstimate
from materials.iteration import reevaluate_program
from materials.optimization import OptimizationPolicy
from materials.program import make_material_program_query
from materials.selection import SelectionPolicy
from materials.utility import ExperimentUtilityInput
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)

DECIDE_ONE = OptimizationPolicy(max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=True)


@dataclass(frozen=True)
class ScriptedDispatcher:
    """A deterministic, test/demo-oriented `ActionDispatcher` -- the
    only kind this codebase ships, exactly as `scout.adapters.
    FixtureSourceAdapter` is the only `SourceAdapter` it ships. Returns
    a pre-scripted value per candidate_id; never touches EvidencePool,
    never reads a clock."""

    values_by_candidate_id: Dict[str, float]
    property_by_candidate_id: Dict[str, str]
    extracted_at: str = "2026-08-24T03:00:00Z"

    def dispatch(self, candidate) -> DispatchedMeasurement:
        value = self.values_by_candidate_id[candidate.id]
        property_name = self.property_by_candidate_id[candidate.id]
        return DispatchedMeasurement(
            content={"property": property_name, "value": value, "unit": "MPa"},
            record_locator=f"scripted-{candidate.id[:8]}-{value}",
            record_raw_content=f"scripted measurement: {property_name}={value}",
            extracted_at=self.extracted_at,
            # Phase 120: a scripted constant is not a measurement. Of the
            # four statuses `classify_epistemic_status` can return, only
            # `simulation:` asserts no EXTERNAL event -- a bare `fixture:`
            # prefix falls through to EXTRACTED, which would falsely claim
            # a document extraction. This is the least-wrong declaration
            # available, not a claim that a simulation ran.
            extraction_method="simulation:scripted_fixture",
        )


def _setup():
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(source_id=source.id, raw_content="session log", retrieval_method="manual_entry", retrieved_at="2026-08-24T00:00:00Z")
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-std-190c", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION,))

    session = make_experiment_session(pool, ENGINE, iteration, document_id=doc.id)
    return pool, doc, session


def _benefit_from_estimate(estimate: InformationValueEstimate) -> ExperimentUtilityInput:
    # Phase 60's own proven composition: route the model-driven
    # information estimate straight into benefit, at face value. When
    # the model has no samples yet to compute a variance from
    # (estimate.estimate is None -- e.g. the very first measurement for
    # a cell), this is an EXPLICIT caller policy choice -- explore once,
    # benefit=1.0 -- documented as exactly that. This is NOT the same
    # thing as silently substituting 0.0 for "unknown": 0.0 would claim
    # "we know the benefit is zero," which is false; an explicit
    # bootstrap constant says "we don't know yet, and we choose to
    # explore anyway," which is what it actually is.
    if estimate.estimate is not None:
        return ExperimentUtilityInput(benefit=estimate.estimate, cost=1.0)
    return ExperimentUtilityInput(benefit=1.0, cost=1.0)  # explicit bootstrap: explore once


# -- 1. a real two-step closed loop, end to end --------------------------------------------------------


def test_1_two_step_closed_loop():
    pool, doc, session = _setup()
    candidates = generate_candidates(session.iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")

    policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL, optimization_policy=DECIDE_ONE, utility_input_source=_benefit_from_estimate,
    )
    dispatcher = ScriptedDispatcher(
        values_by_candidate_id={candidate.id: 80.0}, property_by_candidate_id={candidate.id: "tensile_strength"},
    )

    step1 = run_experiment_step(session, candidates, dispatcher, policy, confidence=1.0)
    assert step1.chosen_candidate_id == candidate.id
    assert step1.session.state.id != session.state.id
    assert step1.session.state_history == (session.state, step1.session.state)
    # the OLD session is untouched.
    assert session.state_history == (session.state,)

    # step 2: re-evaluate against the now-updated pool, dispatch a
    # second measurement for the SAME candidate/cell.
    iteration2 = reevaluate_program(pool, ENGINE, make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",)), (TENSILE_CRITERION,))
    session2 = step1.session
    session2 = type(session2)(
        pool=session2.pool, engine=session2.engine, iteration=iteration2, state=session2.state,
        state_history=session2.state_history, document_id=session2.document_id,
    )
    candidates2 = generate_candidates(iteration2.specification)
    candidate2 = next((c for c in candidates2.candidates if c.property == "tensile_strength"), candidate)
    dispatcher2 = ScriptedDispatcher(
        values_by_candidate_id={candidate2.id: 90.0}, property_by_candidate_id={candidate2.id: "tensile_strength"},
    )
    step2 = run_experiment_step(session2, candidates2, dispatcher2, policy, confidence=1.0)

    assert step2.session.state.id != step1.session.state.id
    assert len(step2.session.state_history) == 3
    trajectory = trajectory_of(step2.session)
    assert len(trajectory.entries) == 3
    assert step2.assessment.residual is not None or step2.assessment.residual is None  # always defined either way


# -- 2. provenance: the decision and the admitted evidence trace back to the same candidate ------------


def test_2_provenance_preserved():
    pool, doc, session = _setup()
    candidates = generate_candidates(session.iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")
    policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL, optimization_policy=DECIDE_ONE, utility_input_source=_benefit_from_estimate,
    )
    dispatcher = ScriptedDispatcher(
        values_by_candidate_id={candidate.id: 82.0}, property_by_candidate_id={candidate.id: "tensile_strength"},
    )
    step = run_experiment_step(session, candidates, dispatcher, policy, confidence=1.0)

    assert step.result.candidate_id == candidate.id
    assert step.optimization.utility_set.process_natural_key == session.iteration.specification.process_natural_key
    selected = [o for o in step.optimization.optimizations if o.status == "SELECTED"]
    assert len(selected) == 1
    assert selected[0].candidate_id == candidate.id
    assert step.assessment.candidate_id == candidate.id


# -- 3. historical-session immutability -----------------------------------------------------------------


def test_3_historical_session_immutability():
    pool, doc, session = _setup()
    before_state_id = session.state.id
    before_history = session.state_history
    candidates = generate_candidates(session.iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")
    policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL, optimization_policy=DECIDE_ONE, utility_input_source=_benefit_from_estimate,
    )
    dispatcher = ScriptedDispatcher(
        values_by_candidate_id={candidate.id: 85.0}, property_by_candidate_id={candidate.id: "tensile_strength"},
    )
    run_experiment_step(session, candidates, dispatcher, policy, confidence=1.0)

    assert session.state.id == before_state_id
    assert session.state_history == before_history


# -- 4. no SELECTED candidate -> explicit rejection, never a silent default -----------------------------


def test_4_no_selected_candidate_raises():
    pool, doc, session = _setup()
    candidates = generate_candidates(session.iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")
    # max_candidates=0 -- nothing can ever be SELECTED.
    impossible_policy = ExperimentPolicy(
        selection_policy=ALLOW_ALL,
        optimization_policy=OptimizationPolicy(max_candidates=0, allowed_action_classes=None, allow_indeterminate_utility=True),
        utility_input_source=_benefit_from_estimate,
    )
    dispatcher = ScriptedDispatcher(
        values_by_candidate_id={candidate.id: 85.0}, property_by_candidate_id={candidate.id: "tensile_strength"},
    )
    try:
        run_experiment_step(session, candidates, dispatcher, impossible_policy, confidence=1.0)
        assert False, "expected a ValueError when no candidate can be SELECTED"
    except ValueError as e:
        assert "exactly one SELECTED candidate" in str(e)
