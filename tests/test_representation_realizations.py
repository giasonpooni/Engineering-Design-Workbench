from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_contracts import state
from ciw.control_plane import builtin_registry
from ciw.core.covariance import create_covariance_artifact
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.representation_interventions import gate_from_spec
from ciw.representation_morphisms import registry_from_specs
from ciw.representation_realizations import (
    adapter_registry_from_specs,
    bind_recovery_realization,
    realize,
    validate_adapter_registry,
    validate_realization,
    validate_recovery_binding,
)
from ciw.semantic_capabilities import builtin_semantic_registry
from test_representation_morphisms import morphism_specs, representation_specs, scale


SOURCE_REF = "sha256:" + "a" * 64


def extra_representation_specs():
    return [
        {
            "representation_id": "state.vector.estimated.v1",
            "role": "STATE",
            "source_state_type": "retained-estimated-state",
            "schema_id": "ciw.state.v1",
            "quantity_semantics": "ordered retained state coordinates",
            "unit_semantics": "explicit per-coordinate units",
            "frame_semantics": "exact declared state frame",
            "time_semantics": "one retained state clock",
            "scale": scale("state estimate"),
            "uncertainty_semantics": "full covariance artifact when required",
            "equivalence_contract": "EXACT",
            "preserved_queries": ["state-coordinate-values", "state-covariance"],
            "supported_interventions": [],
            "recovery_route": None,
            "provenance_refs": [],
            "notes": "Typed state record realization fixture.",
        },
        {
            "representation_id": "uncertainty.covariance.matrix.v1",
            "role": "MATRIX",
            "source_state_type": "retained-covariance-artifact",
            "schema_id": "covariance-artifact.v1",
            "quantity_semantics": "full covariance over ordered coordinates",
            "unit_semantics": "axis units retained explicitly",
            "frame_semantics": "exact declared covariance frame",
            "time_semantics": "bound to retained reference values",
            "scale": scale("covariance matrix"),
            "uncertainty_semantics": "the representation is the covariance itself",
            "equivalence_contract": "EXACT",
            "preserved_queries": ["covariance-matrix", "variance", "cross-covariance"],
            "supported_interventions": [],
            "recovery_route": None,
            "provenance_refs": [],
            "notes": "Content-addressed covariance realization fixture.",
        },
    ]


def realization_registry():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    reps = representation_specs() + extra_representation_specs()
    morphisms = registry_from_specs(reps, morphism_specs(), semantic)
    specs = [
        {
            "adapter_id": "realizer.oscillator-channel.v1",
            "representation_id": "signal.timeseries.uniform-scalar.v1",
            "validator_id": "run-channel.v1",
            "binding": {
                "quantity_ids": ["q"],
                "units": ["m"],
                "frame": "oscillator-state",
                "uncertainty_required": False,
            },
            "notes": "Exact retained q-channel realization.",
        },
        {
            "adapter_id": "realizer.estimated-state.v1",
            "representation_id": "state.vector.estimated.v1",
            "validator_id": "state-record.v1",
            "binding": {
                "quantity_ids": ["x", "v"],
                "units": ["m", "m/s"],
                "frame": "lab-frame",
                "uncertainty_required": True,
            },
            "notes": "State plus full covariance realization.",
        },
        {
            "adapter_id": "realizer.state-covariance.v1",
            "representation_id": "uncertainty.covariance.matrix.v1",
            "validator_id": "covariance-artifact.v1",
            "binding": {
                "quantity_ids": ["x", "v"],
                "units": ["m", "m/s"],
                "frame": "lab-frame",
                "uncertainty_required": True,
            },
            "notes": "Full covariance artifact realization.",
        },
    ]
    adapters = adapter_registry_from_specs(morphisms, semantic, specs)
    return concrete, semantic, morphisms, adapters, specs


