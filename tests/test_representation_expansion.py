from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, run_graph
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.representation_expansion import (
    expansion_from_spec,
    promote_expansion,
    validate_expansion,
    validate_expansion_verification,
    validate_promotion,
    verify_expansion,
)
from ciw.representation_interventions import gate_from_spec
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry, compile_graph
from ciw.session import Session
from test_representation_interventions import gate_spec, registry_specs


def retained_projection(tmp_path):
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    reps, morphisms = registry_specs()
    registry = registry_from_specs(reps, morphisms, semantic)
    source = make_demo_run()
    graph = {
        "schema": "ciw.semantic-work-graph.v1",
        "graph_id": "expansion-retained-periodogram",
        "mandate": "Retain current coarse periodogram before expansion.",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [{
            "node_id": "projection",
            "capability": "analysis.spectrum.v1",
            "parameters": {"channel": "q", "interval_s": [0.0, 12.0]},
            "inputs": {}, "depends_on": [], "resources": [],
            "acceptance": {}, "inspection": False,
        }],
    }
    compiled = compile_graph(graph, semantic)
    session = Session(source, tmp_path / "retained", operations=concrete.operations)
    run = run_graph(session, compiled["experiment"], concrete)
    assert run["status"] == "completed"
    node = run["nodes"]["projection"]
    gate = gate_from_spec(
        registry, semantic,
        gate_spec(
            "signal.periodogram.one-sided-density.v1",
            recovery_representation_id="signal.timeseries.uniform-scalar.v1",
            recovery_evidence_ref=source["evidence_id"],
        ),
    )
    assert gate["decision"] == "EXPAND"
    return source, node["execution"], node["result"], gate, registry, semantic


def expansion_spec():
    return {
        "expansion_id": "periodogram-to-retained-timeseries",
        "projection_morphism_id": "signal.periodogram.transform.v1",
        "notes": "Resolve retained source evidence; do not infer a spectral inverse.",
    }


def promotion_spec():
    return {
        "promotion_id": "verified-timeseries-locality",
        "local_gate_id": "timeseries-after-verified-expansion",
        "notes": "Replay verified exact retained projection relationship.",
    }


