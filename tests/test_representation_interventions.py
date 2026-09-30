import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, experiment, run_graph
from ciw.instruments import make_demo_run
from ciw.representation_interventions import (
    gate_from_spec,
    plan_represented_needle,
)
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.session import Session


def scale(label):
    return {
        "length_m": None,
        "time_s": None,
        "energy_j": None,
        "resolution": None,
        "label": label,
    }


def registry_specs():
    representations = [
        {
            "representation_id": "signal.timeseries.uniform-scalar.v1",
            "role": "SIGNAL",
            "source_state_type": "retained-recording-channel",
            "schema_id": "ciw.run-channel.v1",
            "quantity_semantics": "uniform sampled scalar signal",
            "unit_semantics": "source-channel-unit",
            "frame_semantics": "source-recording-coordinate-frame",
            "time_semantics": "retained source sample clock",
            "scale": scale("source-time-series"),
            "uncertainty_semantics": "source-declared-or-none",
            "equivalence_contract": "EXACT",
            "preserved_queries": ["retained-sample-values"],
            "supported_interventions": ["select-channel-and-half-open-interval"],
            "recovery_route": "retained source recording",
            "provenance_refs": [],
            "notes": "",
        },
        {
            "representation_id": "signal.periodogram.one-sided-density.v1",
            "role": "SPECTRAL",
            "source_state_type": "derived-spectral-result",
            "schema_id": "ciw.periodogram-data.v1",
            "quantity_semantics": "one-sided power spectral density",
            "unit_semantics": "(source-channel-unit)^2/Hz",
            "frame_semantics": "frequency axis from source sample rate",
            "time_semantics": "selected source interval summary",
            "scale": scale("frequency-domain"),
            "uncertainty_semantics": "no uncertainty model declared",
            "equivalence_contract": "TASK_SPECIFIC",
            "preserved_queries": ["frequency-grid", "peak-frequency"],
            "supported_interventions": [],
            "recovery_route": "retained source recording",
            "provenance_refs": [],
            "notes": "",
        },
    ]
    morphisms = [{
        "morphism_id": "signal.periodogram.transform.v1",
        "kind": "TRANSFORM",
        "domain_representation_id": "signal.timeseries.uniform-scalar.v1",
        "codomain_representation_id": "signal.periodogram.one-sided-density.v1",
        "semantic_capability": "analysis.spectrum.v1",
        "parameter_names": ["channel", "interval_s"],
        "preconditions": ["retained source recording validates"],
        "validity": {
            "assumptions": ["periodic Hann window"],
            "operating_regime": ["finite source signal"],
            "failure_conditions": ["fewer than four samples"],
        },
        "preservation": {
            "queries": ["frequency-grid", "peak-frequency"],
            "interventions": [],
            "invariants": ["source evidence identity retained"],
            "approximation_tolerance": None,
        },
        "loss": {
            "class": "LOSSY",
            "description": "Phase and time-local source ordering are not retained.",
            "metrics": {"phase_retained": False},
        },
        "uncertainty": {"behavior": "UNKNOWN", "method": None},
        "reversibility": "NONE",
        "authority_requirements": ["read:recording"],
        "verification_requirements": ["source evidence retained"],
        "provenance_refs": [],
        "notes": "",
    }]
    return representations, morphisms


def registry():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    representations, morphisms = registry_specs()
    return concrete, semantic, registry_from_specs(representations, morphisms, semantic)


def baseline(tmp_path):
    concrete = builtin_registry(bind=True)
    source = make_demo_run()
    graph = experiment(
        "represented-needle-v1",
        model_id="analytic-damped-oscillator.v1",
        nodes=[{
            "node_id": "statistics",
            "operation_id": "statistics.v1",
            "parameters": {"channel": "q"},
            "inputs": {},
            "depends_on": [],
        }],
    )
    session = Session(source, tmp_path / "session", operations=concrete.operations)
    run = run_graph(session, graph, concrete)
    assert run["status"] == "completed"
    return source, run


def needle_spec():
    return {
        "needle_id": "q-to-v",
        "target": {
            "kind": "NODE_PARAMETER",
            "node_id": "statistics",
            "parameter": "channel",
        },
        "replacement": "v",
        "propagation": {
            "relation": "DEPENDENCY",
            "scope": "DESCENDANTS_INCLUSIVE",
        },
    }


