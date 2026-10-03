"""Phase 37: materials.candidates -- deterministic generic
information-acquisition candidate generation over an already-computed
ExperimentSpecification (Phase 35), exercised against the same
Phase 30-35 workload: F1 (measurement conflict + condition-dependent
viscosity), F2 (clean FAIL), F3 (model disagreement over one
observation), F4 (clean PASS + measurement without prediction), F5
(prediction without a matching measurement), F6 (no process
relationship).
"""

import dataclasses

import pytest

from evidence.admission import (
    admit_claimed_relationship, admit_derived_grounding, admit_derived_value,
    admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_derived_grounding, make_derived_value,
    make_document, make_observation, make_record, make_referent, make_source,
)
from materials.audit import audit_program
from materials.candidates import (
    generate_candidates, make_action_candidate, requirement_identity,
)
from materials.decision import make_criterion, evaluate_program
from materials.experiment import analyze_experiment_gaps
from materials.program import make_material_program_query, analyze_program
from materials.specification import (
    EITHER, OBSERVED, ExperimentSpecification, specify_experiment_requirements,
)
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
MODULUS_CRITERION = make_criterion("modulus", ">=", 2.7)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


def _base(order="normal"):
    pool = EvidencePool()
    qc_lab = make_source(kind="lab_notebook", name="Internal QC Lab")
    third_party = make_source(kind="external_report", name="Third-Party Test Lab")
    for s in ((qc_lab, third_party) if order == "normal" else (third_party, qc_lab)):
        pool.put_source(s)

    doc = make_document(source_id=qc_lab.id, raw_content="QC panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z")
    tp_doc = make_document(source_id=third_party.id, raw_content="Third-party verification", retrieval_method="pdf_ingest", retrieved_at="2026-08-23T00:00:00Z")
    for d in (doc, tp_doc):
        admit_document(pool, d)
        pool.put_document(d)

    process_std = make_referent(natural_key="process-std-190c", kind="process")
    formulations = {k: make_referent(natural_key=f"formulation-{k}", kind="formulation") for k in ("f1", "f2", "f3", "f4", "f5", "f6")}
    all_refs = [process_std] + list(formulations.values())
    for ref in (all_refs if order == "normal" else list(reversed(all_refs))):
        admit_referent(pool, ref)
        pool.put_referent(ref)

    return pool, doc, tp_doc, process_std, formulations


def _add_obs(pool, document, formulation, process, locator, content, extracted_at="2026-08-23T00:00:00Z"):
    rec = make_record(document_id=document.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at=extracted_at)
    admit_observation(pool, obs)
    pool.put_observation(obs)
    if process is not None:
        rel = make_claimed_relationship(from_referent_id=formulation.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)
    return obs


def _add_pred(pool, formulation, obs, method, content, confidence=0.85, derived_at="2026-08-23T01:00:00Z"):
    dv = make_derived_value(derived_from=[obs.id], method=method, content=content, confidence=confidence, derived_at=derived_at)
    admit_derived_value(pool, dv)
    pool.put_derived_value(dv)
    g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[formulation.id])
    admit_derived_grounding(pool, g)
    pool.put_derived_grounding(g)
    return dv


