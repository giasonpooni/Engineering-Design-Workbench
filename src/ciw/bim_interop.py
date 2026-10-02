"""Runtime bridge from qualified external ingress to the existing BIM/CSE workload.

This is the first concrete executable-interoperability adapter. It does not
invent another IFC parser or estimator. It binds an already QUALIFIED ingress
occurrence to the exact IFC bytes embedded in an existing ciw.bim-quantity
source, executes the existing pinned CSE workflow, and emits a mapping witness.

Important boundaries:
- ingress qualification does not execute the mapping;
- this bridge executes the existing BIM/CSE mapping;
- CSE's retained invariant/ledger checks remain authoritative for that workload;
- the bridge does not create a canonical entity or admit canonical state;
- a successful runtime witness is evidence for later typed preservation
  verification, not that verification itself.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .bim_quantity import workflow as bim_workflow
from .control_contracts import content_ref, detached, keys, record, text
from .interop_ingress import validate_qualification
from .operations.runner import check_seal
from .preservation_contracts import validate_contract
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry
from .telemetry import byte_digest, canonical

ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
OUTCOMES = {"MAPPED", "HELD", "REFUSED"}


def _versioned(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None or len(value) > 180:
        raise ValueError(f"{label} must be a bounded versioned hierarchical ID")
    return value


def _notes(value: Any, label: str, maximum: int = 8192) -> str:
    if type(value) is not str or len(value) > maximum:
        raise ValueError(f"{label} must be bounded text")
    return value


def _result_data(bundle: dict) -> dict:
    if type(bundle) is not dict or bundle.get("schema") != bim_workflow.schema:
        raise ValueError("Runtime bridge requires an existing BIM quantity session")
    if type(bundle.get("steps")) is not list or len(bundle["steps"]) != 1:
        raise ValueError("BIM runtime bridge requires exactly one retained workload step")
    step = bundle["steps"][0]
    if step.get("operation_id") != bim_workflow.operation:
        raise ValueError("BIM runtime bridge received a different operation")
    result = step.get("result")
    if type(result) is not dict or type(result.get("data")) is not dict:
        raise ValueError("BIM runtime bridge requires retained native result data")
    return result["data"]


def _source_from_bundle(bundle: dict) -> dict:
    if type(bundle) is not dict or type(bundle.get("source")) is not dict:
        raise ValueError("BIM session does not retain its source")
    evidence = bundle["source"].get("evidence")
    if type(evidence) is not list or len(evidence) != 1:
        raise ValueError("BIM session requires one retained source artifact")
    import base64
    raw = base64.b64decode(evidence[0]["bytes_b64"], validate=True)
    return bim_workflow._source(raw)


def _outcome(data: dict) -> str:
    status = data["status"]
    if status == "accepted":
        return "MAPPED"
    if status == "held":
        return "HELD"
    if status == "refused":
        return "REFUSED"
    raise ValueError("Unknown native BIM mapping outcome")


def execute_bim_mapping_bundle(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    ingress_verification: dict,
    qualification: dict,
    bim_source: dict,
    repositories: dict,
    spec: dict,
) -> tuple[dict, dict]:
    """Execute the existing CSE mapping and return witness plus retained native bundle."""
    qualification = validate_qualification(
        qualification,
        registry,
        semantic,
        preservation_contract,
        profile,
        ingress,
        ingress_verification,
    )
    if qualification["status"] != "QUALIFIED":
        raise ValueError("BIM mapping execution requires QUALIFIED external ingress")
    preservation_contract = validate_contract(
        preservation_contract, registry, semantic
    )
    if qualification["preservation_contract_ref"] != preservation_contract["record_digest"]:
        raise ValueError("BIM mapping qualification uses another preservation contract")

    keys(spec, {"execution_id", "notes"})
    execution_id = _versioned(spec["execution_id"], "execution_id")

    source = bim_workflow._source(canonical(bim_source))
    if source["schema"] != "ciw.bim-quantity-source.v1":
        raise ValueError("BIM mapping bridge requires the existing BIM quantity source")
    if qualification["source_identity"]["object_kind"] not in {"CAD_OBJECT", "BIM_OBJECT"}:
        raise ValueError("BIM mapping bridge requires a CAD/BIM external identity")

    ifc_bytes = source["ifc_bytes_b64"]
    # Reuse the workload's own canonical evidence decoder indirectly through the
    # already validated source and compare its exact declared byte commitment.
    import base64
    raw_ifc = base64.b64decode(ifc_bytes, validate=True)
    exact_ifc_ref = byte_digest(raw_ifc)
    if ingress["payload_ref"] != exact_ifc_ref:
        raise ValueError("Qualified ingress payload is not the exact IFC bytes executed by CSE")

    bundle = bim_workflow.create_session(canonical(source), repositories)
    data = _result_data(bundle)
    outcome = _outcome(data)

    if data["ifc_sha256"] != exact_ifc_ref:
        raise ValueError("Native CSE result does not retain the qualified IFC byte identity")
    if data["target"] != source["target"]:
        raise ValueError("Native CSE result target differs from declared BIM source")

    value = record(
        "interop-mapping-witness",
        execution_id=execution_id,
        qualification_ref=qualification["record_digest"],
        ingress_ref=ingress["record_digest"],
        payload_ref=exact_ifc_ref,
        source_system_id=qualification["source_system_id"],
        source_identity=deepcopy(qualification["source_identity"]),
        source_representation_id=qualification["source_representation_id"],
        target_representation_id=qualification["target_representation_id"],
        morphism_ref=qualification["morphism_ref"],
        preservation_contract_ref=preservation_contract["record_digest"],
        workload_schema=bundle["schema"],
        workload_ref=bundle["bundle_digest"],
        operation_id=bim_workflow.operation,
        native_result_ref=bundle["steps"][0]["result_id"],
        native_execution_ref=bundle["steps"][0]["execution_id"],
        mapping_outcome=outcome,
        native_status=data["status"],
        native_reason=data["reason"],
        target=deepcopy(data["target"]),
        prior_world_digest=None if data["prior"] is None else data["prior"]["world_digest"],
        posterior_world_digest=None if data["posterior"] is None else data["posterior"]["world_digest"],
        invariant_report=deepcopy(data["invariants"]),
        ledger_replay=deepcopy(data["ledger_replay"]),
        notes=_notes(spec["notes"], "BIM interoperability mapping notes"),
        claims={
            "qualified_external_payload_executed": True,
            "existing_bim_cse_runtime_reused": True,
            "mapping_executed": True,
            "mapping_accepted": outcome == "MAPPED",
            "preservation_verification_performed": False,
            "physical_validity_established": False,
            "canonical_entity_created": False,
            "state_admission_performed": False,
            "canonical_state_mutated": False,
        },
    )
    validate_bim_mapping_witness(
        value,
        registry,
        semantic,
        preservation_contract,
        profile,
        ingress,
        ingress_verification,
        qualification,
        bundle,
    )
    return value, bundle



def execute_bim_mapping(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    ingress_verification: dict,
    qualification: dict,
    bim_source: dict,
    repositories: dict,
    spec: dict,
) -> dict:
    """Compatibility wrapper returning only the mapping witness."""
    witness, _ = execute_bim_mapping_bundle(
        registry,
        semantic,
        preservation_contract,
        profile,
        ingress,
        ingress_verification,
        qualification,
        bim_source,
        repositories,
        spec,
    )
    return witness

def validate_bim_mapping_witness(
    value: dict,
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    ingress_verification: dict,
    qualification: dict,
    bundle: dict,
) -> dict:
    keys(value, {
        "schema", "record_digest", "execution_id", "qualification_ref",
        "ingress_ref", "payload_ref", "source_system_id", "source_identity",
        "source_representation_id", "target_representation_id", "morphism_ref",
        "preservation_contract_ref", "workload_schema", "workload_ref",
        "operation_id", "native_result_ref", "native_execution_ref",
        "mapping_outcome", "native_status", "native_reason", "target",
        "prior_world_digest", "posterior_world_digest", "invariant_report",
        "ledger_replay", "notes", "claims",
    })
    if value["schema"] != "ciw.interop-mapping-witness.v1":
        raise ValueError("Wrong interoperability mapping witness schema")
    check_seal(value)
    _versioned(value["execution_id"], "execution_id")
    qualification = validate_qualification(
        qualification,
        registry,
        semantic,
        preservation_contract,
        profile,
        ingress,
        ingress_verification,
    )
    if qualification["status"] != "QUALIFIED":
        raise ValueError("BIM mapping witness requires qualified ingress")
    preservation_contract = validate_contract(
        preservation_contract, registry, semantic
    )
    data = _result_data(bundle)
    source = _source_from_bundle(bundle)
    import base64
    exact_ifc_ref = byte_digest(
        base64.b64decode(source["ifc_bytes_b64"], validate=True)
    )
    expected = {
        "qualification_ref": qualification["record_digest"],
        "ingress_ref": ingress["record_digest"],
        "payload_ref": exact_ifc_ref,
        "source_system_id": qualification["source_system_id"],
        "source_identity": qualification["source_identity"],
        "source_representation_id": qualification["source_representation_id"],
        "target_representation_id": qualification["target_representation_id"],
        "morphism_ref": qualification["morphism_ref"],
        "preservation_contract_ref": preservation_contract["record_digest"],
        "workload_schema": bundle["schema"],
        "workload_ref": bundle["bundle_digest"],
        "operation_id": bim_workflow.operation,
        "native_result_ref": bundle["steps"][0]["result_id"],
        "native_execution_ref": bundle["steps"][0]["execution_id"],
        "mapping_outcome": _outcome(data),
        "native_status": data["status"],
        "native_reason": data["reason"],
        "target": data["target"],
        "prior_world_digest": None if data["prior"] is None else data["prior"]["world_digest"],
        "posterior_world_digest": None if data["posterior"] is None else data["posterior"]["world_digest"],
        "invariant_report": data["invariants"],
        "ledger_replay": data["ledger_replay"],
    }
    for field, expected_value in expected.items():
        if value[field] != expected_value:
            raise ValueError(f"BIM interoperability mapping witness {field} mismatch")
    for field in (
        "qualification_ref", "ingress_ref", "payload_ref", "morphism_ref",
        "preservation_contract_ref",
    ):
        content_ref(value[field])
    if ingress["payload_ref"] != exact_ifc_ref or data["ifc_sha256"] != exact_ifc_ref:
        raise ValueError("BIM mapping witness payload identity differs across ingress/source/runtime")
    if value["mapping_outcome"] not in OUTCOMES:
        raise ValueError("Unknown BIM interoperability mapping outcome")
    text(value["workload_schema"])
    text(value["operation_id"])
    text(value["native_result_ref"])
    text(value["native_execution_ref"])
    text(value["native_status"])
    text(value["native_reason"])
    _notes(value["notes"], "BIM interoperability mapping notes")
    if value["claims"] != {
        "qualified_external_payload_executed": True,
        "existing_bim_cse_runtime_reused": True,
        "mapping_executed": True,
        "mapping_accepted": value["mapping_outcome"] == "MAPPED",
        "preservation_verification_performed": False,
        "physical_validity_established": False,
        "canonical_entity_created": False,
        "state_admission_performed": False,
        "canonical_state_mutated": False,
    }:
        raise ValueError("BIM interoperability mapping witness claims exceed runtime scope")
    return detached(value)
