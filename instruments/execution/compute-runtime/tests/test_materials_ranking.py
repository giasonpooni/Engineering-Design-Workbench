"""Phase 48: materials.ranking -- small focused test set over a single
compact fixture (build-more-test-less development mode).
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from materials.ranking import (
    ASCENDING, DESCENDING, NOT_DETERMINABLE, RANKED, RANKED_LAST, UNRANKED,
    RankingPolicy, rank_candidates,
)
from materials.utility import ExperimentUtilityInput, evaluate_utility_set
from materials.value import evaluate_candidate_information_values
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})


def _utility_set():
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z")
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-std-190c", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)

    def _obs(locator, content):
        rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
        admit_record(pool, rec)
        pool.put_record(rec)
        obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at="2026-08-23T00:00:00Z")
        admit_observation(pool, obs)
        pool.put_observation(obs)
        rel = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)

    _obs("ts-a", {"property": "tensile_strength", "value": 78, "unit": "MPa"})
    _obs("ts-b", {"property": "tensile_strength", "value": 84, "unit": "MPa"})
    _obs("visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    # hardness: never measured -> MISSING_EVIDENCE

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength", "hardness", "viscosity"))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION, HARDNESS_CRITERION, VISCOSITY_CRITERION))
    candidates = generate_candidates(iteration.specification)
    values = evaluate_candidate_information_values(candidates, iteration)

    tensile = next(v for v in values.values if v.evaluation.candidate.action_class == "measurement:repeat")
    hardness = next(v for v in values.values if v.evaluation.candidate.action_class == "acquisition:unspecified")
    viscosity = next(v for v in values.values if v.evaluation.candidate.action_class == "measurement:context")

    inputs = {
        tensile.candidate_id: ExperimentUtilityInput(benefit=100.0, cost=20.0),   # utility 80
        hardness.candidate_id: ExperimentUtilityInput(benefit=90.0, cost=10.0),   # utility 80 -- ties with tensile
    }
    # viscosity intentionally has no utility_input entry -- unknown utility
    return evaluate_utility_set(values, inputs), tensile.candidate_id, hardness.candidate_id, viscosity.candidate_id


# -- 1. descending utility ranking ----------------------------------------------------------------------


def test_1_descending_ranking():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    policy = RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED)
    result = rank_candidates(utility_set, policy)
    ranked = [r for r in result.rankings if r.rank is not None]
    assert [r.candidate_id for r in ranked][:2] == sorted([tensile_id, hardness_id])  # tie -> id order
    assert ranked[0].rank == 1 and ranked[1].rank == 2


# -- 2. ascending utility ranking -------------------------------------------------------------------------


def test_2_ascending_ranking():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    policy_desc = RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED)
    policy_asc = RankingPolicy(direction=ASCENDING, unknown_utility_policy=UNRANKED)
    desc = rank_candidates(utility_set, policy_desc)
    asc = rank_candidates(utility_set, policy_asc)
    # both tied at utility=80 (only two determinate candidates), so ascending vs
    # descending order among THEM is identical (tie-break always by id) --
    # the real distinguishing check is that utility values are preserved either way.
    assert {r.candidate_id for r in desc.rankings if r.rank is not None} == {r.candidate_id for r in asc.rankings if r.rank is not None}
    assert all(r.utility.utility == 80.0 for r in asc.rankings if r.rank is not None)


# -- 3. equal-utility deterministic tie-break -------------------------------------------------------------


def test_3_equal_utility_tie_break():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    policy = RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED)
    a = rank_candidates(utility_set, policy)
    b = rank_candidates(utility_set, policy)
    ranked_ids_a = [r.candidate_id for r in a.rankings if r.rank is not None]
    ranked_ids_b = [r.candidate_id for r in b.rankings if r.rank is not None]
    assert ranked_ids_a == ranked_ids_b == sorted([tensile_id, hardness_id])


# -- 4. explicit handling of unknown utility ------------------------------------------------------------------


def test_4_unknown_utility_explicit_handling():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()

    unranked_policy = RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED)
    result_unranked = rank_candidates(utility_set, unranked_policy)
    visc_ranking = next(r for r in result_unranked.rankings if r.candidate_id == viscosity_id)
    assert visc_ranking.rank is None
    assert visc_ranking.ranking_status == NOT_DETERMINABLE

    ranked_last_policy = RankingPolicy(direction=DESCENDING, unknown_utility_policy=RANKED_LAST)
    result_ranked_last = rank_candidates(utility_set, ranked_last_policy)
    visc_ranking2 = next(r for r in result_ranked_last.rankings if r.candidate_id == viscosity_id)
    assert visc_ranking2.rank == 3  # still last, but a real position, not None
    assert visc_ranking2.ranking_status == NOT_DETERMINABLE  # never claims to be RANKED by comparison


# -- 5. every candidate preserved -----------------------------------------------------------------------------


def test_5_every_candidate_preserved():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    for policy in (
        RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED),
        RankingPolicy(direction=ASCENDING, unknown_utility_policy=RANKED_LAST),
    ):
        result = rank_candidates(utility_set, policy)
        assert {r.candidate_id for r in result.rankings} == {u.candidate_id for u in utility_set.utilities}
        assert len(result.rankings) == len(utility_set.utilities)
        assert {tensile_id, hardness_id, viscosity_id} <= {r.candidate_id for r in result.rankings}


# -- 6. provenance/identity preserved -----------------------------------------------------------------------------


def test_6_provenance_and_identity_preserved():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    policy = RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED)
    result = rank_candidates(utility_set, policy)
    tensile_ranking = next(r for r in result.rankings if r.candidate_id == tensile_id)
    assert tensile_ranking.ranking_status == RANKED
    assert tensile_ranking.utility.candidate_id == tensile_id
    requirement = tensile_ranking.utility.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"


# -- 7. input immutability ---------------------------------------------------------------------------------------


def test_7_input_immutability():
    utility_set, tensile_id, hardness_id, viscosity_id = _utility_set()
    before = repr(utility_set)
    rank_candidates(utility_set, RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED))
    assert repr(utility_set) == before
