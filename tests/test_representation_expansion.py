from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry
from ciw.core.identities import content_identity, evidence_id
from ciw.operations.runner import seal
from ciw.representation_expansion import (
    plan_after_expansion,
    reconsider_after_expansion,
    resolve_expansion,
    validate_expansion,
    validate_reconsideration,
)
from ciw.representation_interventions import gate_from_spec
from ciw.representation_morphisms import witness_from_spec
from ciw.semantic_capabilities import builtin_semantic_registry
from test_representation_interventions import baseline, needle_spec
from test_representation_morphisms import execute_real_periodogram


def retained_spec():
    return {"expansion_id": "periodogram-to-source", "projection_morphism_id": "signal.periodogram.transform.v1", "notes": ""}


def reconsideration_spec():
    return {"reconsideration_id": "periodogram-source-reconsideration",
            "local_gate_id": "represented-channel-selection-after-expansion", "notes": ""}


def make_case(tmp_path):
    source, run, result, data, semantic, registry = execute_real_periodogram(tmp_path / "projection")
    execution = run["nodes"]["spectrum"]["execution"]
    witness = witness_from_spec(registry, semantic, {
        "witness_id": "expansion-periodogram-witness",
        "morphism_id": "signal.periodogram.transform.v1",
        "source_evidence_id": source["evidence_id"],
        "execution_ref": content_identity(execution),
        "result_ref": content_identity(result),
        "checks": [
            {"check_id": "source-retained", "kind": "PROVENANCE", "status": "PASS",
             "evidence_ref": source["evidence_id"], "notes": "Source evidence retained."},
            {"check_id": "periodogram-contract", "kind": "CODOMAIN", "status": "PASS",
             "evidence_ref": content_identity(data), "notes": "Saved periodogram payload contract validated."},
            {"check_id": "physical-validation", "kind": "VALIDITY", "status": "UNRESOLVED",
             "evidence_ref": None, "notes": "Synthetic source is not empirical validation."},
        ],
        "notes": "Retained transform witness for expansion tests.",
    })
    gate = gate_from_spec(registry, semantic, {
        "gate_id": "periodogram-time-domain-intervention",
        "representation_id": "signal.periodogram.one-sided-density.v1",
        "intervention_id": "select-channel-and-half-open-interval",
        "needle_target": {"node_id": "statistics", "parameter": "channel"},
        "recovery_representation_id": "signal.timeseries.uniform-scalar.v1",
        "recovery_evidence_ref": source["evidence_id"],
        "notes": "",
    })
    assert gate["decision"] == "EXPAND"
    return source, execution, result, witness, gate, semantic, registry


