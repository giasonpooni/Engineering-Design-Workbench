from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry
from ciw.industrial_transition import binding_from_spec, validate_binding
from ciw.interop_ingress import (
    identity_reference_from_qualification,
    ingress_from_spec,
    profile_from_spec,
    qualify_ingress,
    validate_profile,
    validate_qualification,
    validate_verification,
    verification_from_spec,
)
from ciw.operations.runner import seal
from ciw.preservation_contracts import contract_from_spec
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry


def ref(char):
    return "sha256:" + char * 64


def semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def representation(rep_id, role):
    return {
        "representation_id": rep_id,
        "role": role,
        "source_state_type": "synthetic-external-fixture",
        "schema_id": "ciw.synthetic-interoperability.v1",
        "quantity_semantics": "synthetic external representation",
        "unit_semantics": "fixture units",
        "frame_semantics": "fixture frame",
        "time_semantics": "single retained occurrence",
        "scale": {
            "length_m": None,
            "time_s": None,
            "energy_j": None,
            "resolution": None,
            "label": "fixture",
        },
        "uncertainty_semantics": "declared only; no physical calibration",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": ["asset-identity"],
        "supported_interventions": [],
        "recovery_route": None,
        "provenance_refs": [],
        "notes": "Synthetic interoperability fixture; not a real standard parser.",
    }


def morphism_spec():
    return {
        "morphism_id": "interop.external-to-net.v1",
        "kind": "TRANSFORM",
        "domain_representation_id": "interop.external-payload.v1",
        "codomain_representation_id": "interop.net-state.v1",
        "semantic_capability": None,
        "parameter_names": [],
        "preconditions": [
            "declared external profile",
            "explicit mapping evidence",
        ],
        "validity": {
            "assumptions": ["synthetic fixture"],
            "operating_regime": ["one bounded retained payload"],
            "failure_conditions": ["mapping precondition unresolved"],
        },
        "preservation": {
            "queries": ["asset-identity"],
            "interventions": [],
            "invariants": ["physical entity identity"],
            "approximation_tolerance": None,
        },
        "loss": {
            "class": "TASK_SPECIFIC",
            "description": "Vendor-specific detail may be intentionally discarded.",
            "metrics": {},
        },
        "uncertainty": {
            "behavior": "PROPAGATE",
            "method": "declared external uncertainty mapping",
        },
        "reversibility": "NONE",
        "authority_requirements": [],
        "verification_requirements": [
            "external profile and mapping checks",
        ],
        "provenance_refs": [],
        "notes": "Synthetic external-to-NET morphism.",
    }


def registry():
    sem = semantic()
    reg = registry_from_specs(
        [
            representation("interop.external-payload.v1", "TABLE"),
            representation("interop.net-state.v1", "STATE"),
        ],
        [morphism_spec()],
        sem,
    )
    return sem, reg


def preservation_spec():
    return {
        "contract_id": "interop.external-preservation.v1",
        "morphism_id": "interop.external-to-net.v1",
        "requires": ["identity.physical-entity.v1"],
        "effects": [
            {
                "property_id": "identity.physical-entity.v1",
                "effect": "PRESERVE",
                "output_property_id": "identity.physical-entity.v1",
                "transform_id": None,
                "bound": None,
                "notes": "",
            },
            {
                "property_id": "geometry.vendor-extension.v1",
                "effect": "FORGET",
                "output_property_id": None,
                "transform_id": None,
                "bound": None,
                "notes": "Vendor-only extension is intentionally not part of target representation.",
            },
        ],
        "notes": "Synthetic preservation contract for external ingress.",
    }


def objects():
    sem, reg = registry()
    contract = contract_from_spec(reg, sem, preservation_spec())
    return sem, reg, contract


def standard_profile_spec():
    return {
        "profile_id": "interop.step-like-profile.v1",
        "source_family": "STANDARD",
        "standard_id": "standard.iso-10303.v1",
        "source_profile_id": "standard.step-ap242-like.v1",
        "source_system_id": "industrial.cad-exporter.v1",
        "source_schema_id": "synthetic STEP-like fixture label; no ISO conformance claim",
        "morphism_id": "interop.external-to-net.v1",
        "mapping_id": "interop.mapping-step-like.v1",
        "mapping_assumptions": [
            "fixture external ID is supplied explicitly",
            "no vendor extension is interpreted as physical truth",
        ],
        "uncertainty_semantics": "no metrological uncertainty established by schema conformance",
        "declared_loss_properties": ["geometry.vendor-extension.v1"],
        "verification_requirements": [
            "profile conformance evidence",
            "mapping evidence",
            "preservation preconditions",
        ],
        "notes": "Synthetic standards-shaped fixture; no real STEP parser or certificate.",
    }


def proprietary_profile_spec():
    value = standard_profile_spec()
    value["profile_id"] = "interop.proprietary-profile.v1"
    value["source_family"] = "PROPRIETARY"
    value["standard_id"] = None
    value["source_profile_id"] = "vendor.machine-schema.v1"
    value["source_system_id"] = "vendor.machine-exporter.v1"
    value["source_schema_id"] = "vendor-private-format"
    value["mapping_id"] = "interop.mapping-vendor-schema.v1"
    return value


