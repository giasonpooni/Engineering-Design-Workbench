"""Evidence-bound recovery of a richer retained representation.

This module closes one narrow gap in representation-aware Needle.  An EXPAND
planning decision names a richer representation and source evidence, but that
name/hash pair is not itself proof that the retained source exists or that the
current coarse result was actually derived from it.

V1 therefore validates an already-retained source run, transform execution,
result and finite morphism witness.  It does not fetch data, rerun a provider,
admit canonical state or authorize execution.  Only after this evidence is
resolved can a *new* LOCAL intervention gate be derived for the richer
representation.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .control_contracts import detached, keys, record, text
from .core.identities import content_identity, validate_evidence_identity
from .instruments import validate_run
from .operations.runner import check_seal, validate_execution
from .operations.schemas import validate_payload
from .representation_interventions import gate_from_spec, plan_represented_needle, validate_gate
from .representation_morphisms import validate_registry, validate_witness
from .semantic_capabilities import SemanticRegistry

PROJECTION_KINDS = {"PROJECT", "COARSEN", "TRANSFORM"}


def _notes(value: Any, label: str) -> str:
    if type(value) is not str or len(value) > 4096:
        raise ValueError(f"{label} must be bounded text")
    return value


def _bound_operation(semantic: SemanticRegistry, capability: str, operation_id: str) -> dict:
    catalog = semantic.catalog()
    rows = catalog["lowerings"].get(capability)
    if not rows:
        raise ValueError("Projection capability has no declared semantic lowering")
    matches = [row for row in rows if row["operation_id"] == operation_id and row["bound"]]
    if len(matches) != 1:
        raise ValueError("Retained projection execution is not an exactly bound semantic lowering")
    return detached(matches[0])


def _validate_retained_projection(source_run: dict, execution: dict, result: dict,
                                  morphism: dict, semantic: SemanticRegistry) -> dict:
    """Validate retained artifacts without running the numerical provider."""
    validate_run(source_run)
    validate_evidence_identity(source_run)
    check_seal(execution)
    check_seal(result)
    if execution.get("status") != "completed":
        raise ValueError("Representation expansion requires a completed retained projection execution")
    if result.get("schema") != "ciw.operation-result.v1":
        raise ValueError("Representation expansion requires a retained operation result")
    if result.get("result_id") != execution.get("result_id"):
        raise ValueError("Retained projection execution/result identity mismatch")
    if result.get("execution_id") != execution.get("execution_id"):
        raise ValueError("Retained projection result references a different execution")
    for field in ("operation_id", "evidence_id", "run_id", "runtime", "parameters",
                  "selection_revision", "channel", "interval_s", "created_at"):
        if result.get(field) != execution.get(field):
            raise ValueError(f"Retained projection execution/result {field} mismatch")
    if execution.get("evidence_id") != source_run["evidence_id"] or result.get("evidence_id") != source_run["evidence_id"]:
        raise ValueError("Retained projection artifacts reference different source evidence")
    if execution.get("run_id") != source_run["run_id"] or result.get("run_id") != source_run["run_id"]:
        raise ValueError("Retained projection artifacts reference a different source run")

    # Reuse the trusted occurrence validator and saved-payload validator.  This
    # checks source binding and the result's declared scientific payload shape,
    # but deliberately does not rerun the provider.
    validate_execution(execution, source_run, execution["selection_revision"],
                       {result["result_id"]: result})
    selection = {
        "revision": execution["selection_revision"],
        "channel": execution["channel"],
        "interval_s": deepcopy(execution["interval_s"]),
    }
    validate_payload(execution["operation_id"], result["data"], source_run,
                     execution["parameters"], selection)

    capability = morphism["semantic_capability"]
    if capability is None:
        raise ValueError("Evidence-bound expansion requires an executable projection capability")
    lowering = _bound_operation(semantic, capability, execution["operation_id"])
    declared = set(morphism["parameter_names"])
    if not set(execution["parameters"]) <= declared:
        raise ValueError("Projection execution used a parameter absent from the scientific morphism")
    return lowering


def resolve_expansion(registry: dict, semantic: SemanticRegistry, gate: dict,
                      source_run: dict, witness: dict, execution: dict, result: dict,
                      spec: dict) -> dict:
    """Resolve an EXPAND gate against actual retained richer-state evidence."""
    registry = validate_registry(registry, semantic)
    gate = validate_gate(gate, registry, semantic)
    if gate["decision"] != "EXPAND":
        raise ValueError("Evidence-bound expansion requires an EXPAND intervention gate")
    keys(spec, {"expansion_id", "projection_morphism_id", "notes"})
    expansion_id = text(spec["expansion_id"])
    morphism_id = text(spec["projection_morphism_id"])
    notes = _notes(spec["notes"], "Expansion notes")

    if morphism_id not in registry["morphisms"]:
        raise ValueError("Expansion references an unknown projection morphism")
    morphism = registry["morphisms"][morphism_id]
    if morphism["kind"] not in PROJECTION_KINDS:
        raise ValueError("Expansion requires a PROJECT, COARSEN or TRANSFORM morphism")
    if morphism["domain_representation_id"] != gate["recovery_representation_id"]:
        raise ValueError("Projection domain is not the richer recovery representation")
    if morphism["codomain_representation_id"] != gate["representation_id"]:
        raise ValueError("Projection codomain is not the current coarse representation")

    recovery = registry["representations"][gate["recovery_representation_id"]]
    current = registry["representations"][gate["representation_id"]]
    validate_run(source_run)
    validate_evidence_identity(source_run)
    if source_run["evidence_id"] != gate["recovery_evidence_ref"]:
        raise ValueError("Retained richer source evidence does not match the EXPAND gate")

    witness = validate_witness(witness, registry)
    if witness["morphism_id"] != morphism_id or witness["morphism_ref"] != morphism["record_digest"]:
        raise ValueError("Projection witness is bound to a different scientific morphism")
    if witness["source_evidence_id"] != source_run["evidence_id"]:
        raise ValueError("Projection witness references different source evidence")
    statuses = {name: sum(row["status"] == name for row in witness["checks"])
                for name in ("PASS", "FAIL", "UNRESOLVED")}
    if statuses["FAIL"]:
        raise ValueError("Projection witness contains a failed retained check")
    if statuses["PASS"] < 1:
        raise ValueError("Projection witness requires at least one passing retained check")

    lowering = _validate_retained_projection(source_run, execution, result, morphism, semantic)
    execution_ref = content_identity(execution)
    result_ref = content_identity(result)
    if execution_ref != witness["execution_ref"] or result_ref != witness["result_ref"]:
        raise ValueError("Retained projection artifacts do not match the morphism witness")

    value = record(
        "representation-expansion",
        expansion_id=expansion_id,
        registry_ref=registry["record_digest"],
        gate_ref=gate["record_digest"],
        current_representation_id=current["representation_id"],
        current_representation_ref=current["record_digest"],
        recovery_representation_id=recovery["representation_id"],
        recovery_representation_ref=recovery["record_digest"],
        source_run_ref=content_identity(source_run),
        source_evidence_id=source_run["evidence_id"],
        projection_morphism_id=morphism_id,
        projection_morphism_ref=morphism["record_digest"],
        semantic_capability=morphism["semantic_capability"],
        operation_id=execution["operation_id"],
        lowering_ref=content_identity(lowering),
        witness_ref=witness["record_digest"],
        execution_ref=execution_ref,
        result_ref=result_ref,
        runtime_ref=content_identity(execution["runtime"]),
        witness_status=statuses,
        notes=notes,
        claims={
            "retained_richer_representation_resolved": True,
            "source_evidence_identity_verified": True,
            "projection_contract_direction_verified": True,
            "retained_projection_payload_validated": True,
            "projection_reexecuted": False,
            "unique_inverse_inferred": False,
            "materialization_performed": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    return value


def validate_expansion(value: dict, registry: dict, semantic: SemanticRegistry, gate: dict,
                       source_run: dict, witness: dict, execution: dict, result: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "expansion_id", "registry_ref", "gate_ref",
        "current_representation_id", "current_representation_ref",
        "recovery_representation_id", "recovery_representation_ref",
        "source_run_ref", "source_evidence_id", "projection_morphism_id",
        "projection_morphism_ref", "semantic_capability", "operation_id", "lowering_ref",
        "witness_ref", "execution_ref", "result_ref", "runtime_ref", "witness_status",
        "notes", "claims",
    })
    check_seal(value)
    expected = resolve_expansion(
        registry, semantic, gate, source_run, witness, execution, result,
        {"expansion_id": value["expansion_id"],
         "projection_morphism_id": value["projection_morphism_id"],
         "notes": value["notes"]},
    )
    if value != expected:
        raise ValueError("Representation expansion differs from exact evidence recomputation")
    return detached(value)


def reconsider_after_expansion(registry: dict, semantic: SemanticRegistry, gate: dict,
                               expansion: dict, source_run: dict, witness: dict,
                               execution: dict, result: dict, spec: dict) -> dict:
    """Derive a fresh LOCAL gate only from a fully revalidated expansion record."""
    gate = validate_gate(gate, registry, semantic)
    expansion = validate_expansion(expansion, registry, semantic, gate, source_run,
                                   witness, execution, result)
    keys(spec, {"reconsideration_id", "local_gate_id", "notes"})
    notes = _notes(spec["notes"], "Reconsideration notes")
    local_gate = gate_from_spec(registry, semantic, {
        "gate_id": text(spec["local_gate_id"]),
        "representation_id": expansion["recovery_representation_id"],
        "intervention_id": gate["intervention_id"],
        "needle_target": deepcopy(gate["needle_target"]),
        "recovery_representation_id": None,
        "recovery_evidence_ref": None,
        "notes": "Derived only after evidence-bound retained-representation expansion.",
    })
    if local_gate["decision"] != "LOCAL":
        raise ValueError("Recovered richer representation did not produce a LOCAL intervention gate")
    return record(
        "intervention-reconsideration",
        reconsideration_id=text(spec["reconsideration_id"]),
        registry_ref=registry["record_digest"],
        prior_gate_ref=gate["record_digest"],
        expansion_ref=expansion["record_digest"],
        source_evidence_id=expansion["source_evidence_id"],
        local_gate=local_gate,
        notes=notes,
        claims={
            "prior_expand_gate_preserved": True,
            "evidence_bound_expansion_revalidated": True,
            "fresh_local_gate_derived": True,
            "candidate_execution_performed": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )


def validate_reconsideration(value: dict, registry: dict, semantic: SemanticRegistry,
                             gate: dict, expansion: dict, source_run: dict, witness: dict,
                             execution: dict, result: dict) -> dict:
    keys(value, {"schema", "record_digest", "reconsideration_id", "registry_ref",
                 "prior_gate_ref", "expansion_ref", "source_evidence_id", "local_gate",
                 "notes", "claims"})
    check_seal(value)
    expected = reconsider_after_expansion(
        registry, semantic, gate, expansion, source_run, witness, execution, result,
        {"reconsideration_id": value["reconsideration_id"],
         "local_gate_id": value["local_gate"]["gate_id"],
         "notes": value["notes"]},
    )
    if value != expected:
        raise ValueError("Intervention reconsideration differs from exact evidence recomputation")
    return detached(value)


def plan_after_expansion(baseline_graph_run: dict, needle_spec: dict, registry: dict,
                         semantic: SemanticRegistry, gate: dict, expansion: dict,
                         reconsideration: dict, source_run: dict, witness: dict,
                         execution: dict, result: dict) -> dict:
    """Create an ordinary Needle plan after evidence-bound recovery and reconsideration."""
    reconsideration = validate_reconsideration(
        reconsideration, registry, semantic, gate, expansion, source_run,
        witness, execution, result)
    if baseline_graph_run.get("source_evidence_id") != reconsideration["source_evidence_id"]:
        raise ValueError("Needle baseline uses different evidence from the resolved richer representation")
    return plan_represented_needle(
        baseline_graph_run, needle_spec, reconsideration["local_gate"], registry, semantic)