def test_expansion_binds_exact_gate_source_projection_and_retained_result(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    value = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    assert value["source_gate_ref"] == gate["record_digest"]
    assert value["source_evidence_ref"] == source["evidence_id"]
    assert value["current_representation_id"] == "signal.periodogram.one-sided-density.v1"
    assert value["richer_representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert value["projection_morphism_id"] == "signal.periodogram.transform.v1"
    assert value["retained_projection"]["operation_id"] == "spectrum.periodogram.v1"
    assert value["claims"]["new_materialization_performed"] is False
    assert value["claims"]["unique_inverse_inferred"] is False


def test_wrong_source_evidence_refuses_expansion(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    other = make_demo_run()
    other["channels"]["q"]["values"][0] += 0.5
    from ciw.core.identities import evidence_id
    other["evidence_id"] = evidence_id(other)
    with pytest.raises(ValueError, match="does not match the EXPAND gate"):
        expansion_from_spec(
            other, execution, result, gate, registry, semantic, expansion_spec())


def test_projection_direction_must_be_richer_to_current(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    bad = deepcopy(registry)
    morphism = bad["morphisms"]["signal.periodogram.transform.v1"]
    morphism["domain_representation_id"], morphism["codomain_representation_id"] = (
        morphism["codomain_representation_id"], morphism["domain_representation_id"])
    bad = seal(bad)
    with pytest.raises(ValueError):
        expansion_from_spec(source, execution, result, gate, bad, semantic, expansion_spec())


def test_retained_result_must_match_current_semantic_lowering(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    bad = deepcopy(result)
    bad["operation_id"] = "statistics.v1"
    bad = seal(bad)
    with pytest.raises(ValueError):
        expansion_from_spec(source, execution, bad, gate, registry, semantic, expansion_spec())


def test_resealed_expansion_tamper_is_recomputed(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    value = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    value["retained_projection"]["data_ref"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="contradicts retained evidence"):
        validate_expansion(
            seal(value), source, execution, result, gate, registry, semantic)


def test_replay_verification_passes_on_exact_retained_projection(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    expansion = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    verification = verify_expansion(
        expansion, source, execution, result, gate, registry, semantic,
        tmp_path / "verification")
    assert verification["status"] == "PASS"
    assert all(verification["comparisons"].values())
    assert verification["replay_execution"]["execution_id"] != execution["execution_id"]
    assert verification["replay_result"]["result_id"] != result["result_id"]
    assert verification["replay_result"]["data"] == result["data"]
    assert verification["claims"]["provider_execution"] is True
    assert verification["claims"]["canonical_state_mutated"] is False


def test_verification_validator_detects_resealed_fake_pass(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    expansion = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    verification = verify_expansion(
        expansion, source, execution, result, gate, registry, semantic,
        tmp_path / "verification")
    verification["replay_result"]["data"]["psd"][0] += 1.0
    verification["comparisons"]["data_equal"] = True
    verification["status"] = "PASS"
    with pytest.raises(ValueError):
        validate_expansion_verification(
            seal(verification), expansion, source, execution, result,
            gate, registry, semantic)


def test_verified_expansion_promotes_to_fresh_local_gate(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    expansion = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    verification = verify_expansion(
        expansion, source, execution, result, gate, registry, semantic,
        tmp_path / "verification")
    promotion = promote_expansion(
        expansion, verification, source, execution, result, gate,
        registry, semantic, promotion_spec())
    assert promotion["source_gate_ref"] == gate["record_digest"]
    assert promotion["verification_ref"] == verification["record_digest"]
    assert promotion["local_gate"]["decision"] == "LOCAL"
    assert promotion["local_gate"]["representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert promotion["claims"]["planning_transition_only"] is True
    assert validate_promotion(
        promotion, expansion, verification, source, execution, result,
        gate, registry, semantic) == promotion


def test_failed_or_tampered_verification_cannot_promote(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    expansion = expansion_from_spec(
        source, execution, result, gate, registry, semantic, expansion_spec())
    verification = verify_expansion(
        expansion, source, execution, result, gate, registry, semantic,
        tmp_path / "verification")
    verification["status"] = "FAIL"
    with pytest.raises(ValueError):
        promote_expansion(
            expansion, seal(verification), source, execution, result, gate,
            registry, semantic, promotion_spec())


def test_expansion_does_not_accept_local_or_refuse_gate(tmp_path):
    source, execution, result, _, registry, semantic = retained_projection(tmp_path)
    local = gate_from_spec(
        registry, semantic, gate_spec("signal.timeseries.uniform-scalar.v1"))
    refused = gate_from_spec(
        registry, semantic, gate_spec("signal.periodogram.one-sided-density.v1"))
    for gate in (local, refused):
        with pytest.raises(ValueError, match="requires an EXPAND gate"):
            expansion_from_spec(
                source, execution, result, gate, registry, semantic, expansion_spec())


def test_cli_full_expansion_chain_retains_separate_records(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    files = {
        "source": source, "execution": execution, "result": result,
        "gate": gate, "registry": registry, "expansion-spec": expansion_spec(),
        "promotion-spec": promotion_spec(),
    }
    for name, value in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    common = [
        str(tmp_path / "source.json"), str(tmp_path / "execution.json"),
        str(tmp_path / "result.json"), str(tmp_path / "gate.json"),
        str(tmp_path / "registry.json"),
    ]
    expansion_path = tmp_path / "expansion.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "expand", *common,
        str(tmp_path / "expansion-spec.json"), "--output", str(expansion_path),
    ], cwd=tmp_path, check=True)
    verification_path = tmp_path / "verification.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "verify-expansion", *common,
        str(expansion_path), "--session-dir", str(tmp_path / "cli-verification"),
        "--output", str(verification_path),
    ], cwd=tmp_path, check=True)
    promotion_path = tmp_path / "promotion.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "promote-expansion", *common,
        str(expansion_path), str(verification_path),
        str(tmp_path / "promotion-spec.json"), "--output", str(promotion_path),
    ], cwd=tmp_path, check=True)
    expansion_value = json.loads(expansion_path.read_text())
    verification_value = json.loads(verification_path.read_text())
    promotion_value = json.loads(promotion_path.read_text())
    assert expansion_value["schema"] == "ciw.representation-expansion.v1"
    assert verification_value["schema"] == "ciw.representation-expansion-verification.v1"
    assert verification_value["status"] == "PASS"
    assert promotion_value["schema"] == "ciw.representation-expansion-promotion.v1"
    assert promotion_value["local_gate"]["decision"] == "LOCAL"
    assert len({
        expansion_value["record_digest"],
        verification_value["record_digest"],
        promotion_value["record_digest"],
    }) == 3


def test_cli_refuses_overwrite_of_retained_expansion(tmp_path):
    source, execution, result, gate, registry, semantic = retained_projection(tmp_path)
    for name, value in {
        "source": source, "execution": execution, "result": result,
        "gate": gate, "registry": registry, "spec": expansion_spec(),
    }.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    output = tmp_path / "expansion.json"
    command = [
        sys.executable, "-m", "ciw.net", "needle", "expand",
        str(tmp_path / "source.json"), str(tmp_path / "execution.json"),
        str(tmp_path / "result.json"), str(tmp_path / "gate.json"),
        str(tmp_path / "registry.json"), str(tmp_path / "spec.json"),
        "--output", str(output),
    ]
    assert subprocess.run(command, cwd=tmp_path).returncode == 0
    assert subprocess.run(command, cwd=tmp_path, capture_output=True).returncode == 1
