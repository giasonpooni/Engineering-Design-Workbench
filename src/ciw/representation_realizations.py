"""Typed validators connecting retained artifacts to representation contracts.

A representation declaration is not proof that a particular retained artifact
realizes it.  This layer registers trusted, family-specific realization
validators and retains their exact binding.  It performs no provider execution,
state admission, inverse reconstruction or physical authentication.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from .control_contracts import (
    content_ref, detached, keys, record, text, validate_state,
)
from .core.covariance import validate_covariance_artifact
from .core.identities import content_identity, validate_evidence_identity
from .instruments import validate_run
from .operations.runner import check_seal
from .representation_interventions import validate_gate
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry

ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
VALIDATORS = {
    "run-channel.v1": "ciw.run-channel.v1",
    "state-record.v1": "ciw.state.v1",
    "covariance-artifact.v1": "covariance-artifact.v1",
}
MAX_ADAPTERS = 128
MAX_QUANTITIES = 64


def _versioned(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None or len(value) > 180:
        raise ValueError(f"{label} must be a bounded versioned hierarchical ID")
    return value


def _binding(value: Any) -> dict:
    keys(value, {"quantity_ids", "units", "frame", "uncertainty_required"})
    quantities = value["quantity_ids"]
    units = value["units"]
    if (type(quantities) is not list or not 1 <= len(quantities) <= MAX_QUANTITIES
            or type(units) is not list or len(units) != len(quantities)):
        raise ValueError("Realization binding requires aligned bounded quantity/unit lists")
    quantities = [text(item) for item in quantities]
    units = [text(item) for item in units]
    if len(set(quantities)) != len(quantities):
        raise ValueError("Realization binding quantity IDs must be unique")
    if type(value["uncertainty_required"]) is not bool:
        raise ValueError("uncertainty_required must be boolean")
    return {
        "quantity_ids": quantities,
        "units": units,
        "frame": text(value["frame"]),
        "uncertainty_required": value["uncertainty_required"],
    }


def adapter_from_spec(spec: dict, representations: dict[str, dict]) -> dict:
    keys(spec, {"adapter_id", "representation_id", "validator_id", "binding", "notes"})
    adapter_id = _versioned(spec["adapter_id"], "adapter_id")
    representation_id = _versioned(spec["representation_id"], "representation_id")
    if representation_id not in representations:
        raise ValueError("Realization adapter references an unknown representation")
    validator_id = spec["validator_id"]
    if validator_id not in VALIDATORS:
        raise ValueError("Unknown trusted realization validator")
    representation = representations[representation_id]
    if representation["schema_id"] != VALIDATORS[validator_id]:
        raise ValueError("Representation schema is incompatible with the selected realization validator")
    binding = _binding(spec["binding"])
    if validator_id == "run-channel.v1" and binding["uncertainty_required"]:
        raise ValueError("Run-channel V1 does not invent channel uncertainty")
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Realization adapter notes must be bounded text")
    value = record(
        "realization-adapter",
        adapter_id=adapter_id,
        representation_id=representation_id,
        representation_ref=representation["record_digest"],
        validator_id=validator_id,
        source_schema=VALIDATORS[validator_id],
        binding=binding,
        notes=notes,
        claims={
            "trusted_family_validator_required": True,
            "semantic_strings_not_parsed_as_proof": True,
            "provider_execution": False,
            "state_admission": False,
            "execution_authority": False,
        },
    )
    validate_adapter(value, representations)
    return value


def validate_adapter(value: dict, representations: dict[str, dict]) -> dict:
    keys(value, {
        "schema", "record_digest", "adapter_id", "representation_id",
        "representation_ref", "validator_id", "source_schema", "binding",
        "notes", "claims",
    })
    if value["schema"] != "ciw.realization-adapter.v1":
        raise ValueError("Wrong realization adapter schema")
    check_seal(value)
    _versioned(value["adapter_id"], "adapter_id")
    representation_id = _versioned(value["representation_id"], "representation_id")
    if representation_id not in representations:
        raise ValueError("Realization adapter references an unknown representation")
    representation = representations[representation_id]
    if value["representation_ref"] != representation["record_digest"]:
        raise ValueError("Realization adapter is bound to a different representation")
    if value["validator_id"] not in VALIDATORS:
        raise ValueError("Unknown trusted realization validator")
    if value["source_schema"] != VALIDATORS[value["validator_id"]]:
        raise ValueError("Realization adapter source schema differs from validator contract")
    if representation["schema_id"] != value["source_schema"]:
        raise ValueError("Representation schema differs from realization adapter")
    binding = _binding(value["binding"])
    if value["validator_id"] == "run-channel.v1" and binding["uncertainty_required"]:
        raise ValueError("Run-channel V1 does not invent channel uncertainty")
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("Realization adapter notes must be bounded text")
    if value["claims"] != {
        "trusted_family_validator_required": True,
        "semantic_strings_not_parsed_as_proof": True,
        "provider_execution": False,
        "state_admission": False,
        "execution_authority": False,
    }:
        raise ValueError("Realization adapter claims exceed registry authority")
    return detached(value)


def adapter_registry_from_specs(morphism_registry: dict, semantic: SemanticRegistry,
                                specs: list[dict]) -> dict:
    morphism_registry = validate_registry(morphism_registry, semantic)
    if type(specs) is not list or not 1 <= len(specs) <= MAX_ADAPTERS:
        raise ValueError("Realization adapter registry requires 1..128 adapter specs")
    adapters = [adapter_from_spec(spec, morphism_registry["representations"]) for spec in specs]
    mapping = {item["adapter_id"]: item for item in adapters}
    if len(mapping) != len(adapters):
        raise ValueError("Duplicate realization adapter identity")
    value = record(
        "realization-adapter-registry",
        morphism_registry_ref=morphism_registry["record_digest"],
        adapters=mapping,
        claims={
            "binds_artifact_validators_to_representations": True,
            "selects_provider": False,
            "provider_execution": False,
            "canonical_state_authority": False,
            "execution_authority": False,
        },
    )
    validate_adapter_registry(value, morphism_registry, semantic)
    return value


def validate_adapter_registry(value: dict, morphism_registry: dict,
                              semantic: SemanticRegistry) -> dict:
    morphism_registry = validate_registry(morphism_registry, semantic)
    keys(value, {"schema", "record_digest", "morphism_registry_ref", "adapters", "claims"})
    if value["schema"] != "ciw.realization-adapter-registry.v1":
        raise ValueError("Wrong realization adapter registry schema")
    check_seal(value)
    if value["morphism_registry_ref"] != morphism_registry["record_digest"]:
        raise ValueError("Realization adapter registry is bound to a different morphism registry")
    if type(value["adapters"]) is not dict or not 1 <= len(value["adapters"]) <= MAX_ADAPTERS:
        raise ValueError("Realization adapter registry requires 1..128 adapters")
    for adapter_id, adapter in value["adapters"].items():
        checked = validate_adapter(adapter, morphism_registry["representations"])
        if adapter_id != checked["adapter_id"]:
            raise ValueError("Realization adapter map identity mismatch")
    if value["claims"] != {
        "binds_artifact_validators_to_representations": True,
        "selects_provider": False,
        "provider_execution": False,
        "canonical_state_authority": False,
        "execution_authority": False,
    }:
        raise ValueError("Realization adapter registry claims exceed descriptive authority")
    return detached(value)


def _selector(value: Any, validator_id: str) -> dict:
    if validator_id != "run-channel.v1":
        if value != {}:
            raise ValueError("This realization family accepts no selector in V1")
        return {}
    keys(value, {"channel", "interval_s"})
    channel = text(value["channel"])
    interval = value["interval_s"]
    if (type(interval) is not list or len(interval) != 2
            or any(type(item) not in (int, float) or isinstance(item, bool)
                   or not math.isfinite(float(item)) for item in interval)):
        raise ValueError("Run-channel selector requires a finite [start,end] interval")
    start, end = map(float, interval)
    if start < 0 or start >= end:
        raise ValueError("Run-channel interval must satisfy 0 <= start < end")
    return {"channel": channel, "interval_s": [start, end]}


def _realize_run(artifact: dict, binding: dict, selector: dict) -> tuple[dict, list[str]]:
    validate_run(artifact)
    validate_evidence_identity(artifact)
    channel = selector["channel"]
    if channel not in artifact["channels"]:
        raise ValueError("Selected run channel is absent")
    if channel not in binding["quantity_ids"]:
        raise ValueError("Selected run channel is outside the realization binding")
    index = binding["quantity_ids"].index(channel)
    if artifact["channels"][channel]["unit"] != binding["units"][index]:
        raise ValueError("Selected run channel unit differs from realization binding")
    if artifact["metadata"]["coordinate_frame"] != binding["frame"]:
        raise ValueError("Run coordinate frame differs from realization binding")
    duration = float(artifact["metadata"]["duration_s"])
    start, end = selector["interval_s"]
    if end > duration:
        raise ValueError("Run-channel interval exceeds retained run duration")
    indices = [i for i, t in enumerate(artifact["time_s"]) if start <= t < end]
    if not indices:
        raise ValueError("Run-channel realization selects no retained samples")
    values = artifact["channels"][channel]["values"]
    if len(values) != len(artifact["time_s"]):
        raise ValueError("Run channel/time sample count mismatch")
    view = {
        "quantity_ids": [channel],
        "units": [artifact["channels"][channel]["unit"]],
        "frame": artifact["metadata"]["coordinate_frame"],
        "uncertainty_ref": None,
        "selector": selector,
        "run_id": artifact["run_id"],
        "instrument": artifact["instrument"],
        "sample_rate_hz": artifact["metadata"]["sample_rate_hz"],
        "selected_sample_count": len(indices),
        "first_selected_time_s": artifact["time_s"][indices[0]],
        "last_selected_time_s": artifact["time_s"][indices[-1]],
        "time_semantics": "retained uniform samples in half-open interval",
    }
    return view, [artifact["evidence_id"]]


def _realize_state(artifact: dict, binding: dict, selector: dict) -> tuple[dict, list[str]]:
    validate_state(artifact)
    quantities = list(artifact["variables"])
    units = [artifact["variables"][name]["unit"] for name in quantities]
    if quantities != binding["quantity_ids"] or units != binding["units"]:
        raise ValueError("State variable order/units differ from realization binding")
    if artifact["frame"] != binding["frame"]:
        raise ValueError("State frame differs from realization binding")
    uncertainty = artifact["uncertainty"]
    if binding["uncertainty_required"] and uncertainty is None:
        raise ValueError("State realization requires retained uncertainty")
    uncertainty_ref = None if uncertainty is None else uncertainty["covariance_id"]
    sources = [content_ref(ref) for ref in artifact["provenance"]["sources"]]
    view = {
        "quantity_ids": quantities,
        "units": units,
        "frame": artifact["frame"],
        "uncertainty_ref": uncertainty_ref,
        "selector": {},
        "state_identity": deepcopy(artifact["identity"]),
        "clock": deepcopy(artifact["clock"]),
        "provenance_semantics": artifact["provenance"]["semantics"],
    }
    return view, sources


def _realize_covariance(artifact: dict, binding: dict, selector: dict) -> tuple[dict, list[str]]:
    validate_covariance_artifact(
        artifact,
        expected_quantity_ids=binding["quantity_ids"],
        expected_units=binding["units"],
        expected_frame=binding["frame"],
    )
    sources = list(artifact["provenance"]["source_evidence_ids"])
    sources += list(artifact["provenance"]["source_covariance_ids"])
    sources = [content_ref(ref) for ref in sources]
    view = {
        "quantity_ids": deepcopy(artifact["quantity_ids"]),
        "units": deepcopy(artifact["units"]),
        "frame": artifact["frame"],
        "uncertainty_ref": artifact["covariance_id"],
        "selector": {},
        "basis": deepcopy(artifact["basis"]),
        "method": artifact["method"],
        "matrix_shape": [len(artifact["matrix"]), len(artifact["matrix"])],
    }
    return view, sources


def realize(adapter_registry: dict, morphism_registry: dict, semantic: SemanticRegistry,
            artifact: dict, spec: dict) -> dict:
    adapter_registry = validate_adapter_registry(adapter_registry, morphism_registry, semantic)
    keys(spec, {"realization_id", "adapter_id", "selector", "notes"})
    realization_id = text(spec["realization_id"])
    adapter_id = _versioned(spec["adapter_id"], "adapter_id")
    if adapter_id not in adapter_registry["adapters"]:
        raise ValueError("Realization references an unknown adapter")
    adapter = adapter_registry["adapters"][adapter_id]
    selector = _selector(spec["selector"], adapter["validator_id"])
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Representation realization notes must be bounded text")
    if adapter["validator_id"] == "run-channel.v1":
        view, evidence_refs = _realize_run(artifact, adapter["binding"], selector)
    elif adapter["validator_id"] == "state-record.v1":
        view, evidence_refs = _realize_state(artifact, adapter["binding"], selector)
    elif adapter["validator_id"] == "covariance-artifact.v1":
        view, evidence_refs = _realize_covariance(artifact, adapter["binding"], selector)
    else:
        raise ValueError("Realization adapter validator is not implemented")
    evidence_refs = list(dict.fromkeys(evidence_refs))
    value = record(
        "representation-realization",
        realization_id=realization_id,
        adapter_registry_ref=adapter_registry["record_digest"],
        adapter_id=adapter_id,
        adapter_ref=adapter["record_digest"],
        representation_id=adapter["representation_id"],
        representation_ref=adapter["representation_ref"],
        validator_id=adapter["validator_id"],
        artifact_ref=content_identity(artifact),
        selector=selector,
        realized_view=view,
        evidence_refs=evidence_refs,
        notes=notes,
        claims={
            "artifact_realizes_representation_under_adapter": True,
            "family_validator_executed": True,
            "empirical_truth_established": False,
            "provider_execution": False,
            "canonical_state_mutated": False,
            "state_admission": False,
            "execution_authority": False,
        },
    )
    return value


def validate_realization(value: dict, adapter_registry: dict, morphism_registry: dict,
                         semantic: SemanticRegistry, artifact: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "realization_id", "adapter_registry_ref",
        "adapter_id", "adapter_ref", "representation_id", "representation_ref",
        "validator_id", "artifact_ref", "selector", "realized_view",
        "evidence_refs", "notes", "claims",
    })
    if value["schema"] != "ciw.representation-realization.v1":
        raise ValueError("Wrong representation realization schema")
    check_seal(value)
    expected = realize(
        adapter_registry, morphism_registry, semantic, artifact,
        {"realization_id": value["realization_id"], "adapter_id": value["adapter_id"],
         "selector": value["selector"], "notes": value["notes"]},
    )
    if value != expected:
        raise ValueError("Representation realization differs from exact family validation")
    return detached(value)


def bind_recovery_realization(adapter_registry: dict, morphism_registry: dict,
                              semantic: SemanticRegistry, gate: dict,
                              realization: dict, artifact: dict, binding_id: str) -> dict:
    """Bind a validated realization to an EXPAND gate, without verifying projection execution."""
    morphism_registry = validate_registry(morphism_registry, semantic)
    adapter_registry = validate_adapter_registry(adapter_registry, morphism_registry, semantic)
    gate = validate_gate(gate, morphism_registry, semantic)
    realization = validate_realization(
        realization, adapter_registry, morphism_registry, semantic, artifact)
    if gate["decision"] != "EXPAND":
        raise ValueError("Recovery realization binding requires an EXPAND gate")
    if realization["representation_id"] != gate["recovery_representation_id"]:
        raise ValueError("Realization is not the richer representation requested by the gate")
    if realization["representation_ref"] != gate["recovery_representation_ref"]:
        raise ValueError("Realization uses a different richer representation contract")
    if gate["recovery_evidence_ref"] not in realization["evidence_refs"]:
        raise ValueError("Realization does not retain the recovery evidence named by the gate")
    value = record(
        "recovery-realization-binding",
        binding_id=text(binding_id),
        adapter_registry_ref=adapter_registry["record_digest"],
        gate_ref=gate["record_digest"],
        realization_ref=realization["record_digest"],
        recovery_representation_id=realization["representation_id"],
        recovery_representation_ref=realization["representation_ref"],
        recovery_evidence_ref=gate["recovery_evidence_ref"],
        artifact_ref=realization["artifact_ref"],
        claims={
            "recovery_representation_realized": True,
            "recovery_evidence_bound": True,
            "projection_execution_verified": False,
            "intervention_reconsidered": False,
            "provider_execution": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    return value


def validate_recovery_binding(value: dict, adapter_registry: dict, morphism_registry: dict,
                              semantic: SemanticRegistry, gate: dict,
                              realization: dict, artifact: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "binding_id", "adapter_registry_ref", "gate_ref",
        "realization_ref", "recovery_representation_id", "recovery_representation_ref",
        "recovery_evidence_ref", "artifact_ref", "claims",
    })
    if value["schema"] != "ciw.recovery-realization-binding.v1":
        raise ValueError("Wrong recovery realization binding schema")
    check_seal(value)
    expected = bind_recovery_realization(
        adapter_registry, morphism_registry, semantic, gate, realization,
        artifact, value["binding_id"])
    if value != expected:
        raise ValueError("Recovery realization binding differs from exact recomputation")
    return detached(value)
