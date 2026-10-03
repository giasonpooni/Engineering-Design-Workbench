"""Phase 72: proves the workbench is a general experimental workbench,
not a polished two-candidate demonstration -- a research session with
FOUR candidates spanning TWO formulations and TWO experimental contexts
(the phase's own minimum ask was three; two formulations x two contexts
is the natural, unmodified product of `materials.candidates.
generate_candidates` given two formulations and two criteria, and
additionally yields a fourth, never-touched "control" candidate that
strengthens every isolation assertion below).

INVESTIGATION (Phase 72 sec. "Audit the current workbench", re-read
fresh: `workbench/interaction.py`, `workbench/cli.py`, `workbench/
investigation.py`, `workbench/demo.py`, `experiment/session.py`,
`experiment/step.py`, `materials/candidates.py`, `materials/model_
state.py`, `materials/information.py`, `materials/utility.py`,
`materials/ranking.py`, `materials/optimization.py`, and every existing
workbench/experiment test):

`workbench.interaction.bootstrap_multi_candidate_scenario` produces
exactly two candidates ONLY because it supplies exactly two `Criterion`
objects for exactly one formulation -- nothing in `materials.candidates.
generate_candidates` (`_action_group_key` groups by formulation.id,
property, role, action_class, and content_hash(criterion_context) --
formulation is the FIRST field), `materials.model_state.
resolve_model_state_key` (keyed by formulation_id, property, and
target_context), `WorkbenchState` (holds a plain `CandidateSet` of
whatever length; `select_candidate`/`list_candidates`/`decide`/
`information_value_estimate` all iterate generically), or `workbench.
cli` (every `_cmd_*`/`format_*` function iterates `state.list_
candidates()` with no length assumption -- confirmed by direct
inspection, not by trying it and hoping) imposes any two-candidate
limit. `bootstrap_multi_candidate_scenario` is confirmed, empirically
and by source inspection, to be MERELY a fixture -- not the definition
of what a "research session" can be. Per the phase's own stop
condition, none of its five conditions for adding a new abstraction are
met (existing operations already express the required semantics;
caller composition already suffices; nothing belongs at a missing
interaction boundary; existing identity/state/provenance already
express multi-formulation/multi-context candidates; nothing would be
duplicated) -- so this file adds NO production abstraction. The
scenario-construction helper below (`_bootstrap_research_scenario`) is
TEST-ONLY, living here rather than in `workbench/interaction.py`,
precisely to keep that finding honest: `workbench/interaction.py`,
`workbench/cli.py`, `materials/`, `experiment/`, and `core/` are all
byte-for-byte unchanged by this phase.
"""

from typing import Callable

import pytest

from evidence.admission import admit_document, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_referent, make_source
from experiment.session import make_experiment_session
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, resolve_model_state_key, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState

PROCESS_KEY = "process-std-190c"
FORMULATION_A = "formulation-f1"
FORMULATION_B = "formulation-f2"
PROPERTY = "tensile_strength"
CONTEXT_ROOM = {"temperature": 25}
CONTEXT_ELEVATED = {"temperature": 100}

ALLOW_ALL_SELECTION_POLICY = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _fixed_clock() -> Callable[[], str]:
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T05:{n:02d}:00Z"

    return clock


def _bootstrap_research_scenario(clock: Callable[[], str]) -> WorkbenchState:
    """Two formulations x two experimental contexts, one shared process,
    zero prior evidence -- built with EXACTLY the same composition
    `workbench.interaction.bootstrap_multi_candidate_scenario` already
    uses (reevaluate_program -> generate_candidates -> evaluate_
    candidates -> select_candidates -> assemble_experiment_plan ->
    assemble_experimental_design -> assemble_experimental_campaign ->
    make_experiment_session), parameterized with a second formulation.
    No new candidate-generation mechanism, no new identity scheme."""
    pool = EvidencePool()
    engine = DeterministicRetrievalEngine()

    source = make_source(kind="lab_notebook", name="Research session")
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content="multi-candidate research session",
        retrieval_method="manual_entry", retrieved_at=clock(),
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key=PROCESS_KEY, kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    formulation_a = make_referent(natural_key=FORMULATION_A, kind="formulation")
    admit_referent(pool, formulation_a)
    pool.put_referent(formulation_a)
    formulation_b = make_referent(natural_key=FORMULATION_B, kind="formulation")
    admit_referent(pool, formulation_b)
    pool.put_referent(formulation_b)

    criterion_room = make_criterion(PROPERTY, ">=", 80, context=CONTEXT_ROOM)
    criterion_elevated = make_criterion(PROPERTY, ">=", 80, context=CONTEXT_ELEVATED)
    query = make_material_program_query([FORMULATION_A, FORMULATION_B], PROCESS_KEY, (PROPERTY,))
    iteration = reevaluate_program(pool, engine, query, (criterion_room, criterion_elevated))
    candidates = generate_candidates(iteration.specification)

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL_SELECTION_POLICY)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)

    session = make_experiment_session(pool, engine, iteration, document_id=doc.id)
    return WorkbenchState(
        pool=pool, engine=engine, document_id=doc.id, candidates=candidates,
        campaign=campaign, session=session, clock=clock,
    )


