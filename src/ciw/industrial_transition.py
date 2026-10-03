"""Industrial identity continuity and proposal-transition envelope V1.

This module connects three boundaries that were previously separate:

1. identity continuity across heterogeneous industrial references;
2. semantic continuity through the typed preservation layer;
3. authority handoff before canonical-state admission.

It deliberately stops before admission. A verified identity binding and an
eligible preservation gate can make a proposal READY_FOR_AUTHORITY_REVIEW, but
cannot mutate canonical state.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .control_contracts import content_ref, detached, keys, record, text, validate_state
from .operations.runner import check_seal
from .preservation_contracts import (
    validate_admission_gate,
    validate_contract,
    validate_verification,
)
from .semantic_capabilities import SemanticRegistry

ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
OBJECT_KINDS = {
    "PHYSICAL_ASSET",
    "CAD_OBJECT",
    "BIM_OBJECT",
    "SENSOR_TAG",
    "ERP_ASSET",
    "MES_ASSET",
    "QMS_RECORD",
    "SIMULATION_VARIABLE",
    "SPECIFICATION",
    "DOCUMENT",
    "OTHER",
}
IDENTITY_STATUS = {"VERIFIED", "REFUTED", "UNRESOLVED"}
IDENTITY_METHODS = {
    "EXACT_IDENTIFIER",
    "DECLARED_MAPPING",
    "CROSS_SYSTEM_EVIDENCE",
    "HUMAN_ATTESTATION",
    "NOT_PERFORMED",
}
PROPOSER_KINDS = {
    "HUMAN",
    "LLM",
    "OPTIMIZER",
    "SOLVER",
    "SIMULATOR",
    "RULE_SYSTEM",
    "OTHER",
}
READINESS = {"READY_FOR_AUTHORITY_REVIEW", "REFUSED", "UNRESOLVED"}
MAX_REFERENCES = 128


def _versioned(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None or len(value) > 180:
        raise ValueError(f"{label} must be a bounded versioned hierarchical ID")
    return value


def _notes(value: Any, label: str, maximum: int = 8192) -> str:
    if type(value) is not str or len(value) > maximum:
        raise ValueError(f"{label} must be bounded text")
    return value


def _reference(value: Any) -> dict:
    keys(value, {
        "reference_id", "system_id", "namespace", "external_id",
        "object_kind", "evidence_ref",
    })
    if value["object_kind"] not in OBJECT_KINDS:
        raise ValueError("Unknown industrial identity object kind")
    return {
        "reference_id": _versioned(value["reference_id"], "reference_id"),
        "system_id": _versioned(value["system_id"], "system_id"),
        "namespace": text(value["namespace"]),
        "external_id": text(value["external_id"]),
        "object_kind": value["object_kind"],
        "evidence_ref": content_ref(value["evidence_ref"]),
    }


def binding_from_spec(spec: dict) -> dict:
    """Declare a candidate cross-system identity map.

    This does not create or admit a canonical entity.
    """
    keys(spec, {"binding_id", "canonical_entity_id", "references", "notes"})
    references = spec["references"]
    if type(references) is not list or not 1 <= len(references) <= MAX_REFERENCES:
        raise ValueError("Identity binding requires 1..128 references")
    normalized = [_reference(row) for row in references]
    ids = [row["reference_id"] for row in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Identity binding contains duplicate reference IDs")
    system_keys = [
        (row["system_id"], row["namespace"], row["external_id"]) for row in normalized
    ]
    if len(system_keys) != len(set(system_keys)):
        raise ValueError("Identity binding repeats one external system identity")
    value = record(
        "entity-binding",
        binding_id=_versioned(spec["binding_id"], "binding_id"),
        canonical_entity_id=text(spec["canonical_entity_id"]),
        references=normalized,
        notes=_notes(spec["notes"], "identity binding notes"),
        claims={
            "candidate_identity_map": True,
            "canonical_entity_created": False,
            "identity_admission_performed": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_binding(value)
    return value


def validate_binding(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "binding_id", "canonical_entity_id",
        "references", "notes", "claims",
    })
    if value["schema"] != "ciw.entity-binding.v1":
        raise ValueError("Wrong entity-binding schema")
    check_seal(value)
    _versioned(value["binding_id"], "binding_id")
    text(value["canonical_entity_id"])
    if type(value["references"]) is not list or not 1 <= len(value["references"]) <= MAX_REFERENCES:
        raise ValueError("Entity binding requires 1..128 references")
    rows = [_reference(row) for row in value["references"]]
    ids = [row["reference_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Entity binding contains duplicate reference IDs")
    system_keys = [(row["system_id"], row["namespace"], row["external_id"]) for row in rows]
    if len(system_keys) != len(set(system_keys)):
        raise ValueError("Entity binding repeats one external system identity")
    _notes(value["notes"], "identity binding notes")
    if value["claims"] != {
        "candidate_identity_map": True,
        "canonical_entity_created": False,
        "identity_admission_performed": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Entity-binding claims exceed identity-mapping authority")
    return detached(value)


def _identity_check(value: Any) -> dict:
    keys(value, {
        "reference_id", "status", "method", "evidence_ref", "notes",
    })
    reference_id = _versioned(value["reference_id"], "reference_id")
    status = value["status"]
    if status not in IDENTITY_STATUS:
        raise ValueError("Unknown identity verification status")
    method = value["method"]
    if method not in IDENTITY_METHODS:
        raise ValueError("Unknown identity verification method")
    evidence = value["evidence_ref"]
    if status in {"VERIFIED", "REFUTED"}:
        if method == "NOT_PERFORMED":
            raise ValueError("Resolved identity check cannot use NOT_PERFORMED")
        evidence = content_ref(evidence)
    elif evidence is not None:
        evidence = content_ref(evidence)
    return {
        "reference_id": reference_id,
        "status": status,
        "method": method,
        "evidence_ref": evidence,
        "notes": _notes(value["notes"], "identity verification notes", 2048),
    }


def identity_verification_from_spec(binding: dict, spec: dict) -> dict:
    binding = validate_binding(binding)
    keys(spec, {"verification_id", "checks", "notes"})
    checks = spec["checks"]
    if type(checks) is not list or len(checks) != len(binding["references"]):
        raise ValueError("Identity verification must cover every bound external reference")
    normalized = [_identity_check(row) for row in checks]
    ids = [row["reference_id"] for row in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate identity verification reference")
    expected = {row["reference_id"] for row in binding["references"]}
    if set(ids) != expected:
        raise ValueError("Identity verification coverage differs from entity binding")
    if any(row["status"] == "REFUTED" for row in normalized):
        status = "REFUTED"
    elif all(row["status"] == "VERIFIED" for row in normalized):
        status = "VERIFIED"
    else:
        status = "UNRESOLVED"
    value = record(
        "entity-binding-verification",
        verification_id=_versioned(spec["verification_id"], "verification_id"),
        binding_ref=binding["record_digest"],
        canonical_entity_id=binding["canonical_entity_id"],
        checks=normalized,
        status=status,
        notes=_notes(spec["notes"], "identity verification notes"),
        claims={
            "cross_system_identity_checked": True,
            "identity_verification_is_not_admission": True,
            "canonical_entity_created": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_identity_verification(value, binding)
    return value


def validate_identity_verification(value: dict, binding: dict) -> dict:
    binding = validate_binding(binding)
    keys(value, {
        "schema", "record_digest", "verification_id", "binding_ref",
        "canonical_entity_id", "checks", "status", "notes", "claims",
    })
    if value["schema"] != "ciw.entity-binding-verification.v1":
        raise ValueError("Wrong entity-binding verification schema")
    check_seal(value)
    _versioned(value["verification_id"], "verification_id")
    if value["binding_ref"] != binding["record_digest"]:
        raise ValueError("Identity verification references a different entity binding")
    content_ref(value["binding_ref"])
    if value["canonical_entity_id"] != binding["canonical_entity_id"]:
        raise ValueError("Identity verification canonical entity differs from binding")
    if type(value["checks"]) is not list or len(value["checks"]) != len(binding["references"]):
        raise ValueError("Identity verification must cover every bound external reference")
    normalized = [_identity_check(row) for row in value["checks"]]
    ids = [row["reference_id"] for row in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate identity verification reference")
    expected_ids = {row["reference_id"] for row in binding["references"]}
    if set(ids) != expected_ids:
        raise ValueError("Identity verification coverage differs from binding")
    expected_status = (
        "REFUTED" if any(row["status"] == "REFUTED" for row in normalized)
        else "VERIFIED" if all(row["status"] == "VERIFIED" for row in normalized)
        else "UNRESOLVED"
    )
    if value["status"] != expected_status:
        raise ValueError("Identity verification aggregate status contradicts checks")
    _notes(value["notes"], "identity verification notes")
    if value["claims"] != {
        "cross_system_identity_checked": True,
        "identity_verification_is_not_admission": True,
        "canonical_entity_created": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Identity-verification claims exceed verification scope")
    return detached(value)


def _proposer(value: Any) -> dict:
    keys(value, {"kind", "proposer_id", "execution_ref", "notes"})
    if value["kind"] not in PROPOSER_KINDS:
        raise ValueError("Unknown transition proposer kind")
    execution_ref = value["execution_ref"]
    if execution_ref is not None:
        execution_ref = content_ref(execution_ref)
    return {
        "kind": value["kind"],
        "proposer_id": text(value["proposer_id"]),
        "execution_ref": execution_ref,
        "notes": _notes(value["notes"], "proposer notes", 2048),
    }


def _readiness(
    source_state: dict,
    candidate_state: dict,
    binding: dict,
    identity_verification: dict,
    preservation_gate: dict,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    source_entity = source_state["identity"]["entity_id"]
    candidate_entity = candidate_state["identity"]["entity_id"]
    canonical_entity = binding["canonical_entity_id"]

    refused = False
    unresolved = False

    if source_entity != canonical_entity:
        refused = True
        reasons.append("source_state_entity_differs_from_identity_binding")
    if candidate_entity != canonical_entity:
        refused = True
        reasons.append("candidate_state_entity_differs_from_identity_binding")

    if identity_verification["status"] == "REFUTED":
        refused = True
        reasons.append("cross_system_identity_refuted")
    elif identity_verification["status"] == "UNRESOLVED":
        unresolved = True
        reasons.append("cross_system_identity_unresolved")

    if preservation_gate["decision"] == "REFUSED":
        refused = True
        reasons.append("semantic_preservation_refused")
    elif preservation_gate["decision"] == "UNRESOLVED":
        unresolved = True
        reasons.append("semantic_preservation_unresolved")

    if refused:
        return "REFUSED", reasons
    if unresolved:
        return "UNRESOLVED", reasons
    return "READY_FOR_AUTHORITY_REVIEW", ["identity_and_semantic_continuity_established_for_review"]


def transition_envelope_from_spec(
    source_state: dict,
    candidate_state: dict,
    binding: dict,
    identity_verification: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    preservation_verification: dict,
    preservation_gate: dict,
    spec: dict,
) -> dict:
    """Bind one proposed state transition to identity + preservation evidence.

    The result can be ready for an external authority review, but cannot admit
    the candidate.
    """
    validate_state(source_state)
    validate_state(candidate_state)
    if source_state["record_digest"] == candidate_state["record_digest"]:
        raise ValueError("Industrial transition candidate must differ from source state")
    binding = validate_binding(binding)
    identity_verification = validate_identity_verification(identity_verification, binding)
    preservation_contract = validate_contract(preservation_contract, registry, semantic)
    preservation_verification = validate_verification(
        preservation_verification, registry, semantic, preservation_contract
    )
    preservation_gate = validate_admission_gate(
        preservation_gate,
        registry,
        semantic,
        preservation_contract,
        preservation_verification,
    )
    if preservation_verification["source_state_ref"] != source_state["record_digest"]:
        raise ValueError("Preservation verification source does not match transition source state")
    if preservation_verification["candidate_state_ref"] != candidate_state["record_digest"]:
        raise ValueError("Preservation verification candidate does not match transition candidate state")
    keys(spec, {
        "transition_id", "proposer", "required_admission_authority", "notes",
    })
    proposer = _proposer(spec["proposer"])
    authority = _versioned(spec["required_admission_authority"], "required admission authority")
    readiness, reasons = _readiness(
        source_state, candidate_state, binding, identity_verification, preservation_gate
    )
    value = record(
        "industrial-transition-envelope",
        transition_id=_versioned(spec["transition_id"], "transition_id"),
        source_state_ref=source_state["record_digest"],
        candidate_state_ref=candidate_state["record_digest"],
        canonical_entity_id=binding["canonical_entity_id"],
        entity_binding_ref=binding["record_digest"],
        identity_verification_ref=identity_verification["record_digest"],
        preservation_contract_ref=preservation_contract["record_digest"],
        preservation_verification_ref=preservation_verification["record_digest"],
        preservation_gate_ref=preservation_gate["record_digest"],
        proposer=proposer,
        required_admission_authority=authority,
        readiness=readiness,
        reasons=reasons,
        notes=_notes(spec["notes"], "transition envelope notes"),
        claims={
            "proposal_not_canonical_state": True,
            "identity_continuity_checked": True,
            "semantic_continuity_checked": True,
            "authority_review_required": True,
            "state_admission_performed": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_transition_envelope(
        value,
        source_state,
        candidate_state,
        binding,
        identity_verification,
        registry,
        semantic,
        preservation_contract,
        preservation_verification,
        preservation_gate,
    )
    return value


def validate_transition_envelope(
    value: dict,
    source_state: dict,
    candidate_state: dict,
    binding: dict,
    identity_verification: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    preservation_verification: dict,
    preservation_gate: dict,
) -> dict:
    keys(value, {
        "schema", "record_digest", "transition_id", "source_state_ref",
        "candidate_state_ref", "canonical_entity_id", "entity_binding_ref",
        "identity_verification_ref", "preservation_contract_ref",
        "preservation_verification_ref", "preservation_gate_ref", "proposer",
        "required_admission_authority", "readiness", "reasons", "notes", "claims",
    })
    if value["schema"] != "ciw.industrial-transition-envelope.v1":
        raise ValueError("Wrong industrial transition envelope schema")
    check_seal(value)
    _versioned(value["transition_id"], "transition_id")
    validate_state(source_state)
    validate_state(candidate_state)
    binding = validate_binding(binding)
    identity_verification = validate_identity_verification(identity_verification, binding)
    preservation_contract = validate_contract(preservation_contract, registry, semantic)
    preservation_verification = validate_verification(
        preservation_verification, registry, semantic, preservation_contract
    )
    preservation_gate = validate_admission_gate(
        preservation_gate,
        registry,
        semantic,
        preservation_contract,
        preservation_verification,
    )

    exact_refs = {
        "source_state_ref": source_state["record_digest"],
        "candidate_state_ref": candidate_state["record_digest"],
        "entity_binding_ref": binding["record_digest"],
        "identity_verification_ref": identity_verification["record_digest"],
        "preservation_contract_ref": preservation_contract["record_digest"],
        "preservation_verification_ref": preservation_verification["record_digest"],
        "preservation_gate_ref": preservation_gate["record_digest"],
    }
    for field, expected in exact_refs.items():
        content_ref(value[field])
        if value[field] != expected:
            raise ValueError(f"Transition envelope {field} identity mismatch")

    if value["canonical_entity_id"] != binding["canonical_entity_id"]:
        raise ValueError("Transition envelope canonical entity differs from identity binding")
    text(value["canonical_entity_id"])
    _proposer(value["proposer"])
    _versioned(value["required_admission_authority"], "required admission authority")
    if value["readiness"] not in READINESS:
        raise ValueError("Unknown industrial transition readiness")
    if type(value["reasons"]) is not list or not value["reasons"]:
        raise ValueError("Transition envelope requires at least one readiness reason")
    [text(reason) for reason in value["reasons"]]
    _notes(value["notes"], "transition envelope notes")

    if preservation_verification["source_state_ref"] != source_state["record_digest"]:
        raise ValueError("Transition preservation source differs from supplied source state")
    if preservation_verification["candidate_state_ref"] != candidate_state["record_digest"]:
        raise ValueError("Transition preservation candidate differs from supplied candidate state")

    expected_readiness, expected_reasons = _readiness(
        source_state, candidate_state, binding, identity_verification, preservation_gate
    )
    if value["readiness"] != expected_readiness or value["reasons"] != expected_reasons:
        raise ValueError("Transition readiness differs from recomputed identity/semantic gates")

    if value["claims"] != {
        "proposal_not_canonical_state": True,
        "identity_continuity_checked": True,
        "semantic_continuity_checked": True,
        "authority_review_required": True,
        "state_admission_performed": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Industrial transition claims exceed review-envelope authority")
    return detached(value)