def _workload(order="normal"):
    pool, doc, tp_doc, process_std, f = _base(order)
    obs = {}

    obs["f1_ts_qc"] = _add_obs(pool, doc, f["f1"], process_std, "f1-ts-qc", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs["f1_ts_tp"] = _add_obs(pool, tp_doc, f["f1"], process_std, "f1-ts-tp", {"property": "tensile_strength", "value": 79, "unit": "MPa"}, extracted_at="2026-08-23T00:30:00Z")
    dv_f1_a = _add_pred(pool, f["f1"], obs["f1_ts_qc"], "model:A", {"property": "tensile_strength", "predicted_value": 80, "unit": "MPa"})
    dv_f1_b = _add_pred(pool, f["f1"], obs["f1_ts_tp"], "model:B", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    obs["f1_visc40"] = _add_obs(pool, doc, f["f1"], process_std, "f1-visc40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    obs["f2_ts"] = _add_obs(pool, doc, f["f2"], process_std, "f2-ts", {"property": "tensile_strength", "value": 79, "unit": "MPa"})

    obs["f3_ts"] = _add_obs(pool, doc, f["f3"], process_std, "f3-ts", {"property": "tensile_strength", "value": 86, "unit": "MPa"})
    dv_f3_a = _add_pred(pool, f["f3"], obs["f3_ts"], "model:A", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    dv_f3_b = _add_pred(pool, f["f3"], obs["f3_ts"], "model:B", {"property": "tensile_strength", "predicted_value": 89, "unit": "MPa"})

    obs["f4_ts"] = _add_obs(pool, doc, f["f4"], process_std, "f4-ts", {"property": "tensile_strength", "value": 81, "unit": "MPa"})
    obs["f4_mod"] = _add_obs(pool, doc, f["f4"], process_std, "f4-mod", {"property": "modulus", "value": 3.0, "unit": "GPa"})

    obs["f5_mod"] = _add_obs(pool, doc, f["f5"], process_std, "f5-mod", {"property": "modulus", "value": 2.9, "unit": "GPa"})
    dv_f5 = _add_pred(pool, f["f5"], obs["f5_mod"], "model:A", {"property": "tensile_strength", "predicted_value": 82, "unit": "MPa"})

    obs["f6_ts"] = _add_obs(pool, doc, f["f6"], None, "f6-ts", {"property": "tensile_strength", "value": 90, "unit": "MPa"})

    return pool, f, process_std, obs, dict(dv_f1_a=dv_f1_a, dv_f1_b=dv_f1_b, dv_f3_a=dv_f3_a, dv_f3_b=dv_f3_b, dv_f5=dv_f5)


def _specify_for(pool, formulation_keys, criteria, properties=None):
    if properties is None:
        properties = tuple(sorted({c.property for c in criteria}))
    query = make_material_program_query([f"formulation-{k}" for k in formulation_keys], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    return specify_experiment_requirements(gaps)


# -- 1. one requirement -> one candidate --------------------------------------------------------


def test_1_one_requirement_one_candidate():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (HARDNESS_CRITERION,))
    cs = generate_candidates(spec)
    assert len(cs.candidates) == 1
    c = cs.candidates[0]
    assert c.action_class == "acquisition:unspecified"
    assert c.role == EITHER
    assert c.property == "hardness"
    assert c.formulation.natural_key == "formulation-f1"


# -- 2. multiple requirements -> deterministic generation ---------------------------------------


def test_2_multiple_requirements_deterministic_generation():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION, VISCOSITY_CRITERION))
    cs = generate_candidates(spec)
    action_classes = sorted(c.action_class for c in cs.candidates)
    # tensile_strength: observed conflict ("measurement:repeat");
    # viscosity: observed incomparable context ("measurement:context")
    # AND no prediction was ever made for viscosity at all
    # ("model_validation:unspecified", MEASUREMENT_WITHOUT_PREDICTION).
    assert action_classes == ["measurement:context", "measurement:repeat", "model_validation:unspecified"]


# -- 3. one candidate targeting multiple requirements --------------------------------------------


def test_3_one_candidate_targets_multiple_requirements():
    """Two criteria for the SAME property, both landing F1's observed
    tensile evidence in CONFLICTING_EVIDENCE (82 vs 79 straddles both
    target=80 and target=81) -- everything a candidate action would need
    (formulation, property, role, action_class, criterion CONTEXT,
    evidence, provenance) is identical; only the criterion threshold
    differs, and a criterion threshold never changes what would need to
    be measured. This is the one composition case the current
    EvidenceRequirement data model genuinely supports without inventing
    a "measured together" fact -- see the module docstring."""
    pool, f, process_std, obs, dv = _workload()
    strict = make_criterion("tensile_strength", ">=", 81)
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION, strict), properties=("tensile_strength",))
    assert len(spec.entries) == 2  # two distinct EvidenceGaps, one per criterion
    cs = generate_candidates(spec)
    matching = [c for c in cs.candidates if c.action_class == "measurement:repeat"]
    assert len(matching) == 1  # merged into ONE candidate
    assert len(matching[0].requirement_ids) == 2  # targeting both requirements


# -- 4. multiple candidates targeting one requirement: not expressible ---------------------------


def test_4_action_class_is_a_pure_function_of_category_and_role():
    """Phase 37 sec.12 item 4 asks for "multiple candidates targeting
    one requirement, ONLY if the current requirement semantics genuinely
    justify multiple distinct generic actions." They do not:
    `_action_class_for` (exercised here indirectly, through every
    reachable (category, role) combination in this workload) is a pure,
    deterministic function -- the SAME single action_class every time
    for the same (category, role) pair. Nothing in EvidenceRequirement
    distinguishes two different ways to resolve the same single gap, so
    generate_candidates never produces more than one candidate for a
    requirement considered alone. Documented here as a finding, not
    invented."""
    pool, f, process_std, obs, dv = _workload()
    strict = make_criterion("tensile_strength", ">=", 85)
    specs = (
        _specify_for(pool, ["f1"], (TENSILE_CRITERION, VISCOSITY_CRITERION)),
        _specify_for(pool, ["f3"], (strict,)),
        _specify_for(pool, ["f1"], (HARDNESS_CRITERION,)),
        _specify_for(pool, ["f4"], (MODULUS_CRITERION,)),
        _specify_for(pool, ["f5"], (TENSILE_CRITERION,)),
    )
    seen = {}
    for spec in specs:
        for entry in spec.entries:
            for requirement in entry.requirements:
                key = (requirement.category, requirement.role)
                cs = generate_candidates(ExperimentSpecification(
                    process_natural_key=spec.process_natural_key, gaps=spec.gaps, entries=(entry,),
                ))
                targeting = [c for c in cs.candidates if requirement_identity(requirement) in c.requirement_ids]
                assert len(targeting) == 1, f"requirement {key} produced {len(targeting)} candidates, not exactly 1"
                action_class = targeting[0].action_class
                if key in seen:
                    assert seen[key] == action_class
                else:
                    seen[key] = action_class
    # Document exactly which (category, role) combinations this workload reaches.
    assert len(seen) >= 5