def _find(state: WorkbenchState, formulation_key: str, context: dict):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation_key and dict(c.target_context) == context
    )


def _display_index(state: WorkbenchState, candidate) -> int:
    return state.list_candidates().index(candidate) + 1


def _sample_count(state: WorkbenchState, candidate) -> int:
    key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    return len(state.session.state.samples.get(key, ()))


@pytest.fixture()
def state() -> WorkbenchState:
    return _bootstrap_research_scenario(clock=_fixed_clock())


# -- structural setup: four distinct candidates, four distinct model-state keys ----------------------


def test_four_candidates_distinct_identity_and_model_state_keys(state: WorkbenchState):
    candidates = state.list_candidates()
    assert len(candidates) == 4
    assert len({c.id for c in candidates}) == 4  # distinct ids -- no new identity scheme needed

    keys = {
        resolve_model_state_key(c.formulation.id, c.property, c.target_context) for c in candidates
    }
    assert len(keys) == 4  # distinct model-state cells for every (formulation, property, context)

    for c in candidates:
        prediction = state.session.predict(c)
        assert prediction.predicted_value is None
        assert prediction.uncertainty is None
        assert prediction.sample_count == 0  # zero, never fabricated


# -- required interaction sequence, driven through the real dispatch layer ----------------------------


def test_candidate_and_context_isolation_through_the_interaction_sequence(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)       # candidate 1 in the phase's own example
    b_room = _find(state, FORMULATION_B, CONTEXT_ROOM)       # candidate 3 in the phase's own example
    a_elevated = _find(state, FORMULATION_A, CONTEXT_ELEVATED)  # candidate 2 in the phase's own example
    b_elevated = _find(state, FORMULATION_B, CONTEXT_ELEVATED)  # never touched -- a control candidate

    dispatch(state, "status", [])
    dispatch(state, "candidates", [])
    dispatch(state, "predict", [])  # honest refusal -- nothing selected yet
    dispatch(state, "decide", [])

    # -- select 1 (a_room); observe 80 --------------------------------------------------------------
    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "predict", [])
    dispatch(state, "decide", [])
    observe_1 = dispatch(state, "observe", ["80"])
    assert "RESIDUAL" in observe_1 and "UNDETERMINED" in observe_1  # honest -- first sample in this cell

    # (candidate isolation, part 1) only a_room's sample count changed
    assert _sample_count(state, a_room) == 1
    assert _sample_count(state, b_room) == 0
    assert _sample_count(state, a_elevated) == 0
    assert _sample_count(state, b_elevated) == 0

    dispatch(state, "status", [])
    dispatch(state, "predict", [])
    dispatch(state, "decide", [])

    # -- select 2 (b_room); observe 60 ---------------------------------------------------------------
    dispatch(state, "select", [str(_display_index(state, b_room))])
    observe_2 = dispatch(state, "observe", ["60"])
    assert "RESIDUAL" in observe_2 and "UNDETERMINED" in observe_2

    # (candidate isolation, part 2) a_room retains its sample; b_room gains one; the rest untouched
    assert _sample_count(state, a_room) == 1
    assert _sample_count(state, b_room) == 1
    assert _sample_count(state, a_elevated) == 0
    assert _sample_count(state, b_elevated) == 0
    assert state.session.predict(a_room).predicted_value == 80.0  # a_room's own prediction is unaffected

    dispatch(state, "status", [])
    dispatch(state, "predict", [])
    dispatch(state, "decide", [])

    # -- select 1 (a_room) again; observe 100 -- a positive residual --------------------------------
    dispatch(state, "select", [str(_display_index(state, a_room))])
    observe_3 = dispatch(state, "observe", ["100"])
    assert "+20.0" in observe_3  # 100 - 80
    assert _sample_count(state, a_room) == 2
    assert _sample_count(state, b_room) == 1  # (context isolation) b_room's own cell is untouched
    assert state.session.predict(a_room).predicted_value == 90.0  # (3) prediction evolution, read from predict()

    dispatch(state, "status", [])
    dispatch(state, "predict", [])
    dispatch(state, "decide", [])

    # -- select 3 (b_elevated); observe 75 -- exercises the fourth, previously-untouched candidate ---
    dispatch(state, "select", [str(_display_index(state, b_elevated))])
    observe_4 = dispatch(state, "observe", ["75"])
    assert "RESIDUAL" in observe_4 and "UNDETERMINED" in observe_4
    assert _sample_count(state, b_elevated) == 1
    # (context isolation, the critical case) a_room (f1/tensile_strength/25C) never moved,
    # even though a_elevated (f1/tensile_strength/100C) shares BOTH formulation and property.
    assert _sample_count(state, a_room) == 2
    assert _sample_count(state, a_elevated) == 0
    assert state.session.predict(a_room).predicted_value == 90.0

    dispatch(state, "history", [])
    dispatch(state, "diagnostics", [])

    # -- a negative residual, for completeness: observe a value below a_room's running mean ----------
    dispatch(state, "select", [str(_display_index(state, a_room))])
    observe_5 = dispatch(state, "observe", ["50"])
    assert "-40.0" in observe_5  # 50 - mean([80, 100]) = 50 - 90


