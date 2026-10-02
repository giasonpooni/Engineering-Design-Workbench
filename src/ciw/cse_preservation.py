"""CSE-backed preservation verifier for the IFC interoperability bridge.

This adapter consumes:
- one typed preservation contract;
- one exact ciw.interop-mapping-witness.v1;
- the exact retained ciw.bim-quantity session used by that witness.

It discharges only the small set of preservation properties for which the
existing BIM/CSE runtime retains direct evidence. Unsupported obligations remain
UNRESOLVED. Runtime success is never treated as a universal proof.
"""
from __future__ import annotations

import base64
import json

from .bim_interop import validate_bim_mapping_witness
from .bim_quantity import workflow as bim_workflow
from .preservation_contracts import (
    validate_contract,
    verification_from_spec,
)
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry


SUPPORTED = {
    "identity.ifc-target.v1",
    "frame.declared-compatible.v1",
    "uncertainty.independent-measurement.v1",
    "unit.length-metres.v1",
    "uncertainty.full-covariance.v1",
    "geometry.solid-authority.v1",
}


def _source(bundle: dict) -> dict:
    raw = bim_workflow._validate(bundle)
    return bim_workflow._source(raw)


def _observation(source: dict) -> dict:
    raw = base64.b64decode(source["observation_bytes_b64"], validate=True)
    value = json.loads(raw.decode("utf-8"))
    if type(value) is not dict:
        raise ValueError("BIM preservation verifier requires object observation")
    return value


def _native_data(bundle: dict) -> dict:
    step, = bundle["steps"]
    result = step["result"]
    data = result["data"]
    if type(data) is not dict:
        raise ValueError("BIM preservation verifier requires native result data")
    return data


def _native_state_refs(data: dict) -> tuple[str, str]:
    prior = data.get("prior")
    posterior = data.get("posterior")
    if type(prior) is not dict or type(posterior) is not dict:
        raise ValueError("BIM preservation verifier requires retained prior/posterior worlds")
    for item in (prior, posterior):
        digest = item.get("world_digest")
        if type(digest) is not str or len(digest) != 64:
            raise ValueError("Native CSE world digest is malformed")
    return "sha256:" + prior["world_digest"], "sha256:" + posterior["world_digest"]


def _mapped(witness: dict) -> bool:
    return witness["mapping_outcome"] == "MAPPED"