# -- 5. candidate identity is stable --------------------------------------------------------------


def test_5_candidate_identity_stable():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1", "f2", "f3"], (TENSILE_CRITERION,))
    ids_a = [c.id for c in generate_candidates(spec).candidates]
    ids_b = [c.id for c in generate_candidates(spec).candidates]
    assert ids_a == ids_b


# -- 6. candidate identity independent of mapping key order ----------------------------------------


def test_6_candidate_identity_independent_of_context_key_order():
    pool, f, process_std, obs, dv = _workload()
    crit_a = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    crit_b = make_criterion("viscosity", "<=", 950, context={"temperature_unit": "C", "temperature": 25, "unit": "mPa.s"})
    spec_a = _specify_for(pool, ["f1"], (crit_a,))
    spec_b = _specify_for(pool, ["f1"], (crit_b,))
    ids_a = sorted(c.id for c in generate_candidates(spec_a).candidates)
    ids_b = sorted(c.id for c in generate_candidates(spec_b).candidates)
    assert ids_a == ids_b


# -- 7. candidate identity excludes non-identity descriptive metadata ------------------------------


def test_7_candidate_identity_excludes_descriptive_metadata():
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    c1 = make_action_candidate(
        action_class="measurement:repeat", requirement_ids=("r1", "r2"), formulation=f1,
        property="tensile_strength", role=OBSERVED, target_context={}, existing_evidence_ids=("obsA",),
    )
    c2 = make_action_candidate(
        action_class="measurement:repeat", requirement_ids=("r1", "r2"), formulation=f1,
        property="tensile_strength", role=OBSERVED, target_context={}, existing_evidence_ids=("obsB", "obsC"),
    )
    assert c1.id == c2.id
    assert c1.existing_evidence_ids != c2.existing_evidence_ids


# -- 8. requirement ordering does not change identity -----------------------------------------------


def test_8_requirement_ordering_does_not_change_identity():
    pool_a, f_a, ps_a, obs_a, dv_a = _workload("normal")
    pool_b, f_b, ps_b, obs_b, dv_b = _workload("shuffled")
    spec_a = _specify_for(pool_a, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))
    spec_b = _specify_for(pool_b, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))
    ids_a = [c.id for c in generate_candidates(spec_a).candidates]
    ids_b = [c.id for c in generate_candidates(spec_b).candidates]
    assert ids_a == ids_b


# -- 9. duplicate requirements behave deterministically ----------------------------------------------


def test_9_duplicate_requirements_deterministic_dedup():
    pool, f, process_std, obs, dv = _workload()
    spec_a = _specify_for(pool, ["f1"], (TENSILE_CRITERION,))
    spec_b = _specify_for(pool, ["f1"], (TENSILE_CRITERION,))  # independently recomputed, identical content
    assert requirement_identity(spec_a.entries[0].requirements[0]) == requirement_identity(spec_b.entries[0].requirements[0])
    combined = ExperimentSpecification(
        process_natural_key=spec_a.process_natural_key, gaps=spec_a.gaps, entries=spec_a.entries + spec_b.entries,
    )
    assert len(combined.entries) == 2 * len(spec_a.entries)
    ids_single = [c.id for c in generate_candidates(spec_a).candidates]
    ids_combined = [c.id for c in generate_candidates(combined).candidates]
    assert ids_combined == ids_single


# -- 10. unknown/open action_class values remain valid -----------------------------------------------


def test_10_open_action_class_values_remain_valid():
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    c = make_action_candidate(
        action_class="literature:review", requirement_ids=("r1",), formulation=f1,
        property="tensile_strength", role=OBSERVED, target_context={},
    )
    assert c.action_class == "literature:review"
    assert c.id


# -- 11. candidate and specification immutability -------------------------------------------------------


