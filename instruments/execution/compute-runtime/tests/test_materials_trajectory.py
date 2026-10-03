"""Phase 56: materials.trajectory -- model-state trajectory and
prediction evolution. Small focused test set (build-more-test-less
mode): trajectory construction over multiple immutable states,
deterministic lineage (including rejection of an invalid sequence),
prediction evolution, residual preservation, historical-state
immutability, deterministic trajectory ordering, information-value
evolution via existing composition, and PYTHONHASHSEED determinism.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from materials.assessment import assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.information import ESTIMATED, NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import (
    EMPTY_MODEL_STATE, ModelStateInformationValueModel, make_model_state, predict, update,
)
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.trajectory import compare_predictions, make_model_state_trajectory, prediction_evolution
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
    Phase 56 sec.9's worked shape. Returns everything needed to build a
    trajectory and its prediction evolution."""
    pool, doc, iteration, candidate, campaign, entry = _setup()

    prediction0 = predict(EMPTY_MODEL_STATE, candidate)
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    assessment0 = assess(prediction0, result1, obs1)  # predicted_value is None -> residual None
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    prediction1 = predict(state1, candidate)
    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    assessment1 = assess(prediction1, result2, obs2)  # 90 - 80 = +10
    state2 = update(state1, candidate, result2, obs2)

    return pool, iteration, candidate, state1, state2, assessment0, assessment1


# -- 1. trajectory over multiple immutable states ----------------------------------------------------------


def test_1_trajectory_over_multiple_immutable_states():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()
    before_empty_repr = repr(EMPTY_MODEL_STATE)
    before_state1_repr = repr(state1)

    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    assert [e.position for e in trajectory.entries] == [0, 1, 2]
    assert [e.state_id for e in trajectory.entries] == [EMPTY_MODEL_STATE.id, state1.id, state2.id]

    # building a trajectory reads states, never mutates them.
    assert repr(EMPTY_MODEL_STATE) == before_empty_repr
    assert repr(state1) == before_state1_repr


# -- 2. deterministic lineage, including rejection of an invalid sequence ------------------------------------


def test_2_deterministic_lineage_and_rejection():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()

    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    assert trajectory.entries[0].predecessor_state_id is None
    assert trajectory.entries[1].predecessor_state_id == EMPTY_MODEL_STATE.id
    assert trajectory.entries[2].predecessor_state_id == state1.id

    # A sequence that is not a valid update() chain (samples missing
    # between predecessor and successor) is actively rejected.
    try:
        make_model_state_trajectory((state1, EMPTY_MODEL_STATE))
        assert False, "expected a ValueError for an invalid (non-monotonic) state sequence"
    except ValueError as e:
        assert "not a valid successor" in str(e)


# -- 3. prediction evolution (and Phase 56 sec.9's G(S_t,x) != G(S_(t+1),x)) ------------------------------


def test_3_prediction_evolution():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))

    steps = prediction_evolution(trajectory, candidate, (assessment0, assessment1))
    assert len(steps) == 3
    assert steps[0].prediction.predicted_value is None
    assert steps[1].prediction.predicted_value == 80.0
    assert steps[2].prediction.predicted_value == 85.0
    assert steps[2].prediction.uncertainty == 50.0  # sample variance (n-1) of [80, 90]

    # each step's prediction remains tied to ITS OWN state -- never the
    # next one.
    assert steps[0].prediction.state_id == EMPTY_MODEL_STATE.id
    assert steps[1].prediction.state_id == state1.id
    assert steps[2].prediction.state_id == state2.id

    # compare_predictions: the purely mathematical delta between two
    # steps, no interpretation attached.
    delta = compare_predictions(steps[1].prediction, steps[2].prediction)
    assert delta.delta_predicted_value == 5.0  # 85 - 80
    assert delta.delta_uncertainty is None  # uncertainty was None at step 1 -- never guessed


# -- 4. residual preservation --------------------------------------------------------------------------------


def test_4_residual_preservation():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    steps = prediction_evolution(trajectory, candidate, (assessment0, assessment1))

    assert steps[0].observed_value == 80.0
    assert steps[0].residual is None  # prediction had no predicted_value -- honestly undetermined
    assert steps[1].observed_value == 90.0
    assert steps[1].residual == 10.0  # 90 - 80, sign preserved
    assert steps[2].observed_value is None  # no assessment supplied for S2
    assert steps[2].residual is None