def gate_spec(representation_id, *, recovery_representation_id=None, recovery_evidence_ref=None):
    return {
        "gate_id": "represented-channel-selection",
        "representation_id": representation_id,
        "intervention_id": "select-channel-and-half-open-interval",
        "needle_target": {"node_id": "statistics", "parameter": "channel"},
        "recovery_representation_id": recovery_representation_id,
        "recovery_evidence_ref": recovery_evidence_ref,
        "notes": "",
    }


def test_local_gate_allows_intervention_explicitly_supported_by_current_representation():
    _, semantic, registry_value = registry()
    gate = gate_from_spec(
        registry_value,
        semantic,
        gate_spec("signal.timeseries.uniform-scalar.v1"),
    )
    assert gate["decision"] == "LOCAL"
    assert gate["recovery_representation_id"] is None
    assert gate["claims"]["representation_contract_enforced"] is True


def test_lossy_periodogram_refuses_time_domain_intervention_without_resolved_recovery():
    _, semantic, registry_value = registry()
    gate = gate_from_spec(
        registry_value,
        semantic,
        gate_spec("signal.periodogram.one-sided-density.v1"),
    )
    assert gate["decision"] == "REFUSE"
    assert gate["recovery_route"] == "retained source recording"


def test_lossy_periodogram_requests_expansion_when_richer_representation_and_evidence_are_supplied():
    _, semantic, registry_value = registry()
    evidence = "sha256:" + "a" * 64
    gate = gate_from_spec(
        registry_value,
        semantic,
        gate_spec(
            "signal.periodogram.one-sided-density.v1",
            recovery_representation_id="signal.timeseries.uniform-scalar.v1",
            recovery_evidence_ref=evidence,
        ),
    )
    assert gate["decision"] == "EXPAND"
    assert gate["recovery_representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert gate["recovery_evidence_ref"] == evidence
    assert gate["claims"]["materialization_performed"] is False


def test_expansion_refuses_when_recovery_representation_still_lacks_intervention():
    _, semantic, registry_value = registry()
    with pytest.raises(ValueError, match="still does not support"):
        gate_from_spec(
            registry_value,
            semantic,
            gate_spec(
                "signal.periodogram.one-sided-density.v1",
                recovery_representation_id="signal.periodogram.one-sided-density.v1",
                recovery_evidence_ref="sha256:" + "b" * 64,
            ),
        )


def test_represented_needle_plan_requires_local_gate(tmp_path):
    _, run = baseline(tmp_path)
    _, semantic, registry_value = registry()

    local = gate_from_spec(
        registry_value, semantic,
        gate_spec("signal.timeseries.uniform-scalar.v1"),
    )
    plan = plan_represented_needle(
        run, needle_spec(), local, registry_value, semantic)
    assert plan["target"]["node_id"] == "statistics"

    refused = gate_from_spec(
        registry_value, semantic,
        gate_spec("signal.periodogram.one-sided-density.v1"),
    )
    with pytest.raises(ValueError, match="not supported"):
        plan_represented_needle(
            run, needle_spec(), refused, registry_value, semantic)

    expanded = gate_from_spec(
        registry_value, semantic,
        gate_spec(
            "signal.periodogram.one-sided-density.v1",
            recovery_representation_id="signal.timeseries.uniform-scalar.v1",
            recovery_evidence_ref=run["source_evidence_id"],
        ),
    )
    with pytest.raises(ValueError, match="expansion/materialization"):
        plan_represented_needle(
            run, needle_spec(), expanded, registry_value, semantic)


def test_gate_must_target_same_needle_coordinate(tmp_path):
    _, run = baseline(tmp_path)
    _, semantic, registry_value = registry()
    gate = gate_from_spec(
        registry_value, semantic,
        {
            **gate_spec("signal.timeseries.uniform-scalar.v1"),
            "needle_target": {"node_id": "statistics", "parameter": "other"},
        },
    )
    with pytest.raises(ValueError, match="different Needle coordinate"):
        plan_represented_needle(
            run, needle_spec(), gate, registry_value, semantic)


def test_cli_gate_refuses_periodogram_intervention(tmp_path):
    concrete, semantic, registry_value = registry()
    registry_path = tmp_path / "registry.json"
    spec_path = tmp_path / "gate-spec.json"
    gate_path = tmp_path / "gate.json"
    registry_path.write_text(json.dumps(registry_value))
    spec_path.write_text(json.dumps(
        gate_spec("signal.periodogram.one-sided-density.v1")))

    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "gate",
        str(registry_path), str(spec_path), "--output", str(gate_path),
    ], cwd=tmp_path, check=True)
    value = json.loads(gate_path.read_text())
    assert value["decision"] == "REFUSE"
    assert value["claims"]["materialization_performed"] is False