def test_11_candidate_and_specification_immutability():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION,))
    before = repr(spec)
    cs = generate_candidates(spec)
    assert repr(spec) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        cs.candidates[0].action_class = "x"  # type: ignore[misc]


# -- 12. no candidate references written into requirements ------------------------------------------------


def test_12_no_candidate_references_written_into_requirements():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION,))
    req = spec.entries[0].requirements[0]
    before = repr(req)
    generate_candidates(spec)
    assert repr(req) == before
    assert not hasattr(req, "candidate_ids")
    assert not hasattr(req, "candidates")


# -- 13. no EvidencePool/retrieval access -------------------------------------------------------------------


def test_13_no_pool_or_retrieval_access():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION,))
    fingerprint_before = pool.fingerprint()
    generate_candidates(spec)  # single argument -- no pool, no engine
    assert pool.fingerprint() == fingerprint_before


# -- 14. no ranking/score/winner/best/recommended/optimal semantics ------------------------------------------


def test_14_no_ranking_score_or_recommendation_fields():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1", "f2"], (TENSILE_CRITERION,))
    cs = generate_candidates(spec)
    forbidden = (
        "score", "rank", "ranking", "winner", "best", "recommended", "optimal",
        "priority", "utility", "cost", "expected_information_gain", "confidence_rank",
        "probability", "feasible", "feasibility", "selected", "selection",
    )
    assert not any(hasattr(cs, name) for name in forbidden)
    for c in cs.candidates:
        assert not any(hasattr(c, name) for name in forbidden)


# -- 15. deterministic output ordering by candidate id ------------------------------------------------------


def test_15_output_ordered_by_candidate_id():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1", "f2", "f3", "f4", "f5"], (TENSILE_CRITERION, MODULUS_CRITERION, VISCOSITY_CRITERION))
    cs = generate_candidates(spec)
    ids = [c.id for c in cs.candidates]
    assert ids == sorted(ids)


# -- 16. PYTHONHASHSEED determinism -----------------------------------------------------------------------------


def test_16_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.admission import admit_claimed_relationship, admit_derived_grounding, "
        "admit_derived_value, admit_document, admit_observation, admit_record, admit_referent\n"
        "from evidence.pool import EvidencePool\n"
        "from evidence.types import make_claimed_relationship, make_derived_grounding, "
        "make_derived_value, make_document, make_observation, make_record, make_referent, make_source\n"
        "from materials.audit import audit_program\n"
        "from materials.candidates import generate_candidates\n"
        "from materials.decision import make_criterion, evaluate_program\n"
        "from materials.experiment import analyze_experiment_gaps\n"
        "from materials.program import make_material_program_query, analyze_program\n"
        "from materials.specification import specify_experiment_requirements\n"
        "from retrieval.engine import DeterministicRetrievalEngine\n"
        "pool = EvidencePool()\n"
        "source = make_source(kind='lab_notebook', name='QC')\n"
        "pool.put_source(source)\n"
        "doc = make_document(source_id=source.id, raw_content='panel', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(doc)\n"
        "process = make_referent(natural_key='process-std-190c', kind='process')\n"
        "pool.put_referent(process)\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "pool.put_referent(f1)\n"
        "rec1 = make_record(document_id=doc.id, locator='r1', raw_content='82')\n"
        "pool.put_record(rec1)\n"
        "rec2 = make_record(document_id=doc.id, locator='r2', raw_content='79')\n"
        "pool.put_record(rec2)\n"
        "obs1 = make_observation(record_ids=(rec1.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 82, 'unit': 'MPa'}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(obs1)\n"
        "obs2 = make_observation(record_ids=(rec2.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 79, 'unit': 'MPa'}, confidence=1.0, extracted_at='t2')\n"
        "pool.put_observation(obs2)\n"
        "rel1 = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs1.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel1)\n"
        "rel2 = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs2.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel2)\n"
        "engine = DeterministicRetrievalEngine()\n"
        "query = make_material_program_query(['formulation-f1'], 'process-std-190c', ['tensile_strength'])\n"
        "program_answer = analyze_program(pool, engine, query)\n"
        "criterion = make_criterion('tensile_strength', '>=', 80)\n"
        "decision = evaluate_program(program_answer, (criterion,))\n"
        "audit = audit_program(decision)\n"
        "gaps = analyze_experiment_gaps(audit)\n"
        "spec = specify_experiment_requirements(gaps)\n"
        "cs = generate_candidates(spec)\n"
        "for c in cs.candidates:\n"
        "    print(c.id, c.action_class, sorted(c.requirement_ids))\n"
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
    assert len(outputs) == 1, f"generate_candidates differed across PYTHONHASHSEED values: {outputs}"
