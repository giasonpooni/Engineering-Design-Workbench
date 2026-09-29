import json
import subprocess
import sys

import pytest

from ciw.container_calculus import (
    composition_from_spec,
    container_from_spec,
    summarize_telemetry,
    telemetry_from_spec,
    validate_container,
)


def ref(char):
    return "sha256:" + char * 64


def port(port_id, schema="fixture.scalar.v1", unit="K", frame="rig-frame", required=True):
    return {
        "port_id": port_id, "schema": schema, "unit": unit,
        "frame": frame, "required": required,
    }


def container_spec(container_id="filter"):
    return {
        "container_id": container_id,
        "purpose": "Synthetic bounded scientific container.",
        "declared_behaviors": ["FILTER", "OBSERVER"],
        "state_partition": {
            "internal_state_schemas": ["fixture.internal-state.v1"],
            "boundary_state_schemas": ["fixture.boundary-state.v1"],
            "external_context_refs": [ref("1")],
        },
        "boundary": {
            "inputs": [port("in")],
            "outputs": [port("out")],
            "authority": {
                "effects": ["read:fixture", "write:fixture-result"],
                "network": False, "hardware_actuation": False,
                "state_admission": False, "release": False,
            },
        },
        "operators": ["signal.filter.v1"],
        "resource_envelope": {
            "cpu_cores_max": 4.0, "gpu_devices_max": 0,
            "ram_bytes_max": 1_000_000_000,
            "storage_bytes_max": 100_000_000, "wall_seconds_max": 120.0,
        },
        "evidence_policy": {
            "retain_inputs": True, "retain_outputs": True,
            "retain_telemetry": True, "required_evidence_refs": [ref("2")],
        },
        "telemetry_policy": {
            "required_resource_metrics": ["wall_seconds"],
            "required_uncertainty_proxies": ["posterior-entropy"],
            "require_verified_output_refs": True,
        },
    }


def metric(value, unit, provenance="MEASURED", char="3"):
    return {
        "value": value, "unit": unit,
        "provenance": provenance if value is not None else "UNKNOWN",
        "source_ref": ref(char) if value is not None else None,
    }


def resource_metrics():
    return {
        "wall_seconds": metric(2.0, "seconds"),
        "cpu_seconds": metric(1.5, "seconds"),
        "gpu_seconds": metric(None, "seconds"),
        "peak_ram_bytes": metric(120_000_000, "bytes"),
        "storage_read_bytes": metric(20_000, "bytes"),
        "storage_write_bytes": metric(10_000, "bytes"),
        "network_in_bytes": metric(0, "bytes"),
        "network_out_bytes": metric(0, "bytes"),
        "energy_joules": metric(None, "joules"),
        "cost_usd": metric(0.02, "usd", "PROVIDER_REPORTED"),
        "human_active_seconds": metric(None, "seconds"),
        "operation_calls": metric(1, "count"),
        "model_calls": metric(0, "count"),
    }


def telemetry_spec(container=None):
    return {
        "container_spec": container or container_from_spec(container_spec()),
        "execution_ref": ref("4"), "occurrence_id": "occurrence-001",
        "parent_occurrence_ref": None,
        "backend": {"class": "CONTAINER", "id": "docker:fixture"},
        "started_at": "2026-09-29T18:00:00-04:00",
        "ended_at": "2026-09-29T18:00:02-04:00",
        "outcome": "COMPLETED",
        "transport": {
            "admitted_items": 100, "admitted_bytes": 10_000,
            "emitted_items": 10, "emitted_bytes": 1_000,
            "discarded_items": 90, "discarded_bytes": 8_000,
            "retained_state_bytes": 1_000,
        },
        "resource_metrics": resource_metrics(),
        "residuals": [{
            "name": "innovation_rms", "value": 0.15, "unit": "K",
            "source_ref": ref("5"),
        }],
        "uncertainty_proxies": [{
            "proxy_id": "posterior-entropy", "kind": "POSTERIOR_ENTROPY",
            "before": 5.0, "after": 2.0, "unit": "bits",
            "method_id": "fixture-discrete-posterior-v1", "source_ref": ref("6"),
        }],
        "retained_state_refs": [ref("7")],
        "verified_output_refs": [ref("8")],
        "notes": "Synthetic telemetry fixture.",
    }


def test_container_spec_is_above_runtime_and_does_not_bind_execution():
    value = container_from_spec(container_spec())
    validate_container(value)
    assert value["schema"] == "ciw.container-spec.v1"
    assert value["operators"] == ["signal.filter.v1"]
    assert value["claims"]["executable_binding"] is False
    assert value["claims"]["runtime_selected"] is False
    assert value["claims"]["fep_interpretation"] is False
    assert value["claims"]["execution_authority"] is False


def test_container_has_explicit_internal_boundary_external_partition():
    value = container_from_spec(container_spec())
    assert value["state_partition"]["internal_state_schemas"] == ["fixture.internal-state.v1"]
    assert value["state_partition"]["boundary_state_schemas"] == ["fixture.boundary-state.v1"]
    assert value["state_partition"]["external_context_refs"] == [ref("1")]


def test_semantic_operator_refuses_runtime_name():
    spec = container_spec(); spec["operators"] = ["python:filter"]
    with pytest.raises(ValueError, match="semantic"):
        container_from_spec(spec)


