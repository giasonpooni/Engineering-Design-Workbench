"""Phase 67: ExperimentSession operated repeatedly, as a real interactive
experimental object -- three full observe cycles against the same
candidate/cell, a counterfactual inspected before a real observation,
full identity-chain verification per cycle, and historical immutability
across every session/state produced along the way.

Investigation (Phase 67 sec.3), answered directly against the actual
Phase 66 code before writing anything: a caller can already inspect the
current ModelState (`session.state`, a public field), obtain predictions
(`session.predict`), inspect a counterfactual (`session.inspect_
counterfactual`), retain the latest PredictionAssessment externally
(`observe()`'s own return value), generate candidates
(`materials.candidates.generate_candidates(session.iteration.
specification)`), and obtain optimization results
(`materials.optimization.optimize_candidates`, or the fully-automated
`experiment.step.run_experiment_step`) -- all through existing public
composition, none of it awkward enough to justify a new session method.
This file is therefore the ENTIRE Phase 67 deliverable: no production
code changes. `experiment/session.py` is unmodified.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from experiment.session import make_experiment_session
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import resolve_model_state_key, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
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
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)

    session = make_experiment_session(pool, ENGINE, iteration, document_id=doc.id)
    return session, candidate, campaign, entry


def _real_experiment(session, campaign, entry, locator, value):
    """The established admission path -- the caller's job, exactly as
    Phase 44/66 already established: admit a Record, then an
    ExperimentalResult/Observation. Nothing here is fabricated; every
    object comes from the real, unmodified admission API."""
    rec = make_record(document_id=session.document_id, locator=locator, raw_content=f"{value} MPa")
    admit_record(session.pool, rec)
    session.pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-24T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    observation, _relationship = admit_experimental_result(session.pool, result, confidence=1.0)
    return result, observation


def test_repeated_interactive_session_three_cycles():
    session_0, candidate, campaign, entry = _setup()

    # -- counterfactual, inspected BEFORE any real observation exists --------------------------------
    cf_outcome = session_0.inspect_counterfactual(candidate, 999.0)
    assert cf_outcome.projected_state.id != session_0.state.id
    cf_sample = next(iter(cf_outcome.projected_state.samples.values()))[0]
    assert cf_sample.observation_id.startswith("hypothetical:")
    assert session_0.state.id == session_0.state_history[0].id  # source session/state unchanged
    assert len(session_0.state_history) == 1  # the counterfactual never entered the real trajectory
    try:
        update(cf_outcome.projected_state, candidate, *_real_experiment(session_0, campaign, entry, "guard-check", 80))
        assert False, "expected the Phase 61 guard to reject the counterfactual state"
    except AssertionError as e:
        assert "hypothetical" in str(e)
    # the guard-check experiment above admitted a real Record/Observation as a side effect of
    # proving the rejection; it was never folded into any session's state, so it is simply unused
    # evidence sitting in the pool -- harmless, and irrelevant to every assertion below.

    # -- cycle 0: y0 = 80 -----------------------------------------------------------------------------
    prediction_0 = session_0.predict(candidate)
    assert prediction_0.predicted_value is None  # honest: no real samples yet
    assert prediction_0.state_id == session_0.state.id
    assert prediction_0.candidate_id == candidate.id
    expected_key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    assert prediction_0.model_state_key == expected_key

    result_0, observation_0 = _real_experiment(session_0, campaign, entry, "y0", 80)
    assert candidate.id == result_0.candidate_id
    assessment_0, session_1 = session_0.observe(candidate, prediction_0, result_0, observation_0)
    sample_0 = next(iter(session_1.state.samples.values()))[0]
    assert observation_0.id == sample_0.observation_id
    assert assessment_0.prediction.state_id == session_0.state.id  # predecessor, not successor
    assert session_1.state.id != session_0.state.id
    assert assessment_0.residual is None  # observed - undefined predicted -- honestly undetermined
    assert assessment_0.observed_value == 80.0

    # -- cycle 1: y1 = 90 -----------------------------------------------------------------------------
    prediction_1 = session_1.predict(candidate)
    assert prediction_1.predicted_value == 80.0
    assert prediction_1.state_id == session_1.state.id
    assert prediction_1.candidate_id == candidate.id
    assert prediction_1.model_state_key == expected_key

    result_1, observation_1 = _real_experiment(session_1, campaign, entry, "y1", 90)
    assert candidate.id == result_1.candidate_id
    assessment_1, session_2 = session_1.observe(candidate, prediction_1, result_1, observation_1)
    sample_1 = next(s for s in session_2.state.samples[expected_key] if s.observation_id == observation_1.id)
    assert observation_1.id == sample_1.observation_id
    assert assessment_1.prediction.state_id == session_1.state.id
    assert session_2.state.id != session_1.state.id
    assert assessment_1.residual == 90.0 - 80.0 == 10.0  # sign preserved, never absolute/normalized
    assert assessment_1.absolute_residual == 10.0

    # -- cycle 2: y2 = 100 ----------------------------------------------------------------------------
    prediction_2 = session_2.predict(candidate)
    assert prediction_2.predicted_value == 85.0  # mean([80, 90])
    # sample variance, divisor n-1: ((80-85)^2 + (90-85)^2) / 1 = 50
    assert prediction_2.uncertainty == 50.0
    assert prediction_2.state_id == session_2.state.id
    assert prediction_2.candidate_id == candidate.id
    assert prediction_2.model_state_key == expected_key

    result_2, observation_2 = _real_experiment(session_2, campaign, entry, "y2", 100)
    assert candidate.id == result_2.candidate_id
    assessment_2, session_3 = session_2.observe(candidate, prediction_2, result_2, observation_2)
    sample_2 = next(s for s in session_3.state.samples[expected_key] if s.observation_id == observation_2.id)
    assert observation_2.id == sample_2.observation_id
    assert assessment_2.prediction.state_id == session_2.state.id
    assert session_3.state.id != session_2.state.id
    assert assessment_2.residual == 100.0 - 85.0 == 15.0  # positive, not clamped, not normalized
    assert assessment_2.absolute_residual == 15.0

    # a fourth prediction, from the successor of the last cycle, for good measure.
    prediction_3 = session_3.predict(candidate)
    assert prediction_3.predicted_value == 90.0  # mean([80, 90, 100])
    # sample variance, divisor n-1 -- derived here rather than read off
    # the implementation, so the test can disagree with the code
    expected_uncertainty = ((80 - 90) ** 2 + (90 - 90) ** 2 + (100 - 90) ** 2) / 2
    assert expected_uncertainty == 100.0
    assert abs(prediction_3.uncertainty - expected_uncertainty) < 1e-9

    # -- residuals are never reinterpreted -------------------------------------------------------------
    for assessment in (assessment_0, assessment_1, assessment_2):
        assert not hasattr(assessment, "quality")
        assert not hasattr(assessment, "confidence")
        assert not hasattr(assessment, "significance")
    assert assessment_1.residual > 0 and assessment_2.residual > 0  # both positive here, signs intact
    assert isinstance(assessment_1.residual, float) and assessment_1.residual == 10.0  # not a percentage/ratio

    # -- historical immutability across every session/state produced -----------------------------------
    original_ids = {
        0: session_0.state.id, 1: session_1.state.id, 2: session_2.state.id, 3: session_3.state.id,
    }
    # re-run predictions against every historical state; each must reproduce its original values.
    assert session_0.predict(candidate).predicted_value is None
    assert session_1.predict(candidate).predicted_value == 80.0
    assert session_2.predict(candidate).predicted_value == 85.0
    assert session_3.predict(candidate).predicted_value == 90.0
    # the sessions/states themselves are untouched by any of the later cycles or the re-predictions above.
    assert session_0.state.id == original_ids[0]
    assert session_1.state.id == original_ids[1]
    assert session_2.state.id == original_ids[2]
    assert session_3.state.id == original_ids[3]
    assert session_1.state_history == (session_0.state, session_1.state)
    assert session_2.state_history == (session_0.state, session_1.state, session_2.state)
    assert session_3.state_history == (session_0.state, session_1.state, session_2.state, session_3.state)
    # session_0 itself was never mutated by any later cycle -- it still has exactly one history entry.
    assert session_0.state_history == (session_0.state,)
