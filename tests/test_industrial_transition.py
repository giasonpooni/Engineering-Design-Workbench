from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_contracts import state
from ciw.control_plane import builtin_registry
from ciw.industrial_transition import (
    binding_from_spec,
    identity_verification_from_spec,
    transition_envelope_from_spec,
    validate_binding,
    validate_identity_verification,
    validate_transition_envelope,
)
from ciw.operations.runner import seal
from ciw.preservation_contracts import (
    admission_gate_from_spec,
    contract_from_spec,
    verification_from_spec,
)
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry


def ref(char):
    return "sha256:" + char * 64


def semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def representation(rep_id):
    return {
        "representation_id": rep_id,
        "role": "STATE",
        "source_state_type": "synthetic-industrial-state",
        "schema_id": "ciw.state.v1",
        "quantity_semantics": "synthetic equipment state",
        "unit_semantics": "declared on state variables",
        "frame_semantics": "equipment-local",
        "time_semantics": "retained state tick",
        "scale": {
            "length_m": None,
            "time_s": None,
            "energy_j": None,
            "resolution": None,
            "label": "equipment",
        },
        "uncertainty_semantics": "state fixture has no covariance",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": ["equipment-temperature"],
        "supported_interventions": [],
        "recovery_route": None,
        "provenance_refs": [],
        "notes": "Synthetic transition-envelope fixture.",
    }


def morphism():
    return {
        "morphism_id": "industrial.transition-model.v1",
        "kind": "ESTIMATE",
        "domain_representation_id": "industrial.state-source.v1",
        "codomain_representation_id": "industrial.state-candidate.v1",
        "semantic_capability": None,
        "parameter_names": [],
        "preconditions": [],
        "validity": {
            "assumptions": ["synthetic fixture"],
            "operating_regime": ["single retained equipment state"],
            "failure_conditions": [],
        },
        "preservation": {
            "queries": ["equipment-temperature"],
            "interventions": [],
            "invariants": ["physical entity identity"],
            "approximation_tolerance": None,
        },
        "loss": {
            "class": "TASK_SPECIFIC",
            "description": "Fixture classifies identity explicitly in preservation contract.",
            "metrics": {},
        },
        "uncertainty": {"behavior": "UNKNOWN", "method": None},
        "reversibility": "UNKNOWN",
        "authority_requirements": [],
        "verification_requirements": ["physical entity identity retained"],
        "provenance_refs": [],
        "notes": "Synthetic state proposal morphism.",
    }


def registry():
    sem = semantic()
    reg = registry_from_specs(
        [
            representation("industrial.state-source.v1"),
            representation("industrial.state-candidate.v1"),
        ],
        [morphism()],
        sem,
    )
    return sem, reg


def contract_spec():
    return {
        "contract_id": "industrial.transition-preservation.v1",
        "morphism_id": "industrial.transition-model.v1",
        "requires": [],
        "effects": [{
            "property_id": "identity.physical-entity.v1",
            "effect": "PRESERVE",
            "output_property_id": "identity.physical-entity.v1",
            "transform_id": None,
            "bound": None,
            "notes": "Candidate must remain bound to the same physical entity.",
        }],
        "notes": "Synthetic transition preservation contract.",
    }


def make_state(entity="asset-17", value=300.0, execution="exec-source"):
    return state(
        identity={
            "model_id": "synthetic-equipment.v1",
            "entity_id": entity,
            "execution_id": execution,
        },
        clock={"id": "fixture-clock", "time_s": 1.0 if execution == "exec-source" else 2.0},
        frame="equipment-local",
        variables={"temperature": {"value": value, "unit": "K"}},
        provenance={
            "provider": "synthetic-fixture",
            "sources": [ref("1")],
            "semantics": "estimated",
        },
        uncertainty=None,
    )


def binding_spec():
    return {
        "binding_id": "industrial.asset-17-binding.v1",
        "canonical_entity_id": "asset-17",
        "references": [
            {
                "reference_id": "industrial.ref-cad.v1",
                "system_id": "industrial.cad-system.v1",
                "namespace": "cad-object",
                "external_id": "PUMP-17",
                "object_kind": "CAD_OBJECT",
                "evidence_ref": ref("2"),
            },
            {
                "reference_id": "industrial.ref-sensor.v1",
                "system_id": "industrial.scada-system.v1",
                "namespace": "opc-tag",
                "external_id": "PT_017",
                "object_kind": "SENSOR_TAG",
                "evidence_ref": ref("3"),
            },
            {
                "reference_id": "industrial.ref-erp.v1",
                "system_id": "industrial.erp-system.v1",
                "namespace": "equipment-master",
                "external_id": "EQ00017",
                "object_kind": "ERP_ASSET",
                "evidence_ref": ref("4"),
            },
        ],
        "notes": "Synthetic cross-system identity map.",
    }


