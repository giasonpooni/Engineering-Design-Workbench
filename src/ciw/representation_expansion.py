"""Evidence-bound representation expansion.

An EXPAND gate is not permission to invent a fine state. V1 resolves an already
retained richer representation, binds it to the exact scientific projection that
produced the coarse representation, and optionally replay-verifies that
projection before allowing a fresh planning-only gate over the richer
representation.

Evidence identity, retained execution identity, replay execution identity,
verification identity and Needle planning remain separate.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .control_contracts import content_ref, detached, keys, record, text
from .control_plane import run_graph
from .core.identities import content_identity, validate_evidence_identity
from .instruments import validate_run
from .operations.runner import check_seal, validate_execution
from .operations.schemas import validate_payload, validate_role
from .representation_interventions import gate_from_spec, plan_represented_needle, validate_gate
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry, compile_graph
from .session import Session

EXPANSION_CLAIMS = {
    "retained_richer_representation_resolved": True,
    "new_materialization_performed": False,
    "retained_projection_binding_validated": True,
    "projection_replay_verified": False,
    "unique_inverse_inferred": False,
    "canonical_state_mutated": False,
    "state_admission": False,
    "execution_authority": False,
}

VERIFICATION_CLAIMS = {
    "projection_replay_performed": True,
    "provider_execution": True,
    "empirical_physical_validity_established": False,
    "canonical_state_mutated": False,
    "state_admission": False,
    "execution_authority": False,
}

PROMOTION_CLAIMS = {
    "verified_expansion_required": True,
    "planning_transition_only": True,
    "provider_execution": False,
    "canonical_state_mutated": False,
    "state_admission": False,
    "execution_authority": False,
}


def _projection(registry: dict, gate: dict, morphism_id: str) -> dict:
    morphism_id = text(morphism_id)
    morphism = registry["morphisms"].get(morphism_id)
    if morphism is None:
        raise ValueError("Expansion references an unknown scientific morphism")
    if morphism["domain_representation_id"] != gate["recovery_representation_id"]:
        raise ValueError("Expansion morphism domain is not the resolved richer representation")
    if morphism["codomain_representation_id"] != gate["representation_id"]:
        raise ValueError("Expansion morphism codomain is not the current coarse representation")
    if morphism["semantic_capability"] is None:
        raise ValueError("Expansion V1 requires an executable semantic projection capability")
    return morphism


def _retained_projection(source_run: dict, execution: dict, result: dict,
                         morphism: dict, semantic: SemanticRegistry) -> dict:
    validate_run(source_run)
    validate_evidence_identity(source_run)
    check_seal(execution)
    check_seal(result)
    if result.get("schema") != "ciw.operation-result.v1":
        raise ValueError("Expansion requires a retained operation result")
    validate_execution(execution, source_run, execution["selection_revision"],
                       {result["result_id"]: result})
    if result["evidence_id"] != source_run["evidence_id"] or result["run_id"] != source_run["run_id"]:
        raise ValueError("Retained projection is bound to different source evidence")
    validate_role(result["operation_id"], result["role"])
    validate_payload(
        result["operation_id"], result["data"], source_run, result["parameters"],
        {"channel": result["channel"], "interval_s": result["interval_s"]},
    )
    resolution = semantic.resolve(morphism["semantic_capability"])
    if result["operation_id"] != resolution["operation_id"]:
        raise ValueError("Retained projection operation differs from current semantic lowering")
    if execution["operation_id"] != result["operation_id"]:
        raise ValueError("Retained execution/result operation identity mismatch")
    return {
        "semantic_resolution_ref": resolution["record_digest"],
        "operation_id": result["operation_id"],
        "engine_id": resolution["engine_id"],
        "runtime_family": resolution["runtime_family"],
        "source_evidence_ref": source_run["evidence_id"],
        "execution_ref": content_identity(execution),
        "result_ref": content_identity(result),
        "data_ref": content_identity(result["data"]),
        "runtime": deepcopy(result["runtime"]),
        "parameters": deepcopy(result["parameters"]),
        "channel": result["channel"],
        "interval_s": deepcopy(result["interval_s"]),
    }


def expansion_from_spec(source_run: dict, current_execution: dict, current_result: dict,
                        gate: dict, registry: dict, semantic: SemanticRegistry,
                        spec: dict) -> dict:
    """Resolve retained richer evidence for an exact EXPAND gate."""
    registry = validate_registry(registry, semantic)
    gate = validate_gate(gate, registry, semantic)
    if gate["decision"] != "EXPAND":
        raise ValueError("Representation expansion requires an EXPAND gate")
    keys(spec, {"expansion_id", "projection_morphism_id", "notes"})
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Expansion notes must be bounded text")
    validate_run(source_run)
    validate_evidence_identity(source_run)
    if source_run["evidence_id"] != gate["recovery_evidence_ref"]:
        raise ValueError("Retained richer evidence does not match the EXPAND gate")
    morphism = _projection(registry, gate, spec["projection_morphism_id"])
    retained = _retained_projection(source_run, current_execution, current_result, morphism, semantic)
    value = record(
        "representation-expansion",
        expansion_id=text(spec["expansion_id"]),
        source_gate_ref=gate["record_digest"],
        registry_ref=registry["record_digest"],
        current_representation_id=gate["representation_id"],
        current_representation_ref=gate["representation_ref"],
        richer_representation_id=gate["recovery_representation_id"],
        richer_representation_ref=gate["recovery_representation_ref"],
        source_evidence_ref=source_run["evidence_id"],
        projection_morphism_id=morphism["morphism_id"],
        projection_morphism_ref=morphism["record_digest"],
        retained_projection=retained,
        intervention_id=gate["intervention_id"],
        needle_target=deepcopy(gate["needle_target"]),
        notes=notes,
        claims=EXPANSION_CLAIMS,
    )
    validate_expansion(
        value, source_run, current_execution, current_result, gate, registry, semantic)
    return value


def validate_expansion(value: dict, source_run: dict, current_execution: dict,
                       current_result: dict, gate: dict, registry: dict,
                       semantic: SemanticRegistry) -> dict:
    keys(value, {
        "schema", "record_digest", "expansion_id", "source_gate_ref", "registry_ref",
        "current_representation_id", "current_representation_ref",
        "richer_representation_id", "richer_representation_ref", "source_evidence_ref",
        "projection_morphism_id", "projection_morphism_ref", "retained_projection",
        "intervention_id", "needle_target", "notes", "claims",
    })
    if value["schema"] != "ciw.representation-expansion.v1":
        raise ValueError("Wrong representation-expansion schema")
    check_seal(value)
    registry = validate_registry(registry, semantic)
    gate = validate_gate(gate, registry, semantic)
    if gate["decision"] != "EXPAND" or value["source_gate_ref"] != gate["record_digest"]:
        raise ValueError("Expansion is not bound to the exact EXPAND gate")
    if value["registry_ref"] != registry["record_digest"]:
        raise ValueError("Expansion is bound to a different morphism registry")
    morphism = _projection(registry, gate, value["projection_morphism_id"])
    retained = _retained_projection(source_run, current_execution, current_result, morphism, semantic)
    expected = {
        "current_representation_id": gate["representation_id"],
        "current_representation_ref": gate["representation_ref"],
        "richer_representation_id": gate["recovery_representation_id"],
        "richer_representation_ref": gate["recovery_representation_ref"],
        "source_evidence_ref": gate["recovery_evidence_ref"],
        "projection_morphism_ref": morphism["record_digest"],
        "retained_projection": retained,
        "intervention_id": gate["intervention_id"],
        "needle_target": gate["needle_target"],
    }
    for name, item in expected.items():
        if value[name] != item:
            raise ValueError("Expansion content contradicts retained evidence or projection binding")
    text(value["expansion_id"])
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("Expansion notes must be bounded text")
    if value["claims"] != EXPANSION_CLAIMS:
        raise ValueError("Expansion claims exceed retained-evidence resolution authority")
    return detached(value)


def verify_expansion(expansion: dict, source_run: dict, current_execution: dict,
                     current_result: dict, gate: dict, registry: dict,
                     semantic: SemanticRegistry, session_dir: Path) -> dict:
    """Replay the exact scientific projection from the same retained evidence."""
    expansion = validate_expansion(
        expansion, source_run, current_execution, current_result, gate, registry, semantic)
    morphism = registry["morphisms"][expansion["projection_morphism_id"]]
    graph = {
        "schema": "ciw.semantic-work-graph.v1",
        "graph_id": "verify-" + expansion["expansion_id"],
        "mandate": "Replay retained projection for representation expansion verification.",
        "model_id": "retained-evidence-projection.v1",
        "nodes": [{
            "node_id": "projection",
            "capability": morphism["semantic_capability"],
            "parameters": deepcopy(current_result["parameters"]),
            "inputs": {},
            "depends_on": [],
            "resources": [],
            "acceptance": {},
            "inspection": False,
        }],
    }
    compilation = compile_graph(graph, semantic)
    session = Session(source_run, Path(session_dir), operations=semantic.concrete.operations)
    replay_run = run_graph(session, compilation["experiment"], semantic.concrete)
    if replay_run["status"] != "completed":
        raise ValueError("Projection replay did not complete")
    node = replay_run["nodes"]["projection"]
    replay_execution, replay_result = node["execution"], node["result"]
    comparisons = {
        "source_evidence_equal": replay_execution["evidence_id"] == source_run["evidence_id"],
        "operation_equal": replay_result["operation_id"] == current_result["operation_id"],
        "parameters_equal": replay_result["parameters"] == current_result["parameters"],
        "runtime_equal": replay_result["runtime"] == current_result["runtime"],
        "data_equal": replay_result["data"] == current_result["data"],
    }
    status = "PASS" if all(comparisons.values()) else "FAIL"
    value = record(
        "representation-expansion-verification",
        verification_id="verify-" + expansion["expansion_id"],
        expansion_ref=expansion["record_digest"],
        source_evidence_ref=source_run["evidence_id"],
        current_execution_ref=content_identity(current_execution),
        current_result_ref=content_identity(current_result),
        replay_execution=deepcopy(replay_execution),
        replay_result=deepcopy(replay_result),
        replay_execution_ref=content_identity(replay_execution),
        replay_result_ref=content_identity(replay_result),
        comparisons=comparisons,
        status=status,
        claims=VERIFICATION_CLAIMS,
    )
    validate_expansion_verification(
        value, expansion, source_run, current_execution, current_result,
        gate, registry, semantic)
    return value


def validate_expansion_verification(value: dict, expansion: dict, source_run: dict,
                                    current_execution: dict, current_result: dict,
                                    gate: dict, registry: dict,
                                    semantic: SemanticRegistry) -> dict:
    keys(value, {
        "schema", "record_digest", "verification_id", "expansion_ref",
        "source_evidence_ref", "current_execution_ref", "current_result_ref",
        "replay_execution", "replay_result", "replay_execution_ref", "replay_result_ref",
        "comparisons", "status", "claims",
    })
    if value["schema"] != "ciw.representation-expansion-verification.v1":
        raise ValueError("Wrong expansion-verification schema")
    check_seal(value)
    expansion = validate_expansion(
        expansion, source_run, current_execution, current_result, gate, registry, semantic)
    if value["expansion_ref"] != expansion["record_digest"]:
        raise ValueError("Verification references a different expansion")
    if value["source_evidence_ref"] != source_run["evidence_id"]:
        raise ValueError("Verification references different source evidence")
    if value["current_execution_ref"] != content_identity(current_execution):
        raise ValueError("Verification references a different retained execution")
    if value["current_result_ref"] != content_identity(current_result):
        raise ValueError("Verification references a different retained result")
    replay_execution, replay_result = value["replay_execution"], value["replay_result"]
    if value["replay_execution_ref"] != content_identity(replay_execution):
        raise ValueError("Replay execution reference mismatch")
    if value["replay_result_ref"] != content_identity(replay_result):
        raise ValueError("Replay result reference mismatch")
    validate_execution(
        replay_execution, source_run, replay_execution["selection_revision"],
        {replay_result["result_id"]: replay_result})
    validate_role(replay_result["operation_id"], replay_result["role"])
    validate_payload(
        replay_result["operation_id"], replay_result["data"], source_run,
        replay_result["parameters"],
        {"channel": replay_result["channel"], "interval_s": replay_result["interval_s"]},
    )
    comparisons = {
        "source_evidence_equal": replay_execution["evidence_id"] == source_run["evidence_id"],
        "operation_equal": replay_result["operation_id"] == current_result["operation_id"],
        "parameters_equal": replay_result["parameters"] == current_result["parameters"],
        "runtime_equal": replay_result["runtime"] == current_result["runtime"],
        "data_equal": replay_result["data"] == current_result["data"],
    }
    if value["comparisons"] != comparisons:
        raise ValueError("Expansion verification comparisons differ from retained records")
    expected_status = "PASS" if all(comparisons.values()) else "FAIL"
    if value["status"] != expected_status:
        raise ValueError("Expansion verification status contradicts retained replay")
    text(value["verification_id"])
    if value["claims"] != VERIFICATION_CLAIMS:
        raise ValueError("Expansion verification claims exceed replay authority")
    return detached(value)


def promote_expansion(expansion: dict, verification: dict, source_run: dict,
                      current_execution: dict, current_result: dict, gate: dict,
                      registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    """Create a fresh LOCAL planning gate only after a verified retained expansion."""
    expansion = validate_expansion(
        expansion, source_run, current_execution, current_result, gate, registry, semantic)
    verification = validate_expansion_verification(
        verification, expansion, source_run, current_execution, current_result,
        gate, registry, semantic)
    if verification["status"] != "PASS":
        raise ValueError("Only a PASS expansion verification may be promoted")
    keys(spec, {"promotion_id", "local_gate_id", "notes"})
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Promotion notes must be bounded text")
    local_gate = gate_from_spec(registry, semantic, {
        "gate_id": text(spec["local_gate_id"]),
        "representation_id": expansion["richer_representation_id"],
        "intervention_id": expansion["intervention_id"],
        "needle_target": deepcopy(expansion["needle_target"]),
        "recovery_representation_id": None,
        "recovery_evidence_ref": None,
        "notes": "Derived only after verified retained expansion: " + notes,
    })
    if local_gate["decision"] != "LOCAL":
        raise ValueError("Verified richer representation still does not support a LOCAL intervention")
    return record(
        "representation-expansion-promotion",
        promotion_id=text(spec["promotion_id"]),
        source_gate_ref=gate["record_digest"],
        expansion_ref=expansion["record_digest"],
        verification_ref=verification["record_digest"],
        source_evidence_ref=source_run["evidence_id"],
        richer_representation_id=expansion["richer_representation_id"],
        local_gate=local_gate,
        notes=notes,
        claims=PROMOTION_CLAIMS,
    )


def validate_promotion(value: dict, expansion: dict, verification: dict,
                       source_run: dict, current_execution: dict, current_result: dict,
                       gate: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    keys(value, {
        "schema", "record_digest", "promotion_id", "source_gate_ref", "expansion_ref",
        "verification_ref", "source_evidence_ref", "richer_representation_id",
        "local_gate", "notes", "claims",
    })
    if value["schema"] != "ciw.representation-expansion-promotion.v1":
        raise ValueError("Wrong expansion-promotion schema")
    check_seal(value)
    spec = {"promotion_id": value["promotion_id"],
            "local_gate_id": value["local_gate"]["gate_id"], "notes": value["notes"]}
    expected = promote_expansion(
        expansion, verification, source_run, current_execution, current_result,
        gate, registry, semantic, spec)
    if value != expected:
        raise ValueError("Expansion promotion differs from exact verified recomputation")
    return detached(value)


def plan_after_verified_expansion(
    baseline_graph_run: dict, needle_spec: dict, promotion: dict,
    expansion: dict, verification: dict, source_run: dict,
    current_execution: dict, current_result: dict, gate: dict,
    registry: dict, semantic: SemanticRegistry,
) -> dict:
    """Delegate to the original represented-Needle planner after full verification.

    This adds no alternate Needle semantics: promotion validation reconstructs the
    evidence chain, then the nested fresh LOCAL gate is passed unchanged into the
    existing plan_represented_needle function.
    """
    promotion = validate_promotion(
        promotion, expansion, verification, source_run, current_execution,
        current_result, gate, registry, semantic)
    plan = plan_represented_needle(
        baseline_graph_run, needle_spec, promotion["local_gate"], registry, semantic)
    return plan