def ingress_spec():
    return {
        "ingress_id": "interop.payload-occurrence.v1",
        "payload_ref": ref("1"),
        "payload_media_type": "application/octet-stream",
        "source_identity": {
            "reference_id": "industrial.ref-cad-pump17.v1",
            "namespace": "cad-object",
            "external_id": "PUMP-17",
            "object_kind": "CAD_OBJECT",
        },
        "mapping_parameters": {
            "declared_coordinate_frame": "fixture-frame",
            "operator_mapping_revision": "1",
        },
        "mapping_evidence_refs": [ref("2"), ref("3")],
        "notes": "Synthetic external payload occurrence.",
    }


def verification_spec(overrides=None):
    overrides = overrides or {}
    methods = {
        "PROFILE_CONFORMANCE": "CONFORMANCE_TOOL",
        "SOURCE_IDENTITY": "EVIDENCE_CROSSCHECK",
        "REPRESENTATION_MAPPING": "MAPPING_TEST",
        "MAPPING_ASSUMPTIONS": "MAPPING_TEST",
        "UNCERTAINTY_HANDLING": "EVIDENCE_CROSSCHECK",
        "PRESERVATION_PRECONDITIONS": "MAPPING_TEST",
    }
    checks = []
    for index, kind in enumerate(sorted(methods)):
        status = overrides.get(kind, "VERIFIED")
        checks.append({
            "kind": kind,
            "status": status,
            "method": methods[kind] if status != "UNRESOLVED" else "NOT_PERFORMED",
            "evidence_ref": ref(str((index + 4) % 10)) if status != "UNRESOLVED" else None,
            "notes": "",
        })
    return {
        "verification_id": "interop.external-verification.v1",
        "checks": checks,
        "notes": "Synthetic verification receipt; evidence refs are fixture identities.",
    }


def full_fixture(overrides=None):
    sem, reg, contract = objects()
    profile = profile_from_spec(reg, sem, contract, standard_profile_spec())
    ingress = ingress_from_spec(profile, ingress_spec())
    verification = verification_from_spec(profile, ingress, verification_spec(overrides))
    qualification = qualify_ingress(
        reg, sem, contract, profile, ingress, verification
    )
    return sem, reg, contract, profile, ingress, verification, qualification


def test_standard_profile_is_bound_to_existing_morphism_and_preservation_contract():
    sem, reg, contract = objects()
    profile = profile_from_spec(reg, sem, contract, standard_profile_spec())
    checked = validate_profile(profile, reg, sem, contract)
    morphism = reg["morphisms"]["interop.external-to-net.v1"]
    assert checked["morphism_ref"] == morphism["record_digest"]
    assert checked["source_representation_id"] == morphism["domain_representation_id"]
    assert checked["target_representation_id"] == morphism["codomain_representation_id"]
    assert checked["preservation_contract_ref"] == contract["record_digest"]
    assert checked["claims"]["standard_or_schema_conformance_established"] is False
    assert checked["claims"]["semantic_preservation_established"] is False


def test_proprietary_profile_uses_same_semantic_ingress_contract():
    sem, reg, contract = objects()
    profile = profile_from_spec(reg, sem, contract, proprietary_profile_spec())
    assert profile["source_family"] == "PROPRIETARY"
    assert profile["standard_id"] is None
    assert profile["morphism_id"] == "interop.external-to-net.v1"


def test_standard_profile_requires_standard_id():
    sem, reg, contract = objects()
    spec = standard_profile_spec()
    spec["standard_id"] = None
    with pytest.raises(ValueError, match="standard_id"):
        profile_from_spec(reg, sem, contract, spec)


def test_proprietary_profile_refuses_fake_standard_id():
    sem, reg, contract = objects()
    spec = proprietary_profile_spec()
    spec["standard_id"] = "standard.fake.v1"
    with pytest.raises(ValueError, match="standard_id=null"):
        profile_from_spec(reg, sem, contract, spec)


def test_profile_declared_loss_must_match_preservation_contract():
    sem, reg, contract = objects()
    spec = standard_profile_spec()
    spec["declared_loss_properties"] = []
    with pytest.raises(ValueError, match="exactly match"):
        profile_from_spec(reg, sem, contract, spec)


def test_ingress_retains_payload_without_executing_mapping():
    sem, reg, contract = objects()
    profile = profile_from_spec(reg, sem, contract, standard_profile_spec())
    ingress = ingress_from_spec(profile, ingress_spec())
    assert ingress["payload_ref"] == ref("1")
    assert ingress["claims"]["mapping_executed"] is False
    assert ingress["claims"]["profile_conformance_established"] is False
    assert ingress["claims"]["semantic_preservation_established"] is False


