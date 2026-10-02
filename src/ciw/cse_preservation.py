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
from .control_contracts import state, validate_state
from .core.covariance import create_covariance_artifact
from .industrial_transition import validate_binding, validate_identity_verification
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



def _axis_name(quantity: dict) -> str:
    return "::".join((
        quantity["ifc_class"],
        quantity["global_id"],
        quantity["quantity"],
    ))


def _project_native_state(
    native: dict,
    *,
    canonical_entity_id: str,
    frame: str,
    witness: dict,
    bundle: dict,
    time_index: float,
    execution_id: str | None,
) -> dict:
    quantities = native["quantities"]
    names = [_axis_name(quantity) for quantity in quantities]
    variables = {
        name: {"value": native["mean"][index], "unit": quantities[index]["unit"]}
        for index, name in enumerate(names)
    }
    covariance = create_covariance_artifact(
        matrix=native["covariance"],
        quantity_ids=names,
        units=[quantity["unit"] for quantity in quantities],
        frame=frame,
        reference_values=native["mean"],
        method="native CSE retained covariance; no repair",
        basis={"kind": "estimated_state", "id": native["world_digest"]},
        provenance={
            "provider": "ciw.bim-quantity.v1",
            "source_evidence_ids": [
                witness["record_digest"],
                bundle["bundle_digest"],
            ],
            "source_covariance_ids": [],
            "metadata": {
                "native_world_digest": native["world_digest"],
                "native_belief_digest": native["belief_digest"],
            },
        },
        assumptions=[
            "CSE quantity ordering is retained exactly",
            "time_s is a transition index, not physical time",
        ],
    )
    return state(
        identity={
            "model_id": "cse.bim-quantity-state.v1",
            "entity_id": canonical_entity_id,
            "execution_id": execution_id,
        },
        clock={"id": "cse-conditioning-sequence", "time_s": time_index},
        frame=frame,
        variables=variables,
        uncertainty=covariance,
        provenance={
            "provider": "ciw.bim-quantity.v1",
            "sources": [witness["record_digest"], bundle["bundle_digest"]],
            "semantics": "estimated",
        },
    )


def project_bim_states(
    registry: dict,
    semantic: SemanticRegistry,
    preservation_contract: dict,
    profile: dict,
    ingress: dict,
    ingress_verification: dict,
    qualification: dict,
    mapping_witness: dict,
    bundle: dict,
    binding: dict,
    identity_verification: dict,
) -> tuple[dict, dict]:
    """Project exact native CSE prior/posterior into typed NET state records.

    A VERIFIED entity binding is required before assigning the canonical entity
    ID to the projected state records.
    """
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
    if witness["mapping_outcome"] != "MAPPED":
        raise ValueError("State projection requires an accepted BIM mapping occurrence")
    binding = validate_binding(binding)
    identity_verification = validate_identity_verification(identity_verification, binding)
    if identity_verification["status"] != "VERIFIED":
        raise ValueError("State projection requires VERIFIED cross-system identity")

    source_identity = witness["source_identity"]
    matching = [
        row for row in binding["references"]
        if (
            row["reference_id"] == source_identity["reference_id"]
            and row["system_id"] == witness["source_system_id"]
            and row["namespace"] == source_identity["namespace"]
            and row["external_id"] == source_identity["external_id"]
            and row["object_kind"] == source_identity["object_kind"]
        )
    ]
    if len(matching) != 1:
        raise ValueError("Verified entity binding does not contain the exact qualified IFC identity")

    source = _source(bundle)
    if source["model_frame"] is None:
        raise ValueError("Mapped BIM state projection requires a declared model frame")
    data = _native_data(bundle)
    if data["prior"] is None or data["posterior"] is None:
        raise ValueError("Mapped BIM state projection requires native prior/posterior")

    prior = _project_native_state(
        data["prior"],
        canonical_entity_id=binding["canonical_entity_id"],
        frame=source["model_frame"],
        witness=witness,
        bundle=bundle,
        time_index=0.0,
        execution_id=None,
    )
    candidate = _project_native_state(
        data["posterior"],
        canonical_entity_id=binding["canonical_entity_id"],
        frame=source["model_frame"],
        witness=witness,
        bundle=bundle,
        time_index=1.0,
        execution_id=witness["native_execution_ref"],
    )
    validate_projected_bim_states(
        prior, candidate, witness, bundle, binding, identity_verification
    )
    return prior, candidate


def validate_projected_bim_states(
    prior: dict,
    candidate: dict,
    witness: dict,
    bundle: dict,
    binding: dict,
    identity_verification: dict,
) -> None:
    validate_state(prior)
    validate_state(candidate)
    binding = validate_binding(binding)
    identity_verification = validate_identity_verification(identity_verification, binding)
    if identity_verification["status"] != "VERIFIED":
        raise ValueError("Projected BIM states require VERIFIED identity")
    data = _native_data(bundle)
    source = _source(bundle)
    if witness["mapping_outcome"] != "MAPPED":
        raise ValueError("Projected BIM states require MAPPED witness")
    if prior["identity"]["entity_id"] != binding["canonical_entity_id"]:
        raise ValueError("Projected prior entity differs from verified binding")
    if candidate["identity"]["entity_id"] != binding["canonical_entity_id"]:
        raise ValueError("Projected candidate entity differs from verified binding")
    if candidate["identity"]["execution_id"] != witness["native_execution_ref"]:
        raise ValueError("Projected candidate execution differs from mapping witness")
    if prior["frame"] != source["model_frame"] or candidate["frame"] != source["model_frame"]:
        raise ValueError("Projected BIM state frame differs from native source")
    for projected, native in ((prior, data["prior"]), (candidate, data["posterior"])):
        names = [_axis_name(quantity) for quantity in native["quantities"]]
        if list(projected["variables"]) != names:
            raise ValueError("Projected BIM state variable order differs from native CSE quantities")
        for index, name in enumerate(names):
            if projected["variables"][name] != {
                "value": native["mean"][index],
                "unit": native["quantities"][index]["unit"],
            }:
                raise ValueError("Projected BIM state quantity differs from native CSE state")
        covariance = projected["uncertainty"]
        if covariance["matrix"] != native["covariance"]:
            raise ValueError("Projected BIM covariance differs from native CSE covariance")
        if covariance["reference_values"] != native["mean"]:
            raise ValueError("Projected BIM covariance reference differs from native mean")
        if covariance["basis"]["id"] != native["world_digest"]:
            raise ValueError("Projected BIM covariance basis differs from native world")

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
