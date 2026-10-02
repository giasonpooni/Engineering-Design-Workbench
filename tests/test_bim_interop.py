"""Qualification of the first real external-artifact -> CSE mapping bridge."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import runpy

import pytest

from ciw.bim_interop import execute_bim_mapping, execute_bim_mapping_bundle, validate_bim_mapping_witness
from ciw.cse_preservation import verify_bim_preservation
from ciw.control_plane import builtin_registry
from ciw.interop_ingress import (
    ingress_from_spec,
    profile_from_spec,
    qualify_ingress,
    verification_from_spec as ingress_verification_from_spec,
)
from ciw.operations.runner import seal
from ciw.preservation_contracts import contract_from_spec
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.telemetry import byte_digest, canonical

ROOT = Path(__file__).resolve().parents[1]


def source():
    return runpy.run_path(str(ROOT / "examples/bim-quantity/make_source.py"))["source"]()


def semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def representation(rep_id, role):
    return {
        "representation_id": rep_id,
        "role": role,
        "source_state_type": "ifc-bim-quantity",
        "schema_id": "ciw.bim-quantity-source.v1" if role == "TABLE" else "ciw.bim-quantity.v1",
        "quantity_semantics": "IFC quantity evidence" if role == "TABLE" else "CSE quantity state",
        "unit_semantics": "CSE normalizes supported declared IFC length units to metres",
        "frame_semantics": "matching declared frame labels are applicability only, not surveyed authority",
        "time_semantics": "single bounded conditioning occurrence",
        "scale": {"length_m": None, "time_s": None, "energy_j": None, "resolution": None, "label": "building-quantity"},
        "uncertainty_semantics": "full native CSE prior/posterior covariance retained",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": ["ifc-target-identity", "quantity-unit", "native-invariants"],
        "supported_interventions": ["scalar-quantity-observation"],
        "recovery_route": None,
        "provenance_refs": [],
        "notes": "Bounded real in-repo IFC/CSE workload representation.",
    }


def morphism():
    return {
        "morphism_id": "interop.ifc-to-cse-quantity.v1",
        "kind": "ESTIMATE",
        "domain_representation_id": "interop.ifc-quantity-source.v1",
        "codomain_representation_id": "interop.cse-quantity-state.v1",
        "semantic_capability": None,
        "parameter_names": [],
        "preconditions": ["exact IFC byte identity", "target identity", "declared compatible frame", "declared units", "independent scalar measurement noise"],
        "validity": {
            "assumptions": ["quantity-only geometry authority", "declared frame labels are applicability only"],
            "operating_regime": ["bounded IFC source and one scalar raw metre quantity"],
            "failure_conditions": ["unknown cross covariance", "frame mismatch", "unit mismatch", "native invariant failure"],
        },
        "preservation": {
            "queries": ["ifc-target-identity", "quantity-unit", "native-invariants"],
            "interventions": ["scalar-quantity-observation"],
            "invariants": ["quantity topology identity", "native CSE invariant report"],
            "approximation_tolerance": None,
        },
        "loss": {"class": "TASK_SPECIFIC", "description": "Solid geometry authority is not carried by this quantity-only map.", "metrics": {}},
        "uncertainty": {"behavior": "PROPAGATE", "method": "native CSE Gaussian conditioning with retained covariance"},
        "reversibility": "NONE",
        "authority_requirements": [],
        "verification_requirements": ["exact source/result IFC identity", "native ledger replay", "native invariant report"],
        "provenance_refs": [],
        "notes": "Existing CSE workload, represented as an interoperability morphism.",
    }


def setup_objects():
    sem = semantic()
    reg = registry_from_specs(
        [
            representation("interop.ifc-quantity-source.v1", "TABLE"),
            representation("interop.cse-quantity-state.v1", "STATE"),
        ],
        [morphism()],
        sem,
    )
    contract = contract_from_spec(reg, sem, {
        "contract_id": "interop.ifc-cse-preservation.v1",
        "morphism_id": "interop.ifc-to-cse-quantity.v1",
        "requires": ["identity.ifc-target.v1", "frame.declared-compatible.v1", "uncertainty.independent-measurement.v1"],
        "effects": [
            {"property_id": "identity.ifc-target.v1", "effect": "PRESERVE", "output_property_id": "identity.ifc-target.v1", "transform_id": None, "bound": None, "notes": ""},
            {"property_id": "unit.length-metres.v1", "effect": "PRESERVE", "output_property_id": "unit.length-metres.v1", "transform_id": None, "bound": None, "notes": ""},
            {"property_id": "uncertainty.full-covariance.v1", "effect": "PRESERVE", "output_property_id": "uncertainty.full-covariance.v1", "transform_id": None, "bound": None, "notes": ""},
            {"property_id": "geometry.solid-authority.v1", "effect": "FORGET", "output_property_id": None, "transform_id": None, "bound": None, "notes": "Quantity-only CSE path carries no solid geometry authority."},
        ],
        "notes": "Runtime contract for the existing IFC/CSE quantity workflow.",
    })
    profile = profile_from_spec(reg, sem, contract, {
        "profile_id": "interop.ifc4-quantity-profile.v1",
        "source_family": "STANDARD",
        "standard_id": "standard.ifc4.v1",
        "source_profile_id": "standard.ifc4-bounded-quantity.v1",
        "source_system_id": "industrial.ifc-source.v1",
        "source_schema_id": "IFC4 fixture parsed by pinned CSE/GAT runtime; no external buildingSMART certification claim",
        "morphism_id": "interop.ifc-to-cse-quantity.v1",
        "mapping_id": "interop.mapping-ifc-cse-quantity.v1",
        "mapping_assumptions": ["exact IFC bytes are retained", "quantity-only authority", "frame labels are declared applicability only"],
        "uncertainty_semantics": "native CSE prior/posterior covariance retained; independence is explicit input policy",
        "declared_loss_properties": ["geometry.solid-authority.v1"],
        "verification_requirements": ["exact IFC identity", "target binding", "native invariant report", "ledger replay"],
        "notes": "Executable profile over the existing bounded IFC workload.",
    })
    src = source()
    raw_ifc = base64.b64decode(src["ifc_bytes_b64"], validate=True)
    ingress = ingress_from_spec(profile, {
        "ingress_id": "interop.ifc-room-occurrence.v1",
        "payload_ref": byte_digest(raw_ifc),
        "payload_media_type": "application/x-step",
        "source_identity": {
            "reference_id": "industrial.ref-ifc-storey15.v1",
            "namespace": "ifc-global-id",
            "external_id": src["target"]["global_id"],
            "object_kind": "BIM_OBJECT",
        },
        "mapping_parameters": {"ifc_class": src["target"]["ifc_class"], "quantity": src["target"]["quantity"], "model_frame": src["model_frame"]},
        "mapping_evidence_refs": [byte_digest(canonical(src))],
        "notes": "Exact in-repo IFC bytes; qualification precedes runtime mapping.",
    })
    checks = []
    methods = {
        "PROFILE_CONFORMANCE": "DECLARED_PROFILE",
        "SOURCE_IDENTITY": "EVIDENCE_CROSSCHECK",
        "REPRESENTATION_MAPPING": "MAPPING_TEST",
        "MAPPING_ASSUMPTIONS": "MAPPING_TEST",
        "UNCERTAINTY_HANDLING": "EVIDENCE_CROSSCHECK",
        "PRESERVATION_PRECONDITIONS": "MAPPING_TEST",
    }
    for i, kind in enumerate(sorted(methods)):
        checks.append({"kind": kind, "status": "VERIFIED", "method": methods[kind],
                       "evidence_ref": "sha256:" + str(i + 1) * 64, "notes": "Synthetic qualification evidence for in-repo integration test."})
    verification = ingress_verification_from_spec(profile, ingress, {
        "verification_id": "interop.ifc-ingress-verification.v1",
        "checks": checks,
        "notes": "Qualification verifies declared ingress/mapping preconditions; not physical truth.",
    })
    qualification = qualify_ingress(reg, sem, contract, profile, ingress, verification)
    return sem, reg, contract, profile, ingress, verification, qualification, src


@pytest.fixture(scope="module")
def repositories():
    path = os.environ.get("CIW_CSE_REPO")
    if not path:
        pytest.skip("set CIW_CSE_REPO for pinned native CSE integration")
    return {"cse": Path(path)}


def test_exact_in_repo_ifc_executes_only_after_qualified_ingress(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    witness = execute_bim_mapping(
        reg, sem, contract, profile, ingress, verification, qualification,
        src, repositories, {"execution_id": "interop.ifc-cse-execution.v1", "notes": ""},
    )
    assert witness["mapping_outcome"] == "MAPPED"
    assert witness["payload_ref"] == ingress["payload_ref"]
    assert witness["native_status"] == "accepted"
    assert witness["native_reason"] == "conditioned"
    assert witness["claims"]["mapping_executed"] is True
    assert witness["claims"]["mapping_accepted"] is True
    assert witness["claims"]["preservation_verification_performed"] is False
    assert witness["claims"]["state_admission_performed"] is False


def test_ingress_payload_must_be_exact_ifc_bytes(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    bad_ingress = deepcopy(ingress)
    bad_ingress["payload_ref"] = "sha256:" + "f" * 64
    bad_ingress.pop("record_digest")
    bad_ingress = seal(bad_ingress)
    # Qualification is bound to the original ingress, so the mismatch is rejected
    # before provider execution.
    with pytest.raises(ValueError):
        execute_bim_mapping(
            reg, sem, contract, profile, bad_ingress, verification, qualification,
            src, repositories, {"execution_id": "interop.ifc-cse-mismatch.v1", "notes": ""},
        )


def test_runtime_witness_recomputes_against_retained_native_bundle(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    witness = execute_bim_mapping(
        reg, sem, contract, profile, ingress, verification, qualification,
        src, repositories, {"execution_id": "interop.ifc-cse-recompute.v1", "notes": ""},
    )
    # Execute a fresh bundle for validator-negative coverage; occurrence IDs differ,
    # therefore it cannot validate the prior witness.
    from ciw.bim_quantity import workflow
    fresh = workflow.create_session(canonical(src), repositories)
    with pytest.raises(ValueError, match="mismatch"):
        validate_bim_mapping_witness(
            witness, reg, sem, contract, profile, ingress, verification,
            qualification, fresh,
        )


def test_cse_preservation_verifier_discharges_supported_contract(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    witness, bundle = execute_bim_mapping_bundle(
        reg, sem, contract, profile, ingress, verification, qualification,
        src, repositories, {"execution_id": "interop.ifc-cse-verify.v1", "notes": ""},
    )
    receipt = verify_bim_preservation(
        reg, sem, contract, profile, ingress, verification, qualification,
        witness, bundle,
        verification_id="interop.ifc-cse-preservation-verification.v1",
        notes="Scoped native CSE evidence only.",
    )
    assert receipt["status"] == "VERIFIED"
    assert receipt["source_state_ref"] == "sha256:" + witness["prior_world_digest"]
    assert receipt["candidate_state_ref"] == "sha256:" + witness["posterior_world_digest"]
    assert len(receipt["checks"]) == len(contract["requires"]) + len(contract["effects"])
    assert all(check["status"] == "VERIFIED" for check in receipt["checks"])
    assert any(
        check["property_id"] == "uncertainty.full-covariance.v1"
        and check["method"] == "NUMERICAL_BOUND"
        for check in receipt["checks"]
    )
    assert receipt["claims"]["verification_is_not_admission"] is True
    assert receipt["claims"]["canonical_state_mutated"] is False


def test_held_mapping_cannot_be_upgraded_to_fully_verified_preservation(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    held = deepcopy(src)
    observation = json.loads(base64.b64decode(held["observation_bytes_b64"]))
    observation["cross_covariance_policy"] = "unknown"
    held["observation_bytes_b64"] = base64.b64encode(canonical(observation)).decode()
    witness, bundle = execute_bim_mapping_bundle(
        reg, sem, contract, profile, ingress, verification, qualification,
        held, repositories, {"execution_id": "interop.ifc-cse-held-verify.v1", "notes": ""},
    )
    assert witness["mapping_outcome"] == "HELD"
    receipt = verify_bim_preservation(
        reg, sem, contract, profile, ingress, verification, qualification,
        witness, bundle,
        verification_id="interop.ifc-cse-held-preservation.v1",
        notes="Held native mapping must not become a verified transition.",
    )
    assert receipt["status"] in {"REFUTED", "UNRESOLVED"}
    checks = {(row["kind"], row["property_id"]): row for row in receipt["checks"]}
    assert checks[("REQUIRE", "uncertainty.independent-measurement.v1")]["status"] == "REFUTED"
    assert checks[("PRESERVE", "uncertainty.full-covariance.v1")]["status"] == "UNRESOLVED"


def test_cse_preservation_verifier_leaves_unknown_property_unresolved(repositories):
    sem, reg, contract, profile, ingress, verification, qualification, src = setup_objects()
    witness, bundle = execute_bim_mapping_bundle(
        reg, sem, contract, profile, ingress, verification, qualification,
        src, repositories, {"execution_id": "interop.ifc-cse-unknown.v1", "notes": ""},
    )
    from ciw.cse_preservation import _check_property
    source_record = runpy.run_path(str(ROOT / "examples/bim-quantity/make_source.py"))["source"]()
    observation = json.loads(base64.b64decode(source_record["observation_bytes_b64"]))
    data = bundle["steps"][0]["result"]["data"]
    check = _check_property(
        kind="PRESERVE",
        property_id="physics.energy-conservation.v1",
        witness=witness,
        source=source_record,
        observation=observation,
        data=data,
    )
    assert check["status"] == "UNRESOLVED"
    assert check["method"] == "NOT_PERFORMED"
    assert check["evidence_ref"] is None