def covariance_and_state():
    covariance = create_covariance_artifact(
        matrix=[[0.04, 0.01], [0.01, 0.09]],
        quantity_ids=["x", "v"],
        units=["m", "m/s"],
        frame="lab-frame",
        reference_values=[1.5, -0.25],
        method="synthetic-fixture",
        basis={"kind": "estimated_state", "id": "state-fixture"},
        provenance={
            "provider": "test-fixture",
            "source_evidence_ids": [SOURCE_REF],
            "source_covariance_ids": [],
        },
        assumptions=["synthetic numerical fixture"],
    )
    selected = state(
        identity={"model_id": "fixture-model", "entity_id": "fixture-entity", "execution_id": None},
        clock={"id": "fixture-clock", "time_s": 0.0},
        frame="lab-frame",
        variables={
            "x": {"value": 1.5, "unit": "m"},
            "v": {"value": -0.25, "unit": "m/s"},
        },
        uncertainty=covariance,
        provenance={
            "provider": "test-fixture",
            "sources": [SOURCE_REF, covariance["covariance_id"]],
            "semantics": "estimated",
        },
    )
    return covariance, selected


def run_spec():
    return {
        "realization_id": "oscillator-q-full",
        "adapter_id": "realizer.oscillator-channel.v1",
        "selector": {"channel": "q", "interval_s": [0.0, 12.0]},
        "notes": "",
    }


def expand_gate(morphisms, semantic, source, evidence_ref=None):
    return gate_from_spec(morphisms, semantic, {
        "gate_id": "periodogram-recover-timeseries",
        "representation_id": "signal.periodogram.one-sided-density.v1",
        "intervention_id": "select-channel-and-half-open-interval",
        "needle_target": {"node_id": "statistics", "parameter": "channel"},
        "recovery_representation_id": "signal.timeseries.uniform-scalar.v1",
        "recovery_evidence_ref": source["evidence_id"] if evidence_ref is None else evidence_ref,
        "notes": "",
    })


def test_adapter_registry_binds_three_existing_validator_families():
    _, semantic, morphisms, adapters, _ = realization_registry()
    assert set(adapters["adapters"]) == {
        "realizer.oscillator-channel.v1",
        "realizer.estimated-state.v1",
        "realizer.state-covariance.v1",
    }
    assert adapters["morphism_registry_ref"] == morphisms["record_digest"]
    assert adapters["claims"]["provider_execution"] is False
    assert validate_adapter_registry(adapters, morphisms, semantic) == adapters


def test_adapter_refuses_representation_schema_validator_mismatch():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    morphisms = registry_from_specs(
        representation_specs() + extra_representation_specs(), morphism_specs(), semantic)
    bad = [{
        "adapter_id": "realizer.bad.v1",
        "representation_id": "state.vector.estimated.v1",
        "validator_id": "run-channel.v1",
        "binding": {
            "quantity_ids": ["x"], "units": ["m"], "frame": "lab-frame",
            "uncertainty_required": False,
        },
        "notes": "",
    }]
    with pytest.raises(ValueError, match="schema is incompatible"):
        adapter_registry_from_specs(morphisms, semantic, bad)


