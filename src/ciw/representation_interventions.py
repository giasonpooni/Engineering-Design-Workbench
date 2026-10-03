"""Representation-aware intervention gate for Needle.

A representation may be sufficient for a query but insufficient for an
intervention. This gate decides whether a named intervention may be performed
locally, requires expansion to a richer retained representation, or must refuse.

The gate is descriptive/authoritative only over planning. It never materializes
data, executes a provider, mutates state, or claims that a representation is
scientifically sufficient beyond its explicit contract.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .control_contracts import content_ref, detached, keys, record, text
from .needle import plan_from_spec, validate_plan
from .operations.runner import check_seal
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry

DECISIONS = {"LOCAL", "EXPAND", "REFUSE"}


def _needle_target(value: Any) -> dict:
    keys(value, {"node_id", "parameter"})
    return {"node_id": text(value["node_id"]), "parameter": text(value["parameter"])}


def _resolve(registry: dict, representation_id: str, intervention_id: str,
             recovery_representation_id: str | None,
             recovery_evidence_ref: str | None) -> dict:
    representations = registry["representations"]
    if representation_id not in representations:
        raise ValueError("Intervention gate references unknown current representation")
    current = representations[representation_id]

    if intervention_id in current["supported_interventions"]:
        if recovery_representation_id is not None or recovery_evidence_ref is not None:
            raise ValueError("LOCAL intervention must not declare recovery materialization")
        return {
            "decision": "LOCAL",
            "reason": "Intervention is explicitly supported by the current representation contract.",
            "recovery_route": None,
            "recovery_representation_id": None,
            "recovery_representation_ref": None,
            "recovery_evidence_ref": None,
        }

    route = current["recovery_route"]
    if recovery_representation_id is not None or recovery_evidence_ref is not None:
        if route is None:
            raise ValueError("Current representation declares no recovery route")
        if recovery_representation_id is None or recovery_evidence_ref is None:
            raise ValueError("Resolved expansion requires both recovery representation and retained evidence")
        if recovery_representation_id not in representations:
            raise ValueError("Recovery representation is absent from the registry")
        recovery = representations[recovery_representation_id]
        if intervention_id not in recovery["supported_interventions"]:
            raise ValueError("Recovery representation still does not support the requested intervention")
        return {
            "decision": "EXPAND",
            "reason": "Current representation does not support the intervention; retained richer representation does.",
            "recovery_route": route,
            "recovery_representation_id": recovery_representation_id,
            "recovery_representation_ref": recovery["record_digest"],
            "recovery_evidence_ref": content_ref(recovery_evidence_ref),
        }

    return {
        "decision": "REFUSE",
        "reason": (
            "Current representation does not support the intervention and no "
            "resolved richer representation/evidence was supplied."
        ),
        "recovery_route": route,
        "recovery_representation_id": None,
        "recovery_representation_ref": None,
        "recovery_evidence_ref": None,
    }


def gate_from_spec(registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    registry = validate_registry(registry, semantic)
    keys(spec, {
        "gate_id", "representation_id", "intervention_id", "needle_target",
        "recovery_representation_id", "recovery_evidence_ref", "notes",
    })
    representation_id = text(spec["representation_id"])
    intervention_id = text(spec["intervention_id"])
    recovery_representation_id = spec["recovery_representation_id"]
    if recovery_representation_id is not None:
        recovery_representation_id = text(recovery_representation_id)
    recovery_evidence_ref = spec["recovery_evidence_ref"]
    if recovery_evidence_ref is not None:
        recovery_evidence_ref = content_ref(recovery_evidence_ref)
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Intervention-gate notes must be bounded text")

    if representation_id not in registry["representations"]:
        raise ValueError("Intervention gate references unknown representation")
    current = registry["representations"][representation_id]
    resolution = _resolve(
        registry,
        representation_id,
        intervention_id,
        recovery_representation_id,
        recovery_evidence_ref,
    )

    value = record(
        "intervention-gate",
        gate_id=text(spec["gate_id"]),
        registry_ref=registry["record_digest"],
        representation_id=representation_id,
        representation_ref=current["record_digest"],
        intervention_id=intervention_id,
        needle_target=_needle_target(spec["needle_target"]),
        decision=resolution["decision"],
        reason=resolution["reason"],
        recovery_route=resolution["recovery_route"],
        recovery_representation_id=resolution["recovery_representation_id"],
        recovery_representation_ref=resolution["recovery_representation_ref"],
        recovery_evidence_ref=resolution["recovery_evidence_ref"],
        notes=notes,
        claims={
            "query_sufficiency_not_intervention_sufficiency": True,
            "representation_contract_enforced": True,
            "materialization_performed": False,
            "provider_execution": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_gate(value, registry, semantic)
    return value


def validate_gate(value: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    registry = validate_registry(registry, semantic)
    keys(value, {
        "schema", "record_digest", "gate_id", "registry_ref",
        "representation_id", "representation_ref", "intervention_id",
        "needle_target", "decision", "reason", "recovery_route",
        "recovery_representation_id", "recovery_representation_ref",
        "recovery_evidence_ref", "notes", "claims",
    })
    if value["schema"] != "ciw.intervention-gate.v1":
        raise ValueError("Wrong intervention-gate schema")
    check_seal(value)
    text(value["gate_id"])
    content_ref(value["registry_ref"])
    if value["registry_ref"] != registry["record_digest"]:
        raise ValueError("Intervention gate is bound to a different morphism registry")
    representation_id = text(value["representation_id"])
    if representation_id not in registry["representations"]:
        raise ValueError("Intervention gate references unknown representation")
    current = registry["representations"][representation_id]
    content_ref(value["representation_ref"])
    if value["representation_ref"] != current["record_digest"]:
        raise ValueError("Intervention gate representation identity mismatch")
    intervention_id = text(value["intervention_id"])
    _needle_target(value["needle_target"])
    if value["decision"] not in DECISIONS:
        raise ValueError("Unknown intervention-gate decision")
    text(value["reason"])

    recovery_id = value["recovery_representation_id"]
    if recovery_id is not None:
        recovery_id = text(recovery_id)
    recovery_evidence = value["recovery_evidence_ref"]
    if recovery_evidence is not None:
        recovery_evidence = content_ref(recovery_evidence)

    expected = _resolve(
        registry,
        representation_id,
        intervention_id,
        recovery_id,
        recovery_evidence,
    )
    for name in (
        "decision", "recovery_route", "recovery_representation_id",
        "recovery_representation_ref", "recovery_evidence_ref",
    ):
        if value[name] != expected[name]:
            raise ValueError("Intervention-gate decision/recovery data contradicts representation contracts")
    if value["reason"] != expected["reason"]:
        raise ValueError("Intervention-gate reason contradicts deterministic resolution")
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("Intervention-gate notes must be bounded text")
    if value["claims"] != {
        "query_sufficiency_not_intervention_sufficiency": True,
        "representation_contract_enforced": True,
        "materialization_performed": False,
        "provider_execution": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Intervention-gate claims exceed planning authority")
    return detached(value)


def plan_represented_needle(
    baseline_graph_run: dict,
    needle_spec: dict,
    gate: dict,
    registry: dict,
    semantic: SemanticRegistry,
) -> dict:
    """Create an ordinary Needle plan only after a LOCAL representation gate."""
    gate = validate_gate(gate, registry, semantic)
    keys(needle_spec, {"needle_id", "target", "replacement", "propagation"})
    target = needle_spec["target"]
    keys(target, {"kind", "node_id", "parameter"})
    if target["kind"] != "NODE_PARAMETER":
        raise ValueError("Representation-aware Needle V1 supports NODE_PARAMETER targets only")
    if {
        "node_id": target["node_id"],
        "parameter": target["parameter"],
    } != gate["needle_target"]:
        raise ValueError("Intervention gate targets a different Needle coordinate")
    if gate["decision"] == "EXPAND":
        raise ValueError(
            "Needle requires representation expansion/materialization before planning")
    if gate["decision"] == "REFUSE":
        raise ValueError(
            "Needle intervention is not supported by the current representation")
    plan = plan_from_spec(baseline_graph_run, needle_spec)
    validate_plan(plan)
    return plan


def inspect_gate(value: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    checked = validate_gate(value, registry, semantic)
    return {
        "schema": "ciw.intervention-gate-inspection.v1",
        "record_digest": checked["record_digest"],
        "gate_id": checked["gate_id"],
        "representation_id": checked["representation_id"],
        "intervention_id": checked["intervention_id"],
        "decision": checked["decision"],
        "needle_target": deepcopy(checked["needle_target"]),
        "recovery_representation_id": checked["recovery_representation_id"],
        "recovery_evidence_ref": checked["recovery_evidence_ref"],
        "materialization_performed": False,
        "provider_execution": False,
        "execution_authority": False,
    }