# -- decision evolution: recomputed from current state, never cached ----------------------------------


def test_decision_recomputed_from_current_state_not_cached(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)
    b_room = _find(state, FORMULATION_B, CONTEXT_ROOM)

    decision_before = state.decide()
    utility_before = next(o for o in decision_before.optimizations if o.candidate_id == a_room.id).utility.utility

    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["80"])

    decision_after = state.decide()
    utility_after = next(o for o in decision_after.optimizations if o.candidate_id == a_room.id).utility.utility
    # the recommendation changed because the computational state changed -- not a cached value,
    # not a claim of scientific causality, only a recomputation from the new ModelState.
    assert utility_after != utility_before
    assert decision_after is not decision_before

    b_room_utility_before = next(
        o for o in decision_before.optimizations if o.candidate_id == b_room.id
    ).utility.utility
    b_room_utility_after = next(
        o for o in decision_after.optimizations if o.candidate_id == b_room.id
    ).utility.utility
    # b_room's OWN utility is unaffected by a_room's observation (still the bootstrap value --
    # b_room itself still has zero samples); its STATUS correctly flips to SELECTED once a_room's
    # own utility drops below it -- the computational recommendation moved because a_room's state
    # changed, never because b_room was touched.
    assert b_room_utility_before == b_room_utility_after == 0.5
    b_room_status_after = next(o for o in decision_after.optimizations if o.candidate_id == b_room.id).status
    a_room_status_after = next(o for o in decision_after.optimizations if o.candidate_id == a_room.id).status
    assert b_room_status_after == "SELECTED"
    assert a_room_status_after == "ELIGIBLE_NOT_SELECTED"


# -- counterfactual isolation, against a candidate that already has real evidence ---------------------


def test_counterfactual_isolation_against_candidate_with_existing_evidence(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)
    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])

    real_state = state.session.state
    real_sample_count = _sample_count(state, a_room)
    pre_fingerprint = state.pool.fingerprint()

    explore_output = dispatch(state, "explore", ["999"])
    assert "This branch is hypothetical." in explore_output
    outcome = state.last_counterfactual
    assert outcome is not None

    assert outcome.projected_state.id != real_state.id  # projected state differs from real state
    hypothetical_sample = next(
        s for s in outcome.projected_state.samples[
            resolve_model_state_key(a_room.formulation.id, a_room.property, a_room.target_context)
        ]
        if s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    )
    assert hypothetical_sample.value == 999.0  # hypothetical sample marker exists

    assert state.session.state.id == real_state.id  # source session is unchanged
    assert _sample_count(state, a_room) == real_sample_count  # source state's sample count is unchanged
    assert state.pool.fingerprint() == pre_fingerprint  # no EvidencePool fingerprint change
    assert len(state.session.state_history) == 3  # no real trajectory transition was created (S0, S1, S2 only)

    # hypothetical state cannot enter update()
    real_assessment = state.assessments[-1]
    with pytest.raises(AssertionError, match="hypothetical"):
        update(outcome.projected_state, a_room, real_assessment.result, real_assessment.observation)


# -- EvidencePool integrity: fingerprint stable under read-only commands, changes only on observe -----


