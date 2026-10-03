from copy import deepcopy
import json

import pytest

from ciw.control_plane import builtin_registry
from ciw.core.identities import content_identity
from ciw.nise_handoff import compile_handoff
from ciw.semantic_capabilities import builtin_semantic_registry


def schematic():
    value = {
        "schema": "nise.inference-schematic.v1",
        "schematic_id": None,
        "query": {
            "schema": "nise.query.v1",
            "query_id": "q1",
            "question": "Inspect the retained oscillator observations.",
            "focus_node_ids": ["oscillator"],
            "requested_capabilities": [
                "analysis.statistics.v1",
                "analysis.spectrum.v1",
                "missing.capability.v1",
            ],
            "max_hops": 2,
            "node_budget": 32,
            "include_hypotheses": False,
        },
        "catalog_id": "fixture-catalog",
        "catalog_digest": "sha256:" + "1" * 64,
        "V_q": [{
            "node_id": "oscillator", "kind": "ENTITY", "label": "Oscillator",
            "status": "DECLARED", "attributes": {}, "evidence_refs": [],
        }],
        "E_q": [],
        "M_q": [],
        "C_q": [],
        "O_q": [],
        "P_q": [
            {
                "node_id": "op.stats", "kind": "OPERATION", "label": "Statistics",
                "status": "DECLARED",
                "attributes": {"semantic_capability": "analysis.statistics.v1"},
                "evidence_refs": [],
            },
            {
                "node_id": "op.spectrum", "kind": "OPERATION", "label": "Spectrum",
                "status": "DECLARED",
                "attributes": {"semantic_capability": "analysis.spectrum.v1"},
                "evidence_refs": [],
            },
        ],
        "selection_trace": [],
        "unresolved_capabilities": ["missing.capability.v1"],
        "frontier": [],
        "claims": {
            "candidate_structure": True,
            "physical_truth_established": False,
            "execution_authority": False,
            "state_admission": False,
            "causal_proof": False,
        },
    }
    value["schematic_id"] = content_identity(
        {key: item for key, item in value.items() if key != "schematic_id"})
    return value


def binding(schematic_id):
    return {
        "schema": "ciw.nise-binding-plan.v1",
        "binding_id": "operator-binding-001",
        "schematic_id": schematic_id,
        "graph_id": "nise-oscillator-plan",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [
            {
                "nise_node_id": "op.stats",
                "node_id": "statistics",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": [],
                "resources": ["cpu"],
                "acceptance": {},
                "inspection": False,
            },
            {
                "nise_node_id": "op.spectrum",
                "node_id": "spectrum",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": ["statistics"],
                "resources": ["cpu"],
                "acceptance": {},
                "inspection": False,
            },
        ],
    }


def registry():
    concrete = builtin_registry(bind=True)
    return builtin_semantic_registry(concrete)


def test_real_handoff_compiles_through_existing_semantic_plane():
    s = schematic()
    result = compile_handoff(s, binding(s["schematic_id"]), registry())
    assert result["schema"] == "ciw.nise-handoff.v1"
    assert result["claims"]["execution_authority"] is False
    assert result["claims"]["engine_selected_by_nise"] is False
    assert result["claims"]["parameters_selected_by_nise"] is False
    assert result["unresolved_capabilities"] == ["missing.capability.v1"]
    experiment = result["semantic_compilation"]["experiment"]
    assert [node["operation_id"] for node in experiment["nodes"]] == [
        "statistics.v1", "spectrum.periodogram.v1"]
    assert result["semantic_compilation"]["authorizes_execution"] is False


def test_nise_capability_cannot_be_replaced_by_binding():
    s = schematic()
    b = binding(s["schematic_id"])
    b["nodes"][0]["capability"] = "analysis.spectrum.v1"
    with pytest.raises(ValueError):
        compile_handoff(s, b, registry())


def test_binding_cannot_target_operation_absent_from_schematic():
    s = schematic()
    b = binding(s["schematic_id"])
    b["nodes"][0]["nise_node_id"] = "op.missing"
    with pytest.raises(ValueError, match="absent"):
        compile_handoff(s, b, registry())


def test_binding_must_match_schematic_identity():
    s = schematic()
    b = binding("sha256:" + "9" * 64)
    with pytest.raises(ValueError, match="different"):
        compile_handoff(s, b, registry())


def test_tampered_schematic_identity_refuses():
    s = schematic()
    s["query"]["question"] = "tampered"
    with pytest.raises(ValueError, match="identity"):
        compile_handoff(s, binding(s["schematic_id"]), registry())


def test_hypothesized_operation_cannot_be_bound():
    s = schematic()
    s["P_q"][0]["status"] = "HYPOTHESIZED"
    s["schematic_id"] = content_identity(
        {key: item for key, item in s.items() if key != "schematic_id"})
    with pytest.raises(ValueError, match="Hypothesized"):
        compile_handoff(s, binding(s["schematic_id"]), registry())


def test_unselected_schematic_operation_is_retained_as_unbound():
    s = schematic()
    b = binding(s["schematic_id"])
    b["nodes"] = b["nodes"][:1]
    result = compile_handoff(s, b, registry())
    assert result["unbound_schematic_operations"] == [{
        "nise_node_id": "op.spectrum",
        "capability": "analysis.spectrum.v1",
        "epistemic_status": "DECLARED",
    }]


def test_schematic_cannot_self_grant_execution_authority():
    s = schematic()
    s["claims"]["execution_authority"] = True
    s["schematic_id"] = content_identity(
        {key: item for key, item in s.items() if key != "schematic_id"})
    with pytest.raises(ValueError, match="authority"):
        compile_handoff(s, binding(s["schematic_id"]), registry())
