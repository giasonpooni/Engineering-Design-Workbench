"""Executable interoperability ingress V1.

Existing industrial standards and proprietary representations are treated as
declared external inputs to the same NET identity/preservation discipline.

This module does not parse or certify STEP, OPC UA, MTConnect or any proprietary
format. It binds an operator-declared external profile to an existing scientific
morphism + preservation contract, retains one concrete payload occurrence, and
requires an explicit verification receipt before that occurrence can be used as
a qualified identity/representation reference.

The distinction is deliberate:

external transport/schema conformance != semantic preservation != physical truth.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .control_contracts import content_ref, detached, json_tree, keys, record, text
from .industrial_transition import OBJECT_KINDS
from .operations.runner import check_seal
from .preservation_contracts import validate_contract
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry

ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
SOURCE_FAMILIES = {"STANDARD", "PROPRIETARY"}
CHECK_KINDS = {
    "PROFILE_CONFORMANCE",
    "SOURCE_IDENTITY",
    "REPRESENTATION_MAPPING",
    "MAPPING_ASSUMPTIONS",
    "UNCERTAINTY_HANDLING",
    "PRESERVATION_PRECONDITIONS",
}
CHECK_STATUS = {"VERIFIED", "REFUTED", "UNRESOLVED"}
CHECK_METHODS = {
    "CONFORMANCE_TOOL",
    "DECLARED_PROFILE",
    "MAPPING_TEST",
    "EVIDENCE_CROSSCHECK",
    "HUMAN_ATTESTATION",
    "NOT_PERFORMED",
}
QUALIFICATION = {"QUALIFIED", "REFUSED", "UNRESOLVED"}
MAX_ITEMS = 128


def _versioned(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None or len(value) > 180:
        raise ValueError(f"{label} must be a bounded versioned hierarchical ID")
    return value


def _notes(value: Any, label: str, maximum: int = 8192) -> str:
    if type(value) is not str or len(value) > maximum:
        raise ValueError(f"{label} must be bounded text")
    return value


def _unique_text(values: Any, label: str) -> list[str]:
    if type(values) is not list or len(values) > MAX_ITEMS:
        raise ValueError(f"{label} must be a bounded list")
    result = [text(value) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _unique_properties(values: Any, label: str) -> list[str]:
    if type(values) is not list or len(values) > MAX_ITEMS:
        raise ValueError(f"{label} must be a bounded list")
    result = [_versioned(value, label) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def profile_from_spec(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    spec: dict,
) -> dict:
    """Bind an external schema/profile to an existing morphism and contract."""
    registry = validate_registry(registry, semantic)
    preservation_contract = validate_contract(preservation_contract, registry, semantic)
    keys(spec, {
        "profile_id", "source_family", "standard_id", "source_profile_id",
        "source_system_id", "source_schema_id", "morphism_id", "mapping_id",
        "mapping_assumptions", "uncertainty_semantics", "declared_loss_properties",
        "verification_requirements", "notes",
    })
    family = spec["source_family"]
    if family not in SOURCE_FAMILIES:
        raise ValueError("Unknown interoperability source family")
    standard_id = spec["standard_id"]
    if family == "STANDARD":
        standard_id = _versioned(standard_id, "standard_id")
    elif standard_id is not None:
        raise ValueError("PROPRIETARY source profile must use standard_id=null")

    morphism_id = _versioned(spec["morphism_id"], "morphism_id")
    if morphism_id not in registry["morphisms"]:
        raise ValueError("Interoperability profile references unknown scientific morphism")
    morphism = registry["morphisms"][morphism_id]
    if preservation_contract["morphism_ref"] != morphism["record_digest"]:
        raise ValueError("Interoperability profile preservation contract targets another morphism")

    declared_loss = _unique_properties(
        spec["declared_loss_properties"], "declared loss property"
    )
    contract_loss = sorted(
        effect["property_id"]
        for effect in preservation_contract["effects"]
        if effect["effect"] == "FORGET"
    )
    if sorted(declared_loss) != contract_loss:
        raise ValueError(
            "Interoperability declared loss must exactly match preservation-contract FORGET effects"
        )

    value = record(
        "interoperability-profile",
        profile_id=_versioned(spec["profile_id"], "profile_id"),
        source_family=family,
        standard_id=standard_id,
        source_profile_id=_versioned(spec["source_profile_id"], "source_profile_id"),
        source_system_id=_versioned(spec["source_system_id"], "source_system_id"),
        source_schema_id=text(spec["source_schema_id"]),
        registry_ref=registry["record_digest"],
        morphism_id=morphism_id,
        morphism_ref=morphism["record_digest"],
        source_representation_id=morphism["domain_representation_id"],
        source_representation_ref=registry["representations"][
            morphism["domain_representation_id"]
        ]["record_digest"],
        target_representation_id=morphism["codomain_representation_id"],
        target_representation_ref=registry["representations"][
            morphism["codomain_representation_id"]
        ]["record_digest"],
        preservation_contract_ref=preservation_contract["record_digest"],
        mapping_id=_versioned(spec["mapping_id"], "mapping_id"),
        mapping_assumptions=_unique_text(
            spec["mapping_assumptions"], "mapping assumption"
        ),
        uncertainty_semantics=text(spec["uncertainty_semantics"]),
        declared_loss_properties=declared_loss,
        verification_requirements=_unique_text(
            spec["verification_requirements"], "verification requirement"
        ),
        notes=_notes(spec["notes"], "interoperability profile notes"),
        claims={
            "external_representation_profile": True,
            "standard_or_schema_conformance_established": False,
            "semantic_preservation_established": False,
            "physical_validity_established": False,
            "provider_execution": False,
            "canonical_state_mutated": False,
            "state_admission_authority": False,
        },
    )
    validate_profile(value, registry, semantic, preservation_contract)
    return value


def validate_profile(
    value: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
) -> dict:
    registry = validate_registry(registry, semantic)
    preservation_contract = validate_contract(preservation_contract, registry, semantic)
    keys(value, {
        "schema", "record_digest", "profile_id", "source_family", "standard_id",
        "source_profile_id", "source_system_id", "source_schema_id", "registry_ref",
        "morphism_id", "morphism_ref", "source_representation_id",
        "source_representation_ref", "target_representation_id",
        "target_representation_ref", "preservation_contract_ref", "mapping_id",
        "mapping_assumptions", "uncertainty_semantics", "declared_loss_properties",
        "verification_requirements", "notes", "claims",
    })
    if value["schema"] != "ciw.interoperability-profile.v1":
        raise ValueError("Wrong interoperability profile schema")
    check_seal(value)
    _versioned(value["profile_id"], "profile_id")
    if value["source_family"] not in SOURCE_FAMILIES:
        raise ValueError("Unknown interoperability source family")
    if value["source_family"] == "STANDARD":
        _versioned(value["standard_id"], "standard_id")
    elif value["standard_id"] is not None:
        raise ValueError("PROPRIETARY source profile must use standard_id=null")
    for field in ("source_profile_id", "source_system_id", "mapping_id"):
        _versioned(value[field], field)
    text(value["source_schema_id"])
    if value["registry_ref"] != registry["record_digest"]:
        raise ValueError("Interoperability profile is bound to a different morphism registry")
    content_ref(value["registry_ref"])
    morphism_id = _versioned(value["morphism_id"], "morphism_id")
    if morphism_id not in registry["morphisms"]:
        raise ValueError("Interoperability profile morphism is absent from registry")
    morphism = registry["morphisms"][morphism_id]
    if value["morphism_ref"] != morphism["record_digest"]:
        raise ValueError("Interoperability profile morphism identity differs from registry")
    content_ref(value["morphism_ref"])
    expected = {
        "source_representation_id": morphism["domain_representation_id"],
        "source_representation_ref": registry["representations"][
            morphism["domain_representation_id"]
        ]["record_digest"],
        "target_representation_id": morphism["codomain_representation_id"],
        "target_representation_ref": registry["representations"][
            morphism["codomain_representation_id"]
        ]["record_digest"],
        "preservation_contract_ref": preservation_contract["record_digest"],
    }
    for field, expected_value in expected.items():
        if value[field] != expected_value:
            raise ValueError(f"Interoperability profile {field} differs from bound semantics")
    for field in (
        "source_representation_ref", "target_representation_ref",
        "preservation_contract_ref",
    ):
        content_ref(value[field])
    if preservation_contract["morphism_ref"] != morphism["record_digest"]:
        raise ValueError("Interoperability profile contract/morphism binding mismatch")
    _unique_text(value["mapping_assumptions"], "mapping assumption")
    text(value["uncertainty_semantics"])
    declared_loss = _unique_properties(
        value["declared_loss_properties"], "declared loss property"
    )
    contract_loss = sorted(
        effect["property_id"]
        for effect in preservation_contract["effects"]
        if effect["effect"] == "FORGET"
    )
    if sorted(declared_loss) != contract_loss:
        raise ValueError("Interoperability profile loss differs from preservation contract")
    _unique_text(value["verification_requirements"], "verification requirement")
    _notes(value["notes"], "interoperability profile notes")
    if value["claims"] != {
        "external_representation_profile": True,
        "standard_or_schema_conformance_established": False,
        "semantic_preservation_established": False,
        "physical_validity_established": False,
        "provider_execution": False,
        "canonical_state_mutated": False,
        "state_admission_authority": False,
    }:
        raise ValueError("Interoperability profile claims exceed declarative scope")
    return detached(value)


def _source_identity(value: Any) -> dict:
    keys(value, {"reference_id", "namespace", "external_id", "object_kind"})
    if value["object_kind"] not in OBJECT_KINDS:
        raise ValueError("Unknown interoperability source object kind")
    return {
        "reference_id": _versioned(value["reference_id"], "reference_id"),
        "namespace": text(value["namespace"]),
        "external_id": text(value["external_id"]),
        "object_kind": value["object_kind"],
    }


def ingress_from_spec(profile: dict, spec: dict) -> dict:
    """Retain one concrete external payload occurrence without translating it."""
    check_seal(profile)
    if profile.get("schema") != "ciw.interoperability-profile.v1":
        raise ValueError("Ingress requires an interoperability profile")
    keys(spec, {
        "ingress_id", "payload_ref", "payload_media_type", "source_identity",
        "mapping_parameters", "mapping_evidence_refs", "notes",
    })
    mapping_parameters = spec["mapping_parameters"]
    if type(mapping_parameters) is not dict or len(mapping_parameters) > 128:
        raise ValueError("Ingress mapping_parameters must be a bounded object")
    json_tree(mapping_parameters)
    evidence = spec["mapping_evidence_refs"]
    if type(evidence) is not list or len(evidence) > MAX_ITEMS:
        raise ValueError("Ingress mapping evidence must be a bounded list")
    evidence = [content_ref(item) for item in evidence]
    if len(evidence) != len(set(evidence)):
        raise ValueError("Ingress mapping evidence contains duplicates")
    value = record(
        "external-ingress",
        ingress_id=_versioned(spec["ingress_id"], "ingress_id"),
        profile_ref=profile["record_digest"],
        payload_ref=content_ref(spec["payload_ref"]),
        payload_media_type=text(spec["payload_media_type"]),
        source_identity=_source_identity(spec["source_identity"]),
        mapping_parameters=deepcopy(mapping_parameters),
        mapping_evidence_refs=evidence,
        notes=_notes(spec["notes"], "external ingress notes"),
        claims={
            "external_payload_retained": True,
            "mapping_executed": False,
            "profile_conformance_established": False,
            "semantic_preservation_established": False,
            "identity_admission_performed": False,
            "canonical_state_mutated": False,
        },
    )
    validate_ingress(value, profile)
    return value


def validate_ingress(value: dict, profile: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "ingress_id", "profile_ref", "payload_ref",
        "payload_media_type", "source_identity", "mapping_parameters",
        "mapping_evidence_refs", "notes", "claims",
    })
    if value["schema"] != "ciw.external-ingress.v1":
        raise ValueError("Wrong external ingress schema")
    check_seal(value)
    check_seal(profile)
    if profile.get("schema") != "ciw.interoperability-profile.v1":
        raise ValueError("Ingress requires an interoperability profile")
    _versioned(value["ingress_id"], "ingress_id")
    if value["profile_ref"] != profile["record_digest"]:
        raise ValueError("External ingress references a different interoperability profile")
    for field in ("profile_ref", "payload_ref"):
        content_ref(value[field])
    text(value["payload_media_type"])
    _source_identity(value["source_identity"])
    if type(value["mapping_parameters"]) is not dict or len(value["mapping_parameters"]) > 128:
        raise ValueError("Ingress mapping_parameters must be a bounded object")
    json_tree(value["mapping_parameters"])
    if type(value["mapping_evidence_refs"]) is not list or len(value["mapping_evidence_refs"]) > MAX_ITEMS:
        raise ValueError("Ingress mapping evidence must be a bounded list")
    refs = [content_ref(item) for item in value["mapping_evidence_refs"]]
    if len(refs) != len(set(refs)):
        raise ValueError("Ingress mapping evidence contains duplicates")
    _notes(value["notes"], "external ingress notes")
    if value["claims"] != {
        "external_payload_retained": True,
        "mapping_executed": False,
        "profile_conformance_established": False,
        "semantic_preservation_established": False,
        "identity_admission_performed": False,
        "canonical_state_mutated": False,
    }:
        raise ValueError("External ingress claims exceed retention scope")
    return detached(value)


def _check(value: Any) -> dict:
    keys(value, {"kind", "status", "method", "evidence_ref", "notes"})
    kind = value["kind"]
    if kind not in CHECK_KINDS:
        raise ValueError("Unknown interoperability verification check kind")
    status = value["status"]
    if status not in CHECK_STATUS:
        raise ValueError("Unknown interoperability verification status")
    method = value["method"]
    if method not in CHECK_METHODS:
        raise ValueError("Unknown interoperability verification method")
    evidence = value["evidence_ref"]
    if status in {"VERIFIED", "REFUTED"}:
        if method == "NOT_PERFORMED":
            raise ValueError("Resolved interoperability check cannot use NOT_PERFORMED")
        evidence = content_ref(evidence)
    elif evidence is not None:
        evidence = content_ref(evidence)
    return {
        "kind": kind,
        "status": status,
        "method": method,
        "evidence_ref": evidence,
        "notes": _notes(value["notes"], "interoperability verification notes", 2048),
    }


def verification_from_spec(profile: dict, ingress: dict, spec: dict) -> dict:
    profile = detached(profile)
    ingress = validate_ingress(ingress, profile)
    keys(spec, {"verification_id", "checks", "notes"})
    checks = spec["checks"]
    if type(checks) is not list or len(checks) != len(CHECK_KINDS):
        raise ValueError("Interoperability verification must cover all V1 check kinds")
    normalized = [_check(row) for row in checks]
    kinds = [row["kind"] for row in normalized]
    if len(kinds) != len(set(kinds)) or set(kinds) != CHECK_KINDS:
        raise ValueError("Interoperability verification check coverage is incomplete or duplicated")
    if any(row["status"] == "REFUTED" for row in normalized):
        status = "REFUTED"
    elif all(row["status"] == "VERIFIED" for row in normalized):
        status = "VERIFIED"
    else:
        status = "UNRESOLVED"
    value = record(
        "external-ingress-verification",
        verification_id=_versioned(spec["verification_id"], "verification_id"),
        profile_ref=profile["record_digest"],
        ingress_ref=ingress["record_digest"],
        payload_ref=ingress["payload_ref"],
        checks=normalized,
        status=status,
        notes=_notes(spec["notes"], "interoperability verification notes"),
        claims={
            "profile_and_mapping_checks_retained": True,
            "verification_is_not_physical_validation": True,
            "verification_is_not_identity_admission": True,
            "mapping_executed": False,
            "canonical_state_mutated": False,
        },
    )
    validate_verification(value, profile, ingress)
    return value


def validate_verification(value: dict, profile: dict, ingress: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "verification_id", "profile_ref", "ingress_ref",
        "payload_ref", "checks", "status", "notes", "claims",
    })
    if value["schema"] != "ciw.external-ingress-verification.v1":
        raise ValueError("Wrong external ingress verification schema")
    check_seal(value)
    ingress = validate_ingress(ingress, profile)
    _versioned(value["verification_id"], "verification_id")
    expected_refs = {
        "profile_ref": profile["record_digest"],
        "ingress_ref": ingress["record_digest"],
        "payload_ref": ingress["payload_ref"],
    }
    for field, expected in expected_refs.items():
        content_ref(value[field])
        if value[field] != expected:
            raise ValueError(f"External ingress verification {field} identity mismatch")
    if type(value["checks"]) is not list or len(value["checks"]) != len(CHECK_KINDS):
        raise ValueError("Interoperability verification must cover all V1 check kinds")
    normalized = [_check(row) for row in value["checks"]]
    kinds = [row["kind"] for row in normalized]
    if len(kinds) != len(set(kinds)) or set(kinds) != CHECK_KINDS:
        raise ValueError("Interoperability verification check coverage is incomplete or duplicated")
    expected_status = (
        "REFUTED" if any(row["status"] == "REFUTED" for row in normalized)
        else "VERIFIED" if all(row["status"] == "VERIFIED" for row in normalized)
        else "UNRESOLVED"
    )
    if value["status"] != expected_status:
        raise ValueError("External ingress aggregate verification status contradicts checks")
    _notes(value["notes"], "interoperability verification notes")
    if value["claims"] != {
        "profile_and_mapping_checks_retained": True,
        "verification_is_not_physical_validation": True,
        "verification_is_not_identity_admission": True,
        "mapping_executed": False,
        "canonical_state_mutated": False,
    }:
        raise ValueError("External ingress verification claims exceed verification scope")
    return detached(value)


def qualify_ingress(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    verification: dict,
) -> dict:
    profile = validate_profile(profile, registry, semantic, preservation_contract)
    ingress = validate_ingress(ingress, profile)
    verification = validate_verification(verification, profile, ingress)
    if verification["status"] == "VERIFIED":
        status = "QUALIFIED"
        reasons = ["profile_mapping_and_preconditions_verified"]
    elif verification["status"] == "REFUTED":
        status = "REFUSED"
        reasons = ["external_profile_or_mapping_refuted"]
    else:
        status = "UNRESOLVED"
        reasons = ["external_profile_or_mapping_unresolved"]
    value = record(
        "external-ingress-qualification",
        profile_ref=profile["record_digest"],
        ingress_ref=ingress["record_digest"],
        verification_ref=verification["record_digest"],
        payload_ref=ingress["payload_ref"],
        source_system_id=profile["source_system_id"],
        source_identity=deepcopy(ingress["source_identity"]),
        source_representation_id=profile["source_representation_id"],
        source_representation_ref=profile["source_representation_ref"],
        target_representation_id=profile["target_representation_id"],
        target_representation_ref=profile["target_representation_ref"],
        morphism_ref=profile["morphism_ref"],
        preservation_contract_ref=profile["preservation_contract_ref"],
        status=status,
        reasons=reasons,
        claims={
            "qualified_for_net_identity_and_semantic_workflow": status == "QUALIFIED",
            "mapping_executed": False,
            "canonical_entity_created": False,
            "state_admission_performed": False,
            "physical_validity_established": False,
            "canonical_state_mutated": False,
        },
    )
    validate_qualification(
        value, registry, semantic, preservation_contract, profile, ingress, verification
    )
    return value


def validate_qualification(
    value: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    verification: dict,
) -> dict:
    keys(value, {
        "schema", "record_digest", "profile_ref", "ingress_ref", "verification_ref",
        "payload_ref", "source_system_id", "source_identity",
        "source_representation_id", "source_representation_ref",
        "target_representation_id", "target_representation_ref", "morphism_ref",
        "preservation_contract_ref", "status", "reasons", "claims",
    })
    if value["schema"] != "ciw.external-ingress-qualification.v1":
        raise ValueError("Wrong external ingress qualification schema")
    check_seal(value)
    profile = validate_profile(profile, registry, semantic, preservation_contract)
    ingress = validate_ingress(ingress, profile)
    verification = validate_verification(verification, profile, ingress)
    expected_refs = {
        "profile_ref": profile["record_digest"],
        "ingress_ref": ingress["record_digest"],
        "verification_ref": verification["record_digest"],
        "payload_ref": ingress["payload_ref"],
        "source_system_id": profile["source_system_id"],
        "source_representation_id": profile["source_representation_id"],
        "source_representation_ref": profile["source_representation_ref"],
        "target_representation_id": profile["target_representation_id"],
        "target_representation_ref": profile["target_representation_ref"],
        "morphism_ref": profile["morphism_ref"],
        "preservation_contract_ref": profile["preservation_contract_ref"],
    }
    for field, expected in expected_refs.items():
        if value[field] != expected:
            raise ValueError(f"External ingress qualification {field} mismatch")
        if field.endswith("_ref") or field == "payload_ref":
            content_ref(value[field])
    if value["source_identity"] != ingress["source_identity"]:
        raise ValueError("External ingress qualification source identity differs from ingress")
    _source_identity(value["source_identity"])
    if verification["status"] == "VERIFIED":
        expected_status = "QUALIFIED"
        expected_reasons = ["profile_mapping_and_preconditions_verified"]
    elif verification["status"] == "REFUTED":
        expected_status = "REFUSED"
        expected_reasons = ["external_profile_or_mapping_refuted"]
    else:
        expected_status = "UNRESOLVED"
        expected_reasons = ["external_profile_or_mapping_unresolved"]
    if value["status"] != expected_status or value["reasons"] != expected_reasons:
        raise ValueError("External ingress qualification differs from recomputed verification")
    if value["status"] not in QUALIFICATION:
        raise ValueError("Unknown external ingress qualification status")
    if value["claims"] != {
        "qualified_for_net_identity_and_semantic_workflow": expected_status == "QUALIFIED",
        "mapping_executed": False,
        "canonical_entity_created": False,
        "state_admission_performed": False,
        "physical_validity_established": False,
        "canonical_state_mutated": False,
    }:
        raise ValueError("External ingress qualification claims exceed ingress authority")
    return detached(value)


def identity_reference_from_qualification(
    qualification: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    verification: dict,
) -> dict:
    """Project a recomputed QUALIFIED ingress into entity-binding reference shape."""
    qualification = validate_qualification(
        qualification,
        registry,
        semantic,
        preservation_contract,
        profile,
        ingress,
        verification,
    )
    if qualification["status"] != "QUALIFIED":
        raise ValueError("Only QUALIFIED ingress may become an entity-binding reference")
    source = _source_identity(qualification["source_identity"])
    return {
        "reference_id": source["reference_id"],
        "system_id": _versioned(qualification["source_system_id"], "source_system_id"),
        "namespace": source["namespace"],
        "external_id": source["external_id"],
        "object_kind": source["object_kind"],
        "evidence_ref": qualification["record_digest"],
    }