def resolved_case(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    expansion = resolve_expansion(registry, semantic, gate, source, witness, execution, result, retained_spec())
    reconsideration = reconsider_after_expansion(
        registry, semantic, gate, expansion, source, witness, execution, result,
        reconsideration_spec())
    return source, execution, result, witness, gate, expansion, reconsideration, semantic, registry


def test_expansion_binds_actual_source_projection_witness_and_payload(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    expansion = resolve_expansion(registry, semantic, gate, source, witness, execution, result, retained_spec())
    assert expansion["source_evidence_id"] == source["evidence_id"]
    assert expansion["source_run_ref"] == content_identity(source)
    assert expansion["recovery_representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert expansion["current_representation_id"] == "signal.periodogram.one-sided-density.v1"
    assert expansion["projection_morphism_id"] == "signal.periodogram.transform.v1"
    assert expansion["operation_id"] == "spectrum.periodogram.v1"
    assert expansion["execution_ref"] == content_identity(execution)
    assert expansion["result_ref"] == content_identity(result)
    assert expansion["witness_status"] == {"PASS": 2, "FAIL": 0, "UNRESOLVED": 1}
    assert expansion["claims"]["retained_projection_payload_validated"] is True
    assert expansion["claims"]["projection_reexecuted"] is False
    assert expansion["claims"]["materialization_performed"] is False
    assert validate_expansion(expansion, registry, semantic, gate, source, witness, execution, result) == expansion


def test_tampered_source_with_stale_evidence_id_refuses(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    source["channels"]["q"]["values"][10] += 1.0
    with pytest.raises(ValueError, match="Evidence integrity mismatch"):
        resolve_expansion(registry, semantic, gate, source, witness, execution, result, retained_spec())


def test_different_self_consistent_source_still_refuses_gate_binding(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    source["channels"]["q"]["values"][10] += 1.0
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError, match="does not match the EXPAND gate"):
        resolve_expansion(registry, semantic, gate, source, witness, execution, result, retained_spec())


def test_result_tampering_is_caught_by_trusted_payload_validation_even_with_new_witness(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    tampered = deepcopy(result)
    tampered["data"]["sample_count"] -= 1
    tampered = seal(tampered)
    witness = witness_from_spec(registry, semantic, {
        "witness_id": "tampered-result-witness",
        "morphism_id": "signal.periodogram.transform.v1",
        "source_evidence_id": source["evidence_id"],
        "execution_ref": content_identity(execution),
        "result_ref": content_identity(tampered),
        "checks": [{"check_id": "claimed", "kind": "CODOMAIN", "status": "PASS",
                    "evidence_ref": content_identity(tampered["data"]), "notes": "Caller claim."}],
        "notes": "A self-consistent caller assertion must not replace trusted payload validation.",
    })
    with pytest.raises(ValueError, match="sample_count"):
        resolve_expansion(registry, semantic, gate, source, witness, execution, tampered, retained_spec())


def test_witness_failure_blocks_expansion(tmp_path):
    source, execution, result, _, gate, semantic, registry = make_case(tmp_path)
    witness = witness_from_spec(registry, semantic, {
        "witness_id": "known-failed-witness",
        "morphism_id": "signal.periodogram.transform.v1",
        "source_evidence_id": source["evidence_id"],
        "execution_ref": content_identity(execution),
        "result_ref": content_identity(result),
        "checks": [
            {"check_id": "source", "kind": "PROVENANCE", "status": "PASS",
             "evidence_ref": source["evidence_id"], "notes": "Source retained."},
            {"check_id": "known-failure", "kind": "PRESERVATION", "status": "FAIL",
             "evidence_ref": None, "notes": "Known failed check."},
        ],
        "notes": "",
    })
    with pytest.raises(ValueError, match="failed retained check"):
        resolve_expansion(registry, semantic, gate, source, witness, execution, result, retained_spec())


def test_witness_and_projection_artifact_hashes_must_match(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    other = deepcopy(result)
    other["recording_file"] = "different-retained-recording.json"
    other = seal(other)
    with pytest.raises(ValueError, match="projection artifacts do not match"):
        resolve_expansion(registry, semantic, gate, source, witness, execution, other, retained_spec())


def test_projection_direction_is_exact_not_reverse_inference(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path)
    mutated = deepcopy(registry)
    row = mutated["morphisms"]["signal.periodogram.transform.v1"]
    row["domain_representation_id"], row["codomain_representation_id"] = (
        row["codomain_representation_id"], row["domain_representation_id"])
    row = seal(row)
    mutated["morphisms"]["signal.periodogram.transform.v1"] = row
    mutated = seal(mutated)
    reverse_gate = gate_from_spec(mutated, semantic, {
        "gate_id": "reverse-direction-test",
        "representation_id": "signal.periodogram.one-sided-density.v1",
        "intervention_id": "select-channel-and-half-open-interval",
        "needle_target": {"node_id": "statistics", "parameter": "channel"},
        "recovery_representation_id": "signal.timeseries.uniform-scalar.v1",
        "recovery_evidence_ref": source["evidence_id"],
        "notes": "",
    })
    with pytest.raises(ValueError, match="Projection domain"):
        resolve_expansion(mutated, semantic, reverse_gate, source, witness, execution, result, retained_spec())


def test_reconsideration_preserves_old_expand_gate_and_derives_fresh_local_gate(tmp_path):
    source, execution, result, witness, gate, expansion, reconsideration, semantic, registry = resolved_case(tmp_path)
    assert gate["decision"] == "EXPAND"
    assert reconsideration["prior_gate_ref"] == gate["record_digest"]
    assert reconsideration["expansion_ref"] == expansion["record_digest"]
    assert reconsideration["local_gate"]["decision"] == "LOCAL"
    assert reconsideration["local_gate"]["representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert reconsideration["source_evidence_id"] == source["evidence_id"]
    assert validate_reconsideration(
        reconsideration, registry, semantic, gate, expansion, source, witness,
        execution, result) == reconsideration


def test_resealed_fake_expansion_or_reconsideration_is_recomputed_and_rejected(tmp_path):
    source, execution, result, witness, gate, expansion, reconsideration, semantic, registry = resolved_case(tmp_path)
    fake = deepcopy(expansion)
    fake["claims"]["projection_reexecuted"] = True
    with pytest.raises(ValueError, match="exact evidence recomputation"):
        validate_expansion(seal(fake), registry, semantic, gate, source, witness, execution, result)
    fake = deepcopy(reconsideration)
    fake["local_gate"]["decision"] = "REFUSE"
    fake["local_gate"] = seal(fake["local_gate"])
    with pytest.raises(ValueError):
        validate_reconsideration(seal(fake), registry, semantic, gate, expansion, source,
                                 witness, execution, result)


def test_plan_after_expansion_reuses_ordinary_needle_plan_only_after_reconsideration(tmp_path):
    source, execution, result, witness, gate, expansion, reconsideration, semantic, registry = resolved_case(tmp_path)
    _, base_run = baseline(tmp_path / "baseline")
    plan = plan_after_expansion(base_run, needle_spec(), registry, semantic, gate, expansion,
                                reconsideration, source, witness, execution, result)
    assert plan["schema"] == "ciw.needle-plan.v1"
    assert plan["target"]["node_id"] == "statistics"
    assert base_run["source_evidence_id"] == source["evidence_id"]
    assert reconsideration["claims"]["candidate_execution_performed"] is False


def test_plan_after_expansion_refuses_different_baseline_evidence(tmp_path):
    source, execution, result, witness, gate, expansion, reconsideration, semantic, registry = resolved_case(tmp_path)
    _, base_run = baseline(tmp_path / "baseline")
    base_run["source_evidence_id"] = "sha256:" + "f" * 64
    base_run = seal(base_run)
    with pytest.raises(ValueError, match="baseline uses different evidence"):
        plan_after_expansion(base_run, needle_spec(), registry, semantic, gate, expansion,
                             reconsideration, source, witness, execution, result)


def test_cli_expansion_reconsideration_and_plan(tmp_path):
    source, execution, result, witness, gate, semantic, registry = make_case(tmp_path / "case")
    _, base_run = baseline(tmp_path / "baseline")
    files = {
        "registry": registry, "gate": gate, "source": source, "witness": witness,
        "execution": execution, "result": result, "expansion-spec": retained_spec(),
        "reconsideration-spec": reconsideration_spec(), "baseline": base_run,
        "needle-spec": needle_spec(),
    }
    for name, value in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    cmd = [sys.executable, "-m", "ciw.net", "needle"]
    expansion = tmp_path / "expansion.json"
    reconsideration = tmp_path / "reconsideration.json"
    plan = tmp_path / "plan.json"
    subprocess.run(cmd + ["expand", str(tmp_path / "registry.json"), str(tmp_path / "gate.json"),
                          str(tmp_path / "source.json"), str(tmp_path / "witness.json"),
                          str(tmp_path / "execution.json"), str(tmp_path / "result.json"),
                          str(tmp_path / "expansion-spec.json"), "--output", str(expansion)], check=True)
    subprocess.run(cmd + ["reconsider", str(tmp_path / "registry.json"), str(tmp_path / "gate.json"),
                          str(tmp_path / "source.json"), str(tmp_path / "witness.json"),
                          str(tmp_path / "execution.json"), str(tmp_path / "result.json"),
                          str(expansion), str(tmp_path / "reconsideration-spec.json"),
                          "--output", str(reconsideration)], check=True)
    subprocess.run(cmd + ["plan-expanded", str(tmp_path / "baseline.json"), str(tmp_path / "needle-spec.json"),
                          str(tmp_path / "registry.json"), str(tmp_path / "gate.json"),
                          str(tmp_path / "source.json"), str(tmp_path / "witness.json"),
                          str(tmp_path / "execution.json"), str(tmp_path / "result.json"),
                          str(expansion), str(reconsideration), "--output", str(plan)], check=True)
    assert json.loads(expansion.read_text())["claims"]["projection_reexecuted"] is False
    assert json.loads(reconsideration.read_text())["local_gate"]["decision"] == "LOCAL"
    assert json.loads(plan.read_text())["schema"] == "ciw.needle-plan.v1"


def test_cli_refuses_overwriting_retained_expansion(tmp_path):
    source, execution, result, witness, gate, _, registry = make_case(tmp_path / "case")
    for name, value in (("registry", registry), ("gate", gate), ("source", source),
                        ("witness", witness), ("execution", execution), ("result", result),
                        ("spec", retained_spec())):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    output = tmp_path / "expansion.json"
    args = [sys.executable, "-m", "ciw.net", "needle", "expand",
            str(tmp_path / "registry.json"), str(tmp_path / "gate.json"), str(tmp_path / "source.json"),
            str(tmp_path / "witness.json"), str(tmp_path / "execution.json"), str(tmp_path / "result.json"),
            str(tmp_path / "spec.json"), "--output", str(output)]
    assert subprocess.run(args).returncode == 0
    assert subprocess.run(args, capture_output=True).returncode == 1