def test_verification_requires_all_check_kinds_exactly_once():
    sem, reg, contract = objects()
    profile = profile_from_spec(reg, sem, contract, standard_profile_spec())
    ingress = ingress_from_spec(profile, ingress_spec())
    spec = verification_spec()
    spec["checks"].pop()
    with pytest.raises(ValueError, match="cover all V1 check kinds"):
        verification_from_spec(profile, ingress, spec)


def test_unresolved_check_keeps_ingress_unresolved():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture(
        {"MAPPING_ASSUMPTIONS": "UNRESOLVED"}
    )
    assert verification["status"] == "UNRESOLVED"
    assert qualification["status"] == "UNRESOLVED"
    assert qualification["claims"]["qualified_for_net_identity_and_semantic_workflow"] is False


def test_refuted_profile_or_mapping_refuses_ingress():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture(
        {"PROFILE_CONFORMANCE": "REFUTED"}
    )
    assert verification["status"] == "REFUTED"
    assert qualification["status"] == "REFUSED"


def test_verified_ingress_is_qualified_but_not_mapped_or_admitted():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture()
    checked = validate_qualification(
        qualification, reg, sem, contract, profile, ingress, verification
    )
    assert checked["status"] == "QUALIFIED"
    assert checked["claims"]["mapping_executed"] is False
    assert checked["claims"]["state_admission_performed"] is False
    assert checked["claims"]["physical_validity_established"] is False


def test_qualified_ingress_projects_into_existing_entity_binding_shape():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture()
    reference = identity_reference_from_qualification(
        qualification, reg, sem, contract, profile, ingress, verification
    )
    assert reference == {
        "reference_id": "industrial.ref-cad-pump17.v1",
        "system_id": "industrial.cad-exporter.v1",
        "namespace": "cad-object",
        "external_id": "PUMP-17",
        "object_kind": "CAD_OBJECT",
        "evidence_ref": qualification["record_digest"],
    }
    binding = binding_from_spec({
        "binding_id": "industrial.asset17-external-binding.v1",
        "canonical_entity_id": "asset-17",
        "references": [reference],
        "notes": "Identity admission remains separate.",
    })
    validate_binding(binding)
    assert binding["claims"]["canonical_entity_created"] is False


def test_unresolved_ingress_cannot_project_identity_reference():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture(
        {"SOURCE_IDENTITY": "UNRESOLVED"}
    )
    with pytest.raises(ValueError, match="Only QUALIFIED"):
        identity_reference_from_qualification(
            qualification, reg, sem, contract, profile, ingress, verification
        )


def test_resealed_forged_qualification_fails_recomputation():
    sem, reg, contract, profile, ingress, verification, qualification = full_fixture(
        {"REPRESENTATION_MAPPING": "REFUTED"}
    )
    forged = deepcopy(qualification)
    forged["status"] = "QUALIFIED"
    forged["reasons"] = ["profile_mapping_and_preconditions_verified"]
    forged["claims"]["qualified_for_net_identity_and_semantic_workflow"] = True
    forged.pop("record_digest")
    forged = seal(forged)
    with pytest.raises(ValueError, match="differs from recomputed"):
        validate_qualification(
            forged, reg, sem, contract, profile, ingress, verification
        )


def test_cli_standard_profile_retain_verify_qualify_and_identity_projection(tmp_path):
    sem, reg, contract = objects()
    paths = {}
    for name, value in (("registry", reg), ("contract", contract)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path

    profile_spec_path = tmp_path / "profile-spec.json"
    profile_spec_path.write_text(json.dumps(standard_profile_spec()), encoding="utf-8")
    profile_path = tmp_path / "profile.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "interop", "create-profile",
        str(paths["registry"]), str(paths["contract"]), str(profile_spec_path),
        "--output", str(profile_path),
    ], check=True)

    ingress_spec_path = tmp_path / "ingress-spec.json"
    ingress_spec_path.write_text(json.dumps(ingress_spec()), encoding="utf-8")
    ingress_path = tmp_path / "ingress.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "interop", "retain",
        str(profile_path), str(ingress_spec_path), "--output", str(ingress_path),
    ], check=True)

    verification_spec_path = tmp_path / "verification-spec.json"
    verification_spec_path.write_text(json.dumps(verification_spec()), encoding="utf-8")
    verification_path = tmp_path / "verification.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "interop", "verify",
        str(profile_path), str(ingress_path), str(verification_spec_path),
        "--output", str(verification_path),
    ], check=True)

    qualification_path = tmp_path / "qualification.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "interop", "qualify",
        str(paths["registry"]), str(paths["contract"]), str(profile_path),
        str(ingress_path), str(verification_path), "--output", str(qualification_path),
    ], check=True)

    reference_path = tmp_path / "identity-reference.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "interop", "identity-reference",
        str(paths["registry"]), str(paths["contract"]), str(profile_path),
        str(ingress_path), str(verification_path), str(qualification_path),
        "--output", str(reference_path),
    ], check=True)

    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    assert qualification["status"] == "QUALIFIED"
    assert qualification["claims"]["mapping_executed"] is False
    assert reference["evidence_ref"] == qualification["record_digest"]