def identity_verification_spec(binding, status_overrides=None):
    status_overrides = status_overrides or {}
    checks = []
    for index, row in enumerate(binding["references"]):
        status = status_overrides.get(row["reference_id"], "VERIFIED")
        checks.append({
            "reference_id": row["reference_id"],
            "status": status,
            "method": "DECLARED_MAPPING" if status != "UNRESOLVED" else "NOT_PERFORMED",
            "evidence_ref": ref(str((index + 5) % 10)) if status != "UNRESOLVED" else None,
            "notes": "",
        })
    return {
        "verification_id": "industrial.identity-verification.v1",
        "checks": checks,
        "notes": "Synthetic identity verification.",
    }


def preservation_objects(source, candidate, *, verification_status="VERIFIED", forbid_identity_loss=False):
    sem, reg = registry()
    contract = contract_from_spec(reg, sem, contract_spec())
    check = {
        "kind": "PRESERVE",
        "property_id": "identity.physical-entity.v1",
        "status": verification_status,
        "method": "EXACT_ALGEBRA" if verification_status != "UNRESOLVED" else "NOT_PERFORMED",
        "evidence_ref": ref("8") if verification_status != "UNRESOLVED" else None,
        "notes": "",
    }
    verification = verification_from_spec(
        reg,
        sem,
        contract,
        {
            "verification_id": "industrial.preservation-verification.v1",
            "source_state_ref": source["record_digest"],
            "candidate_state_ref": candidate["record_digest"],
            "checks": [check],
            "notes": "",
        },
    )
    gate = admission_gate_from_spec(
        reg,
        sem,
        contract,
        verification,
        {
            "gate_id": "industrial.preservation-gate.v1",
            "forbidden_forgets": ["identity.physical-entity.v1"] if forbid_identity_loss else [],
            "notes": "",
        },
    )
    return sem, reg, contract, verification, gate


def envelope_spec():
    return {
        "transition_id": "industrial.asset-17-transition.v1",
        "proposer": {
            "kind": "LLM",
            "proposer_id": "proposal-engine-fixture",
            "execution_ref": ref("9"),
            "notes": "Candidate generator only.",
        },
        "required_admission_authority": "authority.canonical-state-operator.v1",
        "notes": "Synthetic transition envelope.",
    }


def complete_fixture(identity_statuses=None, candidate_entity="asset-17", preservation_status="VERIFIED"):
    source = make_state()
    candidate = make_state(
        entity=candidate_entity,
        value=301.0,
        execution="exec-candidate",
    )
    binding = binding_from_spec(binding_spec())
    identity_verification = identity_verification_from_spec(
        binding,
        identity_verification_spec(binding, identity_statuses),
    )
    sem, reg, contract, preservation_verification, gate = preservation_objects(
        source, candidate, verification_status=preservation_status
    )
    return (
        source, candidate, binding, identity_verification,
        sem, reg, contract, preservation_verification, gate,
    )


def test_identity_binding_is_candidate_map_not_canonical_admission():
    binding = binding_from_spec(binding_spec())
    checked = validate_binding(binding)
    assert checked["canonical_entity_id"] == "asset-17"
    assert len(checked["references"]) == 3
    assert checked["claims"]["candidate_identity_map"] is True
    assert checked["claims"]["canonical_entity_created"] is False
    assert checked["claims"]["identity_admission_performed"] is False


def test_identity_binding_refuses_duplicate_external_identity():
    spec = binding_spec()
    duplicate = deepcopy(spec["references"][0])
    duplicate["reference_id"] = "industrial.ref-duplicate.v1"
    spec["references"].append(duplicate)
    with pytest.raises(ValueError, match="repeats one external system identity"):
        binding_from_spec(spec)


def test_identity_verification_requires_exact_reference_coverage():
    binding = binding_from_spec(binding_spec())
    spec = identity_verification_spec(binding)
    spec["checks"].pop()
    with pytest.raises(ValueError, match="cover every"):
        identity_verification_from_spec(binding, spec)


def test_identity_verification_aggregates_unresolved_without_admission():
    binding = binding_from_spec(binding_spec())
    value = identity_verification_from_spec(
        binding,
        identity_verification_spec(
            binding, {"industrial.ref-sensor.v1": "UNRESOLVED"}
        ),
    )
    checked = validate_identity_verification(value, binding)
    assert checked["status"] == "UNRESOLVED"
    assert checked["claims"]["identity_verification_is_not_admission"] is True


def test_identity_refutation_dominates_aggregate_status():
    binding = binding_from_spec(binding_spec())
    value = identity_verification_from_spec(
        binding,
        identity_verification_spec(
            binding, {"industrial.ref-erp.v1": "REFUTED"}
        ),
    )
    assert value["status"] == "REFUTED"