def _check_property(
    *, kind: str, property_id: str, witness: dict, source: dict,
    observation: dict, data: dict,
) -> dict:
    mapped = _mapped(witness)
    evidence_ref = witness["record_digest"]

    if property_id not in SUPPORTED:
        return {
            "kind": kind,
            "property_id": property_id,
            "status": "UNRESOLVED",
            "method": "NOT_PERFORMED",
            "evidence_ref": None,
            "notes": "CSE verifier has no V1 rule for this preservation property.",
        }

    if property_id == "identity.ifc-target.v1":
        ok = (
            data["target"] == source["target"]
            and observation["ifc_class"] == source["target"]["ifc_class"]
            and observation["global_id"] == source["target"]["global_id"]
            and observation["quantity"] == source["target"]["quantity"]
        )
        status = "VERIFIED" if ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "EXACT_ALGEBRA", "evidence_ref": evidence_ref,
            "notes": "Exact IFC class/global-id/quantity equality across source, observation and native result.",
        }

    if property_id == "frame.declared-compatible.v1":
        ok = (
            source["model_frame"] is not None
            and observation["frame"] == source["model_frame"]
            and data["model_frame"] == source["model_frame"]
        )
        status = "VERIFIED" if ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "EXACT_ALGEBRA", "evidence_ref": evidence_ref,
            "notes": "Declared frame labels agree; this is applicability only, not surveyed frame authority.",
        }

    if property_id == "uncertainty.independent-measurement.v1":
        ok = observation["cross_covariance_policy"] == "independent"
        status = "VERIFIED" if ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "EXACT_ALGEBRA", "evidence_ref": evidence_ref,
            "notes": "Exact retained cross-covariance policy declaration; does not prove physical independence.",
        }

    if property_id == "unit.length-metres.v1":
        if not mapped:
            return {
                "kind": kind, "property_id": property_id, "status": "UNRESOLVED",
                "method": "NOT_PERFORMED", "evidence_ref": None,
                "notes": "No accepted mapping occurrence exists for unit-preservation verification.",
            }
        target = source["target"]
        prior = data["prior"]
        posterior = data["posterior"]
        prior_q = next(
            (q for q in prior["quantities"] if all(q[k] == target[k] for k in target)),
            None,
        )
        post_q = next(
            (q for q in posterior["quantities"] if all(q[k] == target[k] for k in target)),
            None,
        )
        ok = (
            observation["unit"] == "m"
            and prior_q is not None and prior_q["unit"] == "m"
            and post_q is not None and post_q["unit"] == "m"
        )
        status = "VERIFIED" if ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "EXACT_ALGEBRA", "evidence_ref": evidence_ref,
            "notes": "Target quantity is retained in metres across observation, prior and posterior.",
        }

    if property_id == "uncertainty.full-covariance.v1":
        if not mapped:
            return {
                "kind": kind, "property_id": property_id, "status": "UNRESOLVED",
                "method": "NOT_PERFORMED", "evidence_ref": None,
                "notes": "No accepted mapping occurrence exists for covariance-preservation verification.",
            }
        prior = data["prior"]
        posterior = data["posterior"]
        same_axes = prior["quantities"] == posterior["quantities"]
        shape_ok = (
            len(prior["covariance"]) == len(prior["quantities"])
            and len(posterior["covariance"]) == len(posterior["quantities"])
        )
        status = "VERIFIED" if same_axes and shape_ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "NUMERICAL_BOUND", "evidence_ref": evidence_ref,
            "notes": (
                "Existing BIM session validation has already checked retained full covariance "
                "symmetry/PSD tolerance without repair; this check binds identical quantity axes."
            ),
        }

    if property_id == "geometry.solid-authority.v1":
        ok = data["geometry_authority"] == "QUANTITY_ONLY"
        status = "VERIFIED" if ok else "REFUTED"
        return {
            "kind": kind, "property_id": property_id, "status": status,
            "method": "EXACT_ALGEBRA", "evidence_ref": evidence_ref,
            "notes": (
                "CSE explicitly retains QUANTITY_ONLY geometry authority; solid-geometry "
                "authority is therefore not carried by this mapping."
            ),
        }

    raise AssertionError("unreachable supported preservation property")


def verify_bim_preservation(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    ingress_verification: dict,
    qualification: dict,
    mapping_witness: dict,
    bundle: dict,
    *,
    verification_id: str,
    notes: str = "",
) -> dict:
    """Create a typed preservation receipt from scoped native CSE evidence."""
    registry = validate_registry(registry, semantic)
    contract = validate_contract(preservation_contract, registry, semantic)
    witness = validate_bim_mapping_witness(
        mapping_witness,
        registry,
        semantic,
        contract,
        profile,
        ingress,
        ingress_verification,
        qualification,
        bundle,
    )
    source = _source(bundle)
    observation = _observation(source)
    data = _native_data(bundle)
    source_ref, candidate_ref = _native_state_refs(data)

    checks = []
    for property_id in contract["requires"]:
        checks.append(_check_property(
            kind="REQUIRE",
            property_id=property_id,
            witness=witness,
            source=source,
            observation=observation,
            data=data,
        ))
    for effect in contract["effects"]:
        checks.append(_check_property(
            kind=effect["effect"],
            property_id=effect["property_id"],
            witness=witness,
            source=source,
            observation=observation,
            data=data,
        ))

    return verification_from_spec(
        registry,
        semantic,
        contract,
        {
            "verification_id": verification_id,
            "source_state_ref": source_ref,
            "candidate_state_ref": candidate_ref,
            "checks": checks,
            "notes": notes,
        },
    )