# -- 5. historical-state immutability -------------------------------------------------------------------------


def test_5_historical_state_immutability():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()
    before_state1_repr = repr(state1)
    before_state2_repr = repr(state2)

    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))
    prediction_evolution(trajectory, candidate, (assessment0, assessment1))

    assert repr(state1) == before_state1_repr
    assert repr(state2) == before_state2_repr
    assert predict(state1, candidate).predicted_value == 80.0  # unchanged by trajectory analysis
    assert predict(state2, candidate).uncertainty == 50.0  # sample variance (n-1) of [80, 90]


# -- 6. deterministic trajectory ordering -------------------------------------------------------------------


def test_6_deterministic_trajectory_ordering():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()

    # An independently-rebuilt state1 that merely shares content (same
    # .id, different insertion order, different Python object) produces
    # an equal trajectory.
    key = next(iter(state1.samples))
    rebuilt_state1 = make_model_state({key: tuple(reversed(state1.samples[key]))})
    assert rebuilt_state1.id == state1.id
    assert rebuilt_state1 is not state1

    trajectory_a = make_model_state_trajectory((EMPTY_MODEL_STATE, state1))
    trajectory_b = make_model_state_trajectory((EMPTY_MODEL_STATE, rebuilt_state1))
    assert [e.position for e in trajectory_a.entries] == [e.position for e in trajectory_b.entries]
    assert [e.state_id for e in trajectory_a.entries] == [e.state_id for e in trajectory_b.entries]
    assert [e.predecessor_state_id for e in trajectory_a.entries] == [e.predecessor_state_id for e in trajectory_b.entries]


# -- 7. information-value evolution via EXISTING composition (Phase 56 sec.8: no new primitive needed) --------


def test_7_information_value_evolution_via_existing_composition():
    pool, iteration, candidate, state1, state2, assessment0, assessment1 = _build_s0_s1_s2()
    trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))

    estimates = [
        estimate_information_value(candidate, iteration, ModelStateInformationValueModel(entry.state))
        for entry in trajectory.entries
    ]
    assert estimates[0].estimate_status == NOT_DETERMINABLE  # S0: zero samples
    assert estimates[1].estimate_status == NOT_DETERMINABLE  # S1: one sample, no defined variance
    assert estimates[2].estimate_status == ESTIMATED
    assert estimates[2].estimate == 50.0  # sample variance (n-1) of [80, 90]


# -- 8. deterministic behavior across PYTHONHASHSEED -----------------------------------------------------------


def test_8_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.types import make_referent\n"
        "from materials.candidates import make_action_candidate\n"
        "from materials.model_state import EMPTY_MODEL_STATE, Sample, make_model_state, resolve_model_state_key\n"
        "from materials.trajectory import compare_predictions, make_model_state_trajectory, prediction_evolution\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "candidate = make_action_candidate(action_class='measurement:repeat', requirement_ids=('r1',), "
        "formulation=f1, property='tensile_strength', role='OBSERVED', target_context={})\n"
        "key = resolve_model_state_key(f1.id, 'tensile_strength', {})\n"
        "state1 = make_model_state({key: (Sample(80.0, 'o1'),)})\n"
        "state2 = make_model_state({key: (Sample(80.0, 'o1'), Sample(90.0, 'o2'))})\n"
        "trajectory = make_model_state_trajectory((EMPTY_MODEL_STATE, state1, state2))\n"
        "steps = prediction_evolution(trajectory, candidate)\n"
        "delta = compare_predictions(steps[1].prediction, steps[2].prediction)\n"
        "print([e.state_id for e in trajectory.entries], [e.predecessor_state_id for e in trajectory.entries], "
        "[s.prediction.predicted_value for s in steps], [s.prediction.uncertainty for s in steps], "
        "delta.delta_predicted_value, delta.delta_uncertainty)\n"
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
    assert len(outputs) == 1, f"trajectory results differed across PYTHONHASHSEED values: {outputs}"