def test_transition_ready_only_for_external_authority_review():
    fixture = complete_fixture()
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    checked = validate_transition_envelope(
        value, source, candidate, binding, identity_verification,
        reg, sem, contract, verification, gate,
    )
    assert checked["readiness"] == "READY_FOR_AUTHORITY_REVIEW"
    assert checked["required_admission_authority"] == "authority.canonical-state-operator.v1"
    assert checked["claims"]["proposal_not_canonical_state"] is True
    assert checked["claims"]["state_admission_performed"] is False
    assert checked["claims"]["canonical_state_mutated"] is False


def test_candidate_entity_mismatch_is_retained_as_refused_transition():
    fixture = complete_fixture(candidate_entity="asset-99")
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    assert value["readiness"] == "REFUSED"
    assert "candidate_state_entity_differs_from_identity_binding" in value["reasons"]


def test_unresolved_cross_system_identity_keeps_transition_unresolved():
    fixture = complete_fixture(
        identity_statuses={"industrial.ref-sensor.v1": "UNRESOLVED"}
    )
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    assert value["readiness"] == "UNRESOLVED"
    assert value["reasons"] == ["cross_system_identity_unresolved"]


def test_refuted_identity_refuses_transition():
    fixture = complete_fixture(
        identity_statuses={"industrial.ref-cad.v1": "REFUTED"}
    )
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    assert value["readiness"] == "REFUSED"
    assert value["reasons"] == ["cross_system_identity_refuted"]


def test_unresolved_semantic_preservation_keeps_transition_unresolved():
    fixture = complete_fixture(preservation_status="UNRESOLVED")
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    assert value["readiness"] == "UNRESOLVED"
    assert value["reasons"] == ["semantic_preservation_unresolved"]


def test_refuted_semantic_preservation_refuses_transition():
    fixture = complete_fixture(preservation_status="REFUTED")
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    assert value["readiness"] == "REFUSED"
    assert value["reasons"] == ["semantic_preservation_refused"]


def test_preservation_receipt_must_bind_exact_source_and_candidate():
    source = make_state()
    candidate = make_state(value=301.0, execution="exec-candidate")
    different = make_state(value=302.0, execution="exec-different")
    binding = binding_from_spec(binding_spec())
    identity_verification = identity_verification_from_spec(
        binding, identity_verification_spec(binding)
    )
    sem, reg, contract, verification, gate = preservation_objects(source, different)
    with pytest.raises(ValueError, match="candidate does not match"):
        transition_envelope_from_spec(
            source, candidate, binding, identity_verification, reg, sem,
            contract, verification, gate, envelope_spec(),
        )


def test_forged_ready_status_fails_recomputed_validation():
    fixture = complete_fixture(candidate_entity="asset-99")
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = fixture
    value = transition_envelope_from_spec(
        source, candidate, binding, identity_verification, reg, sem,
        contract, verification, gate, envelope_spec(),
    )
    forged = deepcopy(value)
    forged["readiness"] = "READY_FOR_AUTHORITY_REVIEW"
    forged["reasons"] = ["identity_and_semantic_continuity_established_for_review"]
    forged.pop("record_digest")
    forged = seal(forged)
    with pytest.raises(ValueError, match="differs from recomputed"):
        validate_transition_envelope(
            forged, source, candidate, binding, identity_verification,
            reg, sem, contract, verification, gate,
        )


def test_cli_identity_and_transition_envelope(tmp_path):
    source, candidate, binding, identity_verification, sem, reg, contract, verification, gate = complete_fixture()

    binding_spec_path = tmp_path / "binding-spec.json"
    binding_spec_path.write_text(json.dumps(binding_spec()), encoding="utf-8")
    binding_path = tmp_path / "binding.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "transition", "bind-identity",
        str(binding_spec_path), "--output", str(binding_path),
    ], check=True)

    cli_binding = json.loads(binding_path.read_text(encoding="utf-8"))
    identity_spec_path = tmp_path / "identity-verification-spec.json"
    identity_spec_path.write_text(
        json.dumps(identity_verification_spec(cli_binding)), encoding="utf-8"
    )
    identity_path = tmp_path / "identity-verification.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "transition", "verify-identity",
        str(binding_path), str(identity_spec_path), "--output", str(identity_path),
    ], check=True)

    paths = {}
    for name, value in (
        ("source", source),
        ("candidate", candidate),
        ("registry", reg),
        ("contract", contract),
        ("preservation-verification", verification),
        ("preservation-gate", gate),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path

    transition_spec_path = tmp_path / "transition-spec.json"
    transition_spec_path.write_text(json.dumps(envelope_spec()), encoding="utf-8")
    envelope_path = tmp_path / "transition-envelope.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "transition", "envelope",
        str(paths["source"]),
        str(paths["candidate"]),
        str(binding_path),
        str(identity_path),
        str(paths["registry"]),
        str(paths["contract"]),
        str(paths["preservation-verification"]),
        str(paths["preservation-gate"]),
        str(transition_spec_path),
        "--output", str(envelope_path),
    ], check=True)
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert envelope["readiness"] == "READY_FOR_AUTHORITY_REVIEW"
    assert envelope["claims"]["state_admission_performed"] is False
