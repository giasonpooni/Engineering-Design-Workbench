"""Phase 59: materials.ensemble -- counterfactual state ensembles and
expected information value. Small focused test set (build-more-test-
less mode): multiple counterfactual outcomes, deterministic branch
identities, branch isolation, prediction-after-branch, information-
value-per-branch, absent probabilities keeping the expected value
NOT_DETERMINABLE, explicitly supplied probabilities producing a real
expected value, source-state immutability, and PYTHONHASHSEED
determinism.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.ensemble import (
    ESTIMATED, NOT_DETERMINABLE, evaluate_counterfactual_information_value, make_counterfactual_set,
    project_outcome,
)
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, predict, update
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


# -- 1/2/3. multiple outcomes, deterministic branch identities, branch isolation --------------------------


def test_1_2_3_multiple_outcomes_deterministic_and_isolated():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)  # one real sample: [80]

    o1 = project_outcome(state1, candidate, 80.0)
    o2 = project_outcome(state1, candidate, 85.0)
    o3 = project_outcome(state1, candidate, 90.0)
    branch_set = make_counterfactual_set((o1, o2, o3))

    assert branch_set.source_state_id == state1.id
    assert branch_set.candidate_id == candidate.id
    assert len({o.projected_state_id for o in branch_set.outcomes}) == 3  # distinct branches

    # deterministic: rebuilding the same branch twice gives the same id.
    o1_again = project_outcome(state1, candidate, 80.0)
    assert o1.projected_state_id == o1_again.projected_state_id

    # branch isolation: each branch's projected_state reflects ONLY its
    # own hypothetical value on top of state1's existing [80] sample --
    # never another branch's hypothetical.
    assert predict(o1.projected_state, candidate).predicted_value == 80.0  # mean([80, 80])
    assert predict(o2.projected_state, candidate).predicted_value == 82.5  # mean([80, 85])
    assert predict(o3.projected_state, candidate).predicted_value == 85.0  # mean([80, 90])


# -- 4. prediction-after-branch (and its delta against the source state's own prediction) -------------------


def test_4_prediction_after_branch():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    outcome = project_outcome(state1, candidate, 90.0)
    assert outcome.prediction_after.predicted_value == 85.0  # mean([80, 90])
    assert outcome.prediction_after.uncertainty == 50.0  # sample variance (n-1) of [80, 90]
    assert outcome.prediction_after.state_id == outcome.projected_state_id

    # delta reuses materials.trajectory.compare_predictions exactly.
    assert outcome.delta.from_state_id == state1.id
    assert outcome.delta.to_state_id == outcome.projected_state_id
    assert outcome.delta.delta_predicted_value == 5.0  # 85 - 80
    assert outcome.delta.delta_uncertainty is None  # source had no defined uncertainty


# -- 5/6. information-value-per-branch; absent probabilities -> NOT_DETERMINABLE ---------------------------


def test_5_6_branch_information_values_and_missing_probability():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    o80 = project_outcome(state1, candidate, 80.0)  # variance 0.0
    o90 = project_outcome(state1, candidate, 90.0)  # variance 50.0 -- no probability supplied
    branch_set = make_counterfactual_set((o80, o90))

    result = evaluate_counterfactual_information_value(branch_set, candidate, iteration)
    assert len(result.branch_information_values) == 2
    assert result.branch_information_values[0].estimate == 0.0
    assert result.branch_information_values[1].estimate == 50.0  # sample variance (n-1) of [80, 90]
    assert result.branch_information_values[0].estimate_status == ESTIMATED

    # no probabilities were supplied -- the expected value stays honestly undetermined.
    assert result.expected_information_value is None
    assert result.expected_information_value_status == NOT_DETERMINABLE


# -- 7. explicitly supplied probabilities -> expected information value computed -----------------------------


def test_7_expected_information_value_with_supplied_probabilities():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    o80 = project_outcome(state1, candidate, 80.0, probability=0.5)   # IV = 0.0
    o90 = project_outcome(state1, candidate, 90.0, probability=0.5)   # IV = 50.0
    branch_set = make_counterfactual_set((o80, o90))

    result = evaluate_counterfactual_information_value(branch_set, candidate, iteration)
    assert result.expected_information_value_status == ESTIMATED
    assert result.expected_information_value == 25.0  # 0.5*0.0 + 0.5*50.0

    # a set with even ONE missing probability stays NOT_DETERMINABLE --
    # never a silent partial sum.
    o95 = project_outcome(state1, candidate, 95.0)  # no probability
    partial_set = make_counterfactual_set((o80, o90, o95))
    partial_result = evaluate_counterfactual_information_value(partial_set, candidate, iteration)
    assert partial_result.expected_information_value is None
    assert partial_result.expected_information_value_status == NOT_DETERMINABLE


# -- 8. source-state immutability; mixed-source rejection -----------------------------------------------------


def test_8_source_state_immutability_and_mixed_source_rejection():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    before_state1_repr = repr(state1)
    before_empty_repr = repr(EMPTY_MODEL_STATE)

    o90 = project_outcome(state1, candidate, 90.0)
    o95 = project_outcome(state1, candidate, 95.0)
    make_counterfactual_set((o90, o95))

    assert repr(state1) == before_state1_repr
    assert repr(EMPTY_MODEL_STATE) == before_empty_repr
    assert predict(state1, candidate).predicted_value == 80.0  # unchanged

    # a set mixing outcomes from two different source states is rejected.
    o_from_empty = project_outcome(EMPTY_MODEL_STATE, candidate, 80.0)
    try:
        make_counterfactual_set((o90, o_from_empty))
        assert False, "expected a ValueError for a mixed-source-state set"
    except ValueError as e:
        assert "same source_state_id" in str(e)


# -- 9. deterministic behavior across PYTHONHASHSEED -----------------------------------------------------------


def test_9_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.types import make_referent\n"
        "from materials.candidates import make_action_candidate\n"
        "from materials.ensemble import make_counterfactual_set, project_outcome\n"
        "from materials.model_state import EMPTY_MODEL_STATE\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "candidate = make_action_candidate(action_class='measurement:repeat', requirement_ids=('r1',), "
        "formulation=f1, property='tensile_strength', role='OBSERVED', target_context={})\n"
        "o1 = project_outcome(EMPTY_MODEL_STATE, candidate, 80.0, probability=0.3)\n"
        "o2 = project_outcome(EMPTY_MODEL_STATE, candidate, 90.0, probability=0.7)\n"
        "branch_set = make_counterfactual_set((o1, o2))\n"
        "print([o.projected_state_id for o in branch_set.outcomes], "
        "[o.prediction_after.predicted_value for o in branch_set.outcomes])\n"
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
    assert len(outputs) == 1, f"ensemble results differed across PYTHONHASHSEED values: {outputs}"
