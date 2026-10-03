"""Phase 57: materials.diagnostics -- state transition diagnostics.
Small focused test set (build-more-test-less mode): predecessor/
successor identity, signed prediction delta, uncertainty delta, residual
linkage, historical-state preservation, multiple trajectory entries,
deterministic output, and PYTHONHASHSEED determinism.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from materials.assessment import assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.diagnostics import diagnose_transitions
from materials.evaluation import evaluate_candidates
from materials.information import ESTIMATED, NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, ModelStateInformationValueModel, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.trajectory import make_model_state_trajectory
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
    doc = make_document(source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-24T00:00:00Z")
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

    return pool, doc, iteration, candidate, campaign, entry


def _admit_result(pool, doc, campaign, entry, locator, value):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-24T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    observation, _ = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


def _build_s0_s1_s2():
    """S0 (empty) -> S1 (samples=[80]) -> S2 (samples=[80,90]) --
    same worked shape as Phase 56's own fixture."""
    pool, doc, iteration, candidate, campaign, entry = _setup()

    prediction0 = predict(EMPTY_MODEL_STATE, candidate)
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    assessment0 = assess(prediction0, result1, obs1)  # predicted_value None -> residual None
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    prediction1 = predict(state1, candidate)
    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    assessment1 = assess(prediction1, result2, obs2)  # 90 - 80 = +10
    state2 = update(state1, candidate, result2, obs2)

    return pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2


# -- 1. correct predecessor/successor identity ----------------------------------------------------------


def test_1_predecessor_successor_identity():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))

    result = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    assert result.candidate_id == candidate.id
    assert len(result.diagnostics) == 2

    d0, d1 = result.diagnostics
    assert d0.predecessor_state_id == EMPTY_MODEL_STATE.id
    assert d0.successor_state_id == state1.id
    assert d1.predecessor_state_id == state1.id
    assert d1.successor_state_id == state2.id
    assert d0.candidate_id == d1.candidate_id == candidate.id


# -- 2/3. correct signed prediction delta + uncertainty delta ---------------------------------------------


def test_2_3_signed_prediction_and_uncertainty_delta():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    result = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    d0, d1 = result.diagnostics

    # S0 -> S1: predicted_value goes None -> 80.0 -- no defined delta.
    assert d0.previous_prediction.predicted_value is None
    assert d0.new_prediction.predicted_value == 80.0
    assert d0.delta_predicted_value is None  # never guessed from a None predecessor
    assert d0.delta_uncertainty is None

    # S1 -> S2: predicted_value 80.0 -> 85.0 (delta +5.0); uncertainty
    # None -> 25.0 (delta undefined -- the predecessor had none).
    assert d1.previous_prediction.predicted_value == 80.0
    assert d1.new_prediction.predicted_value == 85.0
    assert d1.delta_predicted_value == 5.0
    assert d1.previous_prediction.uncertainty is None
    assert d1.new_prediction.uncertainty == 50.0  # sample variance (n-1) of [80, 90]
    assert d1.delta_uncertainty is None


# -- 4. correct residual linkage -------------------------------------------------------------------------


def test_4_residual_linkage():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    result = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    d0, d1 = result.diagnostics

    # d0's residual is assessment0's -- the observation that CAUSED
    # S0 -> S1, not assessment1's (which caused S1 -> S2).
    assert d0.assessment is assessment0
    assert d0.observation_value == 80.0
    assert d0.residual_against_previous_prediction is None  # predicted_value was None at S0
    assert d0.absolute_residual is None

    assert d1.assessment is assessment1
    assert d1.observation_value == 90.0
    assert d1.residual_against_previous_prediction == 10.0
    assert d1.absolute_residual == 10.0
    assert d1.assessment.observation.id == obs2.id  # observation identity preserved, not reconstructed


# -- 5. historical-state preservation --------------------------------------------------------------------


def test_5_historical_state_preservation():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    before_state1_repr = repr(state1)
    before_state2_repr = repr(state2)

    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    diagnose_transitions(trajectory, candidate, (assessment0, assessment1))

    assert repr(state1) == before_state1_repr
    assert repr(state2) == before_state2_repr
    assert predict(state1, candidate).predicted_value == 80.0
    assert predict(state2, candidate).uncertainty == 50.0  # sample variance (n-1) of [80, 90]


# -- 6. multiple trajectory entries (3 states -> 2 diagnostics, correctly ordered) --------------------------


def test_6_multiple_trajectory_entries():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    result = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    assert [ (d.predecessor_state_id, d.successor_state_id) for d in result.diagnostics ] == [
        (EMPTY_MODEL_STATE.id, state1.id), (state1.id, state2.id),
    ]

    # A single-state trajectory has no transition to diagnose.
    single = make_model_state_trajectory((EMPTY_MODEL_STATE,))
    assert diagnose_transitions(single, candidate, (assessment0,)).diagnostics == ()


# -- 7. deterministic output; information-value coexistence (sec.7, existing machinery only) -----------------


def test_7_deterministic_and_information_value_coexistence():
    pool, iteration, candidate, state1, state2, assessment0, assessment1, obs2 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))

    a = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    b = diagnose_transitions(trajectory, candidate, (assessment0, assessment1))
    assert a == b  # equal dataclasses for equal inputs

    # No new information-value machinery -- the existing Phase 50/52
    # composition, applied to the SAME states a diagnostic already
    # names, coexists without conflict.
    d0, d1 = a.diagnostics
    before = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state1))
    after = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state2))
    assert before.information_value.candidate_id == d1.candidate_id
    assert before.estimate_status == NOT_DETERMINABLE
    assert after.estimate_status == ESTIMATED
    assert after.estimate == 50.0  # sample variance (n-1) of [80, 90]


# -- 8. deterministic behavior across PYTHONHASHSEED -----------------------------------------------------------


def test_8_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.types import make_referent\n"
        "from materials.candidates import make_action_candidate\n"
        "from materials.diagnostics import diagnose_transitions\n"
        "from materials.model_state import EMPTY_MODEL_STATE, Sample, make_model_state, resolve_model_state_key\n"
        "from materials.trajectory import make_model_state_trajectory\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "candidate = make_action_candidate(action_class='measurement:repeat', requirement_ids=('r1',), "
        "formulation=f1, property='tensile_strength', role='OBSERVED', target_context={})\n"
        "key = resolve_model_state_key(f1.id, 'tensile_strength', {})\n"
        "state1 = make_model_state({key: (Sample(80.0, 'o1'),)})\n"
        "state2 = make_model_state({key: (Sample(80.0, 'o1'), Sample(90.0, 'o2'))})\n"
        "trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))\n"
        "result = diagnose_transitions(trajectory, candidate)\n"
        "print([(d.predecessor_state_id, d.successor_state_id, d.delta_predicted_value, d.delta_uncertainty) "
        "for d in result.diagnostics])\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"diagnostics differed across PYTHONHASHSEED values: {outputs}"