def test_composition_validates_nested_hierarchy_and_typed_flow():
    left = container_from_spec(container_spec("source"))
    right_spec = container_spec("sink"); right_spec["operators"] = ["state.estimate.v1"]
    right = container_from_spec(right_spec)
    composition = composition_from_spec({
        "composition_id": "fixture-composition",
        "containers": [left, right],
        "relations": [
            {"relation_id": "R-1", "kind": "FLOW", "source_container_id": "source",
             "target_container_id": "sink", "source_port": "out", "target_port": "in"},
            {"relation_id": "R-2", "kind": "NESTED", "source_container_id": "sink",
             "target_container_id": "source", "source_port": None, "target_port": None},
        ],
    })
    assert composition["schema"] == "ciw.container-composition.v1"
    assert composition["claims"]["provider_execution"] is False


def test_flow_refuses_unit_frame_or_schema_mismatch():
    left = container_from_spec(container_spec("source"))
    right_spec = container_spec("sink"); right_spec["boundary"]["inputs"][0]["unit"] = "Pa"
    right = container_from_spec(right_spec)
    with pytest.raises(ValueError, match="schema/unit/frame"):
        composition_from_spec({
            "composition_id": "bad-flow", "containers": [left, right],
            "relations": [{"relation_id": "R-1", "kind": "FLOW",
                           "source_container_id": "source", "target_container_id": "sink",
                           "source_port": "out", "target_port": "in"}],
        })


def test_nested_cycle_refuses():
    a = container_from_spec(container_spec("a")); b = container_from_spec(container_spec("b"))
    with pytest.raises(ValueError, match="cycle"):
        composition_from_spec({
            "composition_id": "cycle", "containers": [a, b],
            "relations": [
                {"relation_id": "R-1", "kind": "NESTED", "source_container_id": "a",
                 "target_container_id": "b", "source_port": None, "target_port": None},
                {"relation_id": "R-2", "kind": "NESTED", "source_container_id": "b",
                 "target_container_id": "a", "source_port": None, "target_port": None},
            ],
        })


def test_telemetry_retains_unknown_resources_instead_of_imputing():
    summary = summarize_telemetry(telemetry_from_spec(telemetry_spec()))
    assert {"gpu_seconds", "energy_joules", "human_active_seconds"} <= set(summary["unknown_resource_metrics"])
    assert summary["claims"]["shannon_information_inferred_from_bytes"] is False


def test_entropy_reduction_is_separate_from_transport_bytes():
    summary = summarize_telemetry(telemetry_from_spec(telemetry_spec()))
    proxy = summary["uncertainty_reductions"][0]
    assert proxy["kind"] == "POSTERIOR_ENTROPY"
    assert proxy["reduction"] == pytest.approx(3.0)
    assert proxy["unit"] == "bits"
    assert summary["transport"]["emitted_over_admitted_bytes"] == pytest.approx(0.1)
    assert "not Shannon information" in summary["transport"]["interpretation"]


def test_entropy_proxy_requires_bits_or_nats():
    spec = telemetry_spec(); spec["uncertainty_proxies"][0]["unit"] = "bytes"
    with pytest.raises(ValueError, match="bits or nats"):
        telemetry_from_spec(spec)


def test_required_metric_cannot_be_unknown():
    spec = telemetry_spec(); spec["resource_metrics"]["wall_seconds"] = metric(None, "seconds")
    with pytest.raises(ValueError, match="Required resource metric"):
        telemetry_from_spec(spec)


def test_completed_occurrence_requires_verified_output_if_policy_demands_it():
    spec = telemetry_spec(); spec["verified_output_refs"] = []
    with pytest.raises(ValueError, match="verified output"):
        telemetry_from_spec(spec)


def test_cloud_is_only_a_backend_identity_not_the_architecture():
    spec = telemetry_spec(); spec["backend"] = {"class": "CLOUD", "id": "provider:fixture-cloud"}
    value = telemetry_from_spec(spec)
    assert value["backend"]["class"] == "CLOUD"
    assert value["claims"]["execution_authority"] is False


def test_yield_ratios_are_only_derived_from_declared_measured_resources():
    summary = summarize_telemetry(telemetry_from_spec(telemetry_spec()))
    assert summary["verified_output_count"] == 1
    assert summary["verified_outputs_per_wall_second"] == pytest.approx(0.5)
    assert summary["verified_outputs_per_cost_usd"] == pytest.approx(50.0)


def test_cli_create_telemetry_and_inspect(tmp_path):
    spec_path = tmp_path / "container-spec.json"
    container_path = tmp_path / "container.json"
    telemetry_input = tmp_path / "telemetry-spec.json"
    telemetry_path = tmp_path / "telemetry.json"
    spec_path.write_text(json.dumps(container_spec()))
    subprocess.run([sys.executable, "-m", "ciw.net", "container", "create",
                    str(spec_path), "--output", str(container_path)], cwd=tmp_path, check=True)
    container = json.loads(container_path.read_text())
    telemetry_input.write_text(json.dumps(telemetry_spec(container)))
    subprocess.run([sys.executable, "-m", "ciw.net", "container", "telemetry",
                    str(telemetry_input), "--output", str(telemetry_path)], cwd=tmp_path, check=True)
    inspected = json.loads(subprocess.check_output([
        sys.executable, "-m", "ciw.net", "container", "inspect", str(telemetry_path)
    ], cwd=tmp_path, text=True))
    assert inspected["claims"]["physical_theory_established"] is False
    assert inspected["claims"]["shannon_information_inferred_from_bytes"] is False