def test_evidence_pool_fingerprint_stable_under_read_only_commands(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)
    fp0 = state.pool.fingerprint()

    dispatch(state, "predict", [])  # nothing selected -- still read-only
    assert state.pool.fingerprint() == fp0
    dispatch(state, "decide", [])
    assert state.pool.fingerprint() == fp0
    dispatch(state, "select", [str(_display_index(state, a_room))])
    assert state.pool.fingerprint() == fp0
    dispatch(state, "predict", [])
    assert state.pool.fingerprint() == fp0
    dispatch(state, "explore", ["90"])
    assert state.pool.fingerprint() == fp0

    fp_before_observe = state.pool.fingerprint()
    dispatch(state, "observe", ["80"])
    assert state.pool.fingerprint() != fp_before_observe  # changes only because real evidence was admitted


# -- history/diagnostics: correct candidate correspondence, agreement between the two views -----------


def test_history_and_diagnostics_reference_correct_candidate_ids(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)
    b_room = _find(state, FORMULATION_B, CONTEXT_ROOM)

    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", [str(_display_index(state, b_room))])
    dispatch(state, "observe", ["60"])
    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["100"])

    # history/diagnostics are both scoped to the CURRENTLY selected candidate (a_room) --
    # correspondence is established by candidate_id, never list position (materials.diagnostics'
    # own design, Phase 57). The real trajectory has THREE transitions total (a_room's own
    # observation, then b_room's, then a_room's own again) -- diagnose_transitions reports one
    # diagnostic per real transition regardless of which candidate caused it, so a_room's set has
    # three entries too, with the MIDDLE one (b_room's transition) correctly carrying no a_room-
    # relevant assessment: candidate correspondence is never inferred from list position.
    diagnostic_set = state.history()
    assert diagnostic_set.candidate_id == a_room.id
    assert len(diagnostic_set.diagnostics) == 3
    first, middle, last = diagnostic_set.diagnostics
    assert first.previous_prediction.candidate_id == a_room.id
    assert middle.assessment is None  # b_room's own transition -- not a_room's
    assert middle.delta_predicted_value == 0.0  # a_room's cell is provably unchanged by b_room's observation
    assert last.previous_prediction.candidate_id == a_room.id
    assert first.model_state_key == resolve_model_state_key(a_room.formulation.id, a_room.property, a_room.target_context)
    assert last.model_state_key == first.model_state_key
    assert last.residual_against_previous_prediction == 20.0  # 100 - 80

    history_output = dispatch(state, "history", [])
    diagnostics_output = dispatch(state, "diagnostics", [])
    assert "+20.0" in history_output
    assert "+20.0" in diagnostics_output
    assert "model_state_key" in diagnostics_output
    assert "model_state_key" not in history_output

    # switching selection to b_room and asking again correctly attributes only the MIDDLE
    # transition to b_room's own observation -- never a_room's, proven by candidate_id/assessment,
    # not by trusting display order or list position.
    dispatch(state, "select", [str(_display_index(state, b_room))])
    b_diagnostic_set = state.history()
    assert b_diagnostic_set.candidate_id == b_room.id
    assert len(b_diagnostic_set.diagnostics) == 3
    b_first, b_middle, b_last = b_diagnostic_set.diagnostics
    assert b_first.assessment is None  # a_room's own transition -- not b_room's
    assert b_middle.assessment is not None
    assert b_middle.observation_value == 60.0
    assert b_last.assessment is None  # a_room's own second transition -- not b_room's


# -- historical immutability across multiple candidates -------------------------------------------------


def test_historical_immutability_across_multiple_candidates(state: WorkbenchState):
    a_room = _find(state, FORMULATION_A, CONTEXT_ROOM)
    b_room = _find(state, FORMULATION_B, CONTEXT_ROOM)

    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["80"])
    session_after_a = state.session
    prediction_after_a = session_after_a.predict(a_room).predicted_value
    state_id_after_a = session_after_a.state.id

    dispatch(state, "select", [str(_display_index(state, b_room))])
    dispatch(state, "observe", ["60"])
    session_after_b = state.session
    prediction_after_b_for_a = session_after_b.predict(a_room).predicted_value
    prediction_after_b_for_b = session_after_b.predict(b_room).predicted_value

    dispatch(state, "select", [str(_display_index(state, a_room))])
    dispatch(state, "observe", ["100"])

    # the earlier session objects, held independently, are completely unaffected by later cycles.
    assert session_after_a.state.id == state_id_after_a
    assert session_after_a.predict(a_room).predicted_value == prediction_after_a == 80.0
    assert len(session_after_a.state_history) == 2

    assert session_after_b.predict(a_room).predicted_value == prediction_after_b_for_a == 80.0
    assert session_after_b.predict(b_room).predicted_value == prediction_after_b_for_b == 60.0
    assert len(session_after_b.state_history) == 3

    # and the current, latest session correctly reflects everything since.
    assert state.session.predict(a_room).predicted_value == 90.0
    assert state.session.predict(b_room).predicted_value == 60.0