def test_run_channel_realization_is_exact_and_bounded():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    value = realize(adapters, morphisms, semantic, source, run_spec())
    assert value["representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert value["evidence_refs"] == [source["evidence_id"]]
    assert value["realized_view"]["quantity_ids"] == ["q"]
    assert value["realized_view"]["units"] == ["m"]
    assert value["realized_view"]["selected_sample_count"] == 768
    assert value["realized_view"]["first_selected_time_s"] == 0.0
    assert value["realized_view"]["last_selected_time_s"] < 12.0
    assert value["claims"]["family_validator_executed"] is True
    assert value["claims"]["empirical_truth_established"] is False
    assert validate_realization(value, adapters, morphisms, semantic, source) == value


def test_run_channel_subinterval_realization_counts_half_open_samples():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    spec = run_spec()
    spec["selector"]["interval_s"] = [0.0, 1.0]
    value = realize(adapters, morphisms, semantic, source, spec)
    assert value["realized_view"]["selected_sample_count"] == 64
    assert value["realized_view"]["last_selected_time_s"] == pytest.approx(63 / 64)


def test_run_channel_refuses_unbound_channel_and_bad_interval():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    bad = run_spec()
    bad["selector"]["channel"] = "v"
    with pytest.raises(ValueError, match="outside the realization binding"):
        realize(adapters, morphisms, semantic, source, bad)
    bad = run_spec()
    bad["selector"]["interval_s"] = [11.0, 13.0]
    with pytest.raises(ValueError, match="exceeds retained run duration"):
        realize(adapters, morphisms, semantic, source, bad)


def test_run_channel_refuses_stale_evidence_identity():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    source["channels"]["q"]["values"][0] += 1.0
    with pytest.raises(ValueError, match="Evidence integrity mismatch"):
        realize(adapters, morphisms, semantic, source, run_spec())


def test_state_realization_reuses_full_covariance_validator():
    _, semantic, morphisms, adapters, _ = realization_registry()
    covariance, selected = covariance_and_state()
    value = realize(adapters, morphisms, semantic, selected, {
        "realization_id": "estimated-state",
        "adapter_id": "realizer.estimated-state.v1",
        "selector": {},
        "notes": "",
    })
    assert value["realized_view"]["quantity_ids"] == ["x", "v"]
    assert value["realized_view"]["uncertainty_ref"] == covariance["covariance_id"]
    assert SOURCE_REF in value["evidence_refs"]
    assert covariance["covariance_id"] in value["evidence_refs"]


def test_state_realization_refuses_missing_required_uncertainty():
    _, semantic, morphisms, adapters, _ = realization_registry()
    _, selected = covariance_and_state()
    selected["uncertainty"] = None
    selected = seal(selected)
    with pytest.raises(ValueError, match="requires retained uncertainty"):
        realize(adapters, morphisms, semantic, selected, {
            "realization_id": "state-without-covariance",
            "adapter_id": "realizer.estimated-state.v1",
            "selector": {},
            "notes": "",
        })


def test_state_realization_refuses_wrong_frame_binding():
    _, semantic, morphisms, adapters, _ = realization_registry()
    _, selected = covariance_and_state()
    selected["frame"] = "other-frame"
    selected["uncertainty"]["frame"] = "other-frame"
    # Rebuild neither covariance identity nor state seal: the lower validator must fail first.
    selected = seal(selected)
    with pytest.raises(ValueError):
        realize(adapters, morphisms, semantic, selected, {
            "realization_id": "wrong-frame",
            "adapter_id": "realizer.estimated-state.v1",
            "selector": {},
            "notes": "",
        })


def test_covariance_realization_reuses_axis_unit_frame_and_psd_checks():
    _, semantic, morphisms, adapters, _ = realization_registry()
    covariance, _ = covariance_and_state()
    value = realize(adapters, morphisms, semantic, covariance, {
        "realization_id": "state-covariance",
        "adapter_id": "realizer.state-covariance.v1",
        "selector": {},
        "notes": "",
    })
    assert value["realized_view"]["matrix_shape"] == [2, 2]
    assert value["realized_view"]["uncertainty_ref"] == covariance["covariance_id"]
    assert value["evidence_refs"] == [SOURCE_REF]


def test_covariance_realization_refuses_tampered_matrix_even_if_structure_is_retained():
    _, semantic, morphisms, adapters, _ = realization_registry()
    covariance, _ = covariance_and_state()
    covariance["matrix"][0][0] = -1.0
    with pytest.raises(ValueError):
        realize(adapters, morphisms, semantic, covariance, {
            "realization_id": "bad-covariance",
            "adapter_id": "realizer.state-covariance.v1",
            "selector": {},
            "notes": "",
        })


def test_realization_validator_recomputes_resealed_derived_view():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    value = realize(adapters, morphisms, semantic, source, run_spec())
    value["realized_view"]["selected_sample_count"] = 1
    with pytest.raises(ValueError, match="exact family validation"):
        validate_realization(seal(value), adapters, morphisms, semantic, source)


def test_adapter_registry_refuses_changed_morphism_registry():
    _, semantic, morphisms, adapters, specs = realization_registry()
    reps = representation_specs() + extra_representation_specs()
    reps[0]["notes"] += " changed"
    changed = registry_from_specs(reps, morphism_specs(), semantic)
    with pytest.raises(ValueError, match="different morphism registry"):
        validate_adapter_registry(adapters, changed, semantic)


def test_recovery_realization_binds_actual_richer_representation_and_evidence():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    realization = realize(adapters, morphisms, semantic, source, run_spec())
    gate = expand_gate(morphisms, semantic, source)
    binding = bind_recovery_realization(
        adapters, morphisms, semantic, gate, realization, source, "periodogram-source-realization")
    assert binding["recovery_representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert binding["recovery_evidence_ref"] == source["evidence_id"]
    assert binding["claims"]["projection_execution_verified"] is False
    assert binding["claims"]["intervention_reconsidered"] is False
    assert validate_recovery_binding(
        binding, adapters, morphisms, semantic, gate, realization, source) == binding


def test_recovery_realization_refuses_gate_with_different_evidence():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    realization = realize(adapters, morphisms, semantic, source, run_spec())
    gate = expand_gate(morphisms, semantic, source, "sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="does not retain the recovery evidence"):
        bind_recovery_realization(
            adapters, morphisms, semantic, gate, realization, source, "wrong-evidence")


def test_resealed_fake_recovery_binding_is_recomputed():
    _, semantic, morphisms, adapters, _ = realization_registry()
    source = make_demo_run()
    realization = realize(adapters, morphisms, semantic, source, run_spec())
    gate = expand_gate(morphisms, semantic, source)
    binding = bind_recovery_realization(
        adapters, morphisms, semantic, gate, realization, source, "binding")
    binding["claims"]["projection_execution_verified"] = True
    with pytest.raises(ValueError, match="exact recomputation"):
        validate_recovery_binding(
            seal(binding), adapters, morphisms, semantic, gate, realization, source)


def test_cli_registry_realization_and_recovery_binding(tmp_path):
    _, semantic, morphisms, adapters, specs = realization_registry()
    source = make_demo_run()
    gate = expand_gate(morphisms, semantic, source)
    paths = {
        "morphisms": morphisms,
        "adapter-spec": {"adapters": specs},
        "source": source,
        "realization-spec": run_spec(),
        "gate": gate,
    }
    for name, value in paths.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    command = [sys.executable, "-m", "ciw.net", "realization"]
    registry_path = tmp_path / "adapters.json"
    realization_path = tmp_path / "realization.json"
    binding_path = tmp_path / "binding.json"
    subprocess.run(command + [
        "create-registry", str(tmp_path / "morphisms.json"),
        str(tmp_path / "adapter-spec.json"), "--output", str(registry_path)], check=True)
    subprocess.run(command + [
        "realize", str(registry_path), str(tmp_path / "morphisms.json"),
        str(tmp_path / "source.json"), str(tmp_path / "realization-spec.json"),
        "--output", str(realization_path)], check=True)
    subprocess.run(command + [
        "bind-recovery", str(registry_path), str(tmp_path / "morphisms.json"),
        str(tmp_path / "gate.json"), str(realization_path), str(tmp_path / "source.json"),
        "cli-recovery-binding", "--output", str(binding_path)], check=True)
    assert json.loads(registry_path.read_text())["record_digest"] == adapters["record_digest"]
    assert json.loads(realization_path.read_text())["representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert json.loads(binding_path.read_text())["recovery_evidence_ref"] == source["evidence_id"]
