"""run_experiment_step: the sequencing function
`docs/EXPERIMENT_ARCHITECTURE.md` §3.4 specifies -- the one place
`experiment/` actually calls things in order. Every step below is an
unmodified `materials/` primitive already proven across Phases 37-61;
this function adds no new prediction, information, utility, ranking, or
transition mathematics of its own -- it only sequences what already
exists, exactly as `scout.pipeline.run_scout` sequences unmodified
`evidence/` primitives without adding new admission logic to them.

    1. materials.model_state.predict                      -- P_t = G(S_t, x), per candidate
    2. materials.information.estimate_information_value     -- information value at S_t (model-driven)
    3. materials.utility.evaluate_utility_set                 -- utility, from policy.utility_input_source
    4. materials.optimization.optimize_candidates(max_candidates=1 typically)  -- THE decision (Phase 60)
    5. the campaign entry the chosen candidate needs to be executed against
       (materials.evaluation/selection/plan/design/campaign -- Phase 38-43, unchanged)
    6. ActionDispatcher.dispatch                              -- perform the chosen action [seam]
    7. evidence.admission.admit_record                          -- log the raw measurement (see below)
    8. materials.results.make_experimental_result /
       admit_experimental_result                                 -- the sole SEMANTIC write boundary
    9. materials.model_state.update                              -- S_(t+1) = F(S_t, O_t)
   10. materials.assessment.assess                                -- residual, diagnostic only

ONE ADMISSION CALL THIS PACKAGE MAKES DIRECTLY, AND WHY IT DOES NOT
VIOLATE THE WRITE BOUNDARY: `docs/EXPERIMENT_ARCHITECTURE.md` originally
specified that every write `experiment/` causes goes through
`materials.results.admit_experimental_result`. Implementing this
function surfaced a precise refinement: `admit_experimental_result`
itself has always required an ALREADY-ADMITTED `record_id` as an input
-- Phase 44's own docstring states this explicitly ("the caller is
responsible for having already admitted the Source/Document/Record
chain"). Record admission has therefore never been part of the write
boundary `materials.results` (or its own boundary test) protects; it is
raw structural bookkeeping (a locator + raw content), not a scientific
claim -- the SAME distinction `docs/SCOUT_ARCHITECTURE.md`'s own data
contract table already draws between `Record` and `Observation`. This
package plays exactly the caller role Phase 44 already anticipated:
`run_experiment_step` calls `evidence.admission.admit_record`/
`pool.put_record` directly (against `session.document_id`, already
admitted before the session was constructed), then hands the resulting
`record.id` to `materials.results.make_experimental_result` -- the
SEMANTIC facts (`Observation`, `ClaimedRelationship`) still only ever
enter `EvidencePool` through `materials.results.admit_experimental_result`,
exactly as specified. `tests/test_experiment_boundaries.py` enforces
this exact, narrower rule: `admit_record`/`pool.put_record` are the only
admission calls permitted anywhere under `experiment/`; `admit_observation`/
`admit_claimed_relationship`/`pool.put_observation`/
`pool.put_claimed_relationship`/`admit_document`/`pool.put_document`/
`pool.put_source` are forbidden, exactly like everywhere else in this
codebase outside `materials/results.py` and `scout/pipeline.py`.

EPISTEMIC BOUNDARY: `chosen_prediction` (step 1's result for the
candidate actually chosen) is computed BEFORE dispatch/admission/update
-- it is `P_t`, attributable forever to `session.state`, exactly the
same "a prediction is tied to the state that produced it" discipline
Phase 52 established. `assess` (step 10) is diagnostic only: its
`PredictionAssessment` is never fed back into the decision already made
in step 4, and is never required by `update` (step 9) -- exactly Phase
54's own "assessing a prediction is not the same act as the state
transition that follows it."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from evidence.admission import admit_record
from evidence.types import Observation, make_record
from materials.assessment import PredictionAssessment, assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import CandidateSet
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.information import estimate_information_value
from materials.model_state import ModelStateInformationValueModel, predict, update
from materials.optimization import SELECTED, OptimizationResult, optimize_candidates
from materials.plan import assemble_experiment_plan
from materials.results import ExperimentalResult, admit_experimental_result, make_experimental_result

if TYPE_CHECKING:  # pragma: no cover -- annotation only; no runtime dependency
    from operations.trace import OperationTrace
from materials.selection import select_candidates
from materials.utility import evaluate_utility_set
from materials.value import evaluate_candidate_information_values

from experiment.interface import ActionDispatcher, DispatchedMeasurement
from experiment.policy import ExperimentPolicy
from experiment.session import ExperimentSession

#: The operation name this seam records under. One constant, one seam --
#: there is no second execution boundary to invent (sec.1).
DISPATCH_OPERATION = "experiment.dispatch"


@dataclass(frozen=True)
class ExperimentStepResult:
    """One complete step's outcome. `session` is the NEW `ExperimentSession`
    (state advanced) -- the OLD session passed into `run_experiment_step`
    remains exactly as it was; nothing about this function mutates it.
    `optimization` is the complete, unmodified `OptimizationResult` --
    full provenance of the decision (every candidate's status, not just
    the chosen one) without duplicating any of it. `dispatched`/`result`/
    `observation`/`assessment` are likewise embedded whole."""

    session: ExperimentSession
    chosen_candidate_id: str
    optimization: OptimizationResult
    dispatched: DispatchedMeasurement
    result: ExperimentalResult
    observation: Observation
    assessment: PredictionAssessment


def run_experiment_step(
    session: ExperimentSession,
    candidates: CandidateSet,
    dispatcher: ActionDispatcher,
    policy: ExperimentPolicy,
    confidence: float,
    trace: Optional["OperationTrace"] = None,
) -> ExperimentStepResult:
    """Deterministic given a deterministic `dispatcher`; never mutates
    `session`, `candidates`, or `policy`. `candidates` is RECEIVED, not
    generated internally -- a caller who wants "generate candidates"
    calls `materials.candidates.generate_candidates(session.iteration.
    specification)` themselves before calling this function, keeping
    this function agnostic to where its input candidates came from
    (freshly generated, curated, reused across steps).

    Raises `ValueError` if `policy.optimization_policy` does not yield
    exactly one SELECTED candidate, or if the selected candidate has no
    `ExperimentalCampaign` entry under `policy.selection_policy` -- both
    are caller-policy configuration problems, not something this
    function silently works around."""
    action_candidates = candidates.candidates
    predictions = {c.id: predict(session.state, c) for c in action_candidates}

    info_model = ModelStateInformationValueModel(session.state)
    info_estimates = {c.id: estimate_information_value(c, session.iteration, info_model) for c in action_candidates}

    structural_info_values = evaluate_candidate_information_values(candidates, session.iteration)
    utility_inputs = {c.id: policy.utility_input_source(info_estimates[c.id]) for c in action_candidates}
    utility_set = evaluate_utility_set(structural_info_values, utility_inputs)

    optimization = optimize_candidates(utility_set, policy.optimization_policy)
    selected = [o for o in optimization.optimizations if o.status == SELECTED]
    if len(selected) != 1:
        raise ValueError(
            f"run_experiment_step requires exactly one SELECTED candidate under the supplied "
            f"OptimizationPolicy; got {len(selected)}. Adjust policy.optimization_policy "
            f"(e.g. max_candidates=1) or supply utility inputs that make a determinate choice possible."
        )
    chosen_candidate = selected[0].utility.information_value.evaluation.candidate
    chosen_prediction = predictions[chosen_candidate.id]

    evaluations = evaluate_candidates(candidates)
    campaign_selection = select_candidates(evaluations, policy.selection_policy)
    plan = assemble_experiment_plan(campaign_selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next((e for e in campaign.entries if e.candidate_id == chosen_candidate.id), None)
    if entry is None:
        raise ValueError(
            f"candidate {chosen_candidate.id!r} was SELECTED by optimize_candidates but has no "
            f"ExperimentalCampaign entry under policy.selection_policy -- widen selection_policy "
            f"so every candidate optimize_candidates can select also has a campaign entry to execute against"
        )

    occurrence = None
    if trace is not None:
        occurrence = trace.invoke(DISPATCH_OPERATION, input_ref=chosen_candidate.id)
        trace.started(occurrence)
    try:
        dispatched = dispatcher.dispatch(chosen_candidate)
    except Exception as exc:
        # RECORD the failure; never HANDLE it. The caller receives exc
        # exactly as before -- see this module's docstring.
        if trace is not None:
            trace.failed(occurrence, failure_type=type(exc).__name__, detail=str(exc)[:200])
        raise

    # The dispatch RETURNED, so the operation succeeded -- but the value it
    # produced must still get past the downstream boundaries below. Both
    # outcomes are recorded from the one place, so no occurrence is ever
    # left dangling in STARTED: SUCCEEDED always fires, and REJECTED
    # follows it whenever a boundary refuses what dispatch produced.
    # NOTE ON TIMING: SUCCEEDED is RECORDED here, after the outcome is
    # known, so its `at` is later than the instant dispatch returned. The
    # transition is real; only the recording moment is deferred, which is
    # what lets it carry the resulting evidence id (sec.6).
    try:
        record = make_record(
            document_id=session.document_id, locator=dispatched.record_locator,
            raw_content=dispatched.record_raw_content,
        )
        admitted_record = admit_record(session.pool, record)
        if isinstance(admitted_record, list):
            raise ValueError(
                f"dispatched measurement's Record was rejected by admit_record: {admitted_record!r}")
        session.pool.put_record(record)

        result = make_experimental_result(
            campaign, entry, content=dispatched.content, record_id=record.id,
            extracted_at=dispatched.extracted_at, extraction_method=dispatched.extraction_method,
        )
        admitted = admit_experimental_result(session.pool, result, confidence=confidence)
        if isinstance(admitted, list):
            raise ValueError(
                f"ExperimentalResult was rejected by admit_experimental_result: {admitted!r}")
        observation, _relationship = admitted
    except Exception as exc:
        if trace is not None:
            trace.succeeded(occurrence)
            trace.rejected(occurrence, failure_code=type(exc).__name__, detail=str(exc)[:200])
        raise

    if trace is not None:
        # sec.6's one-directional link: the OCCURRENCE points at the evidence.
        # No inverse edge is added, and no evidence object learns that an
        # operation exists.
        trace.succeeded(occurrence, output_ref=observation.id)

    new_state = update(session.state, chosen_candidate, result, observation)
    assessment = assess(chosen_prediction, result, observation)

    new_session = ExperimentSession(
        pool=session.pool, engine=session.engine, iteration=session.iteration, state=new_state,
        state_history=session.state_history + (new_state,), document_id=session.document_id,
    )

    return ExperimentStepResult(
        session=new_session, chosen_candidate_id=chosen_candidate.id, optimization=optimization,
        dispatched=dispatched, result=result, observation=observation, assessment=assessment,
    )
