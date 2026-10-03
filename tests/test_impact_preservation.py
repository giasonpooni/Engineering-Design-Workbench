from copy import deepcopy

import pytest

from ciw.impact_contract import EXPANSION_OBSERVABLES, example_request
from ciw.impact_preservation import PROPERTY_IDS, build, validate
from ciw.impact_solver import simulate
from ciw.impact_verification import verify
from ciw.operations.runner import digest, seal


def fixture(request=None):
    request = example_request() if request is None else request
    result = simulate(request)
    report = verify(request, result)
    return request, result, report, build(request, result, report)


def test_bridge_uses_existing_typed_contract_and_exact_content_bindings():
    request, result, report, bundle = fixture()
    assert validate(bundle, request, result, report) == bundle
    assert bundle["request_digest"] == digest(request)
    assert bundle["result_digest"] == result["record_digest"]
    assert bundle["report_digest"] == report["record_digest"]
    assert bundle["registry"]["schema"] == "ciw.morphism-registry.v1"
    assert bundle["contract"]["schema"] == "ciw.preservation-contract.v1"
    assert bundle["verification"]["schema"] == "ciw.preservation-verification.v1"
    assert bundle["verification"]["source_state_ref"] == digest(request)
    assert bundle["verification"]["candidate_state_ref"] == result["record_digest"]
    assert bundle["verification"]["status"] == "VERIFIED"
    assert bundle["admission_gate"]["decision"] == "ELIGIBLE"
    assert bundle["admission_gate"]["claims"]["state_admission_performed"] is False
    assert bundle["claims"]["physical_validation_established"] is False
    assert bundle["claims"]["scale_preservation_established"] is False
    assert bundle["claims"]["cross_scale_commutative_witness_supplied"] is False
    morphism = next(iter(bundle["registry"]["morphisms"].values()))
    assert morphism["kind"] == "SIMULATE"
    assert morphism["semantic_capability"] is None
    assert morphism["preservation"]["interventions"] == []


def test_absolute_bounds_convert_normalized_tolerances_using_matching_si_scales():
    request = example_request()
    request["model"].update(mass_kg=2.0, stiffness_n_per_m=40000.0, initial_speed_m_per_s=3.0)
    request, result, report, bundle = fixture(request)
    effects = {effect["property_id"]: effect for effect in bundle["contract"]["effects"]}
    cases = [
        ("force_time", "analytic_normalized", "peak_force_n", "N"),
        ("impulse", "impulse_relative", "support_impulse_n_s", "N*s"),
        ("energy_accounting", "energy_relative", "initial_energy_j", "J"),
        ("separation_time", "separation_relative", "contact_duration_s", "s"),
    ]
    for observable, tolerance, reference, unit in cases:
        effect = effects[PROPERTY_IDS[observable]]
        assert effect["effect"] == "BOUND"
        assert effect["bound"]["unit"] == unit
        assert effect["bound"]["upper_bound"] == request["tolerances"][tolerance] * report["reference"][reference]
    assert effects[PROPERTY_IDS["restitution"]]["bound"]["upper_bound"] == request["tolerances"]["restitution_absolute"]
    assert effects[PROPERTY_IDS["restitution"]]["bound"]["unit"] == "1"
    numerical = [check for check in bundle["verification"]["checks"] if check["kind"] == "BOUND"]
    assert all(check["method"] == "NUMERICAL_BOUND" for check in numerical)
    assert all(check["evidence_ref"] == report["record_digest"] for check in numerical)


def test_numerical_failure_produces_refuted_receipt_and_refused_gate():
    request = example_request()
    request["integration"]["steps_per_contact"] = 16
    request, result, report, bundle = fixture(request)
    assert report["status"] == "FAIL"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert "preservation_verification_refuted" in bundle["admission_gate"]["reasons"]
    force_check = next(check for check in bundle["verification"]["checks"]
                       if check["property_id"] == PROPERTY_IDS["force_time"])
    assert force_check["status"] == "REFUTED"
    assert force_check["method"] == "NUMERICAL_BOUND"
    assert validate(bundle, request, result, report) == bundle


def test_unsupported_requested_properties_are_explicit_policy_forgets():
    request = example_request()
    request["desired_observables"] += ["plate_deformation", "damage", "molecular_response", "scale_preservation"]
    request, result, report, bundle = fixture(request)
    assert report["qualification"]["action"] == "EXPAND"
    assert bundle["verification"]["status"] == "VERIFIED"
    gate = bundle["admission_gate"]
    assert gate["decision"] == "REFUSED"
    expected = sorted(PROPERTY_IDS[name] for name in request["desired_observables"] if name in EXPANSION_OBSERVABLES)
    assert gate["forbidden_forgets"] == expected
    assert gate["policy_violations"] == expected
    forgotten = {effect["property_id"] for effect in bundle["contract"]["effects"] if effect["effect"] == "FORGET"}
    assert forgotten == {PROPERTY_IDS[name] for name in EXPANSION_OBSERVABLES}
    forget_checks = [check for check in bundle["verification"]["checks"] if check["kind"] == "FORGET"]
    assert all(check["method"] == "EXACT_ALGEBRA" for check in forget_checks)
    assert all(check["evidence_ref"] == result["record_digest"] for check in forget_checks)
    assert validate(bundle, request, result, report) == bundle


def test_resealed_threshold_or_obligation_tampering_is_rejected():
    request, result, report, bundle = fixture()
    altered = deepcopy(bundle)
    altered["contract"]["effects"][0]["bound"]["upper_bound"] *= 2
    seal(altered["contract"])
    seal(altered)
    with pytest.raises(ValueError):
        validate(altered, request, result, report)

    # The report itself remains unchanged; rewiring a receipt to another valid
    # request is rejected even when the attacker freshly seals every outer row.
    changed = deepcopy(request)
    changed["model"]["mass_kg"] *= 2
    with pytest.raises(ValueError):
        validate(bundle, changed, result, report)


def test_structural_validation_does_not_execute_numerical_engines(monkeypatch):
    request, result, report, bundle = fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("retained preservation validation must not execute numerical engines")

    monkeypatch.setattr("ciw.impact_solver.simulate", forbidden)
    monkeypatch.setattr("ciw.impact_verification.verify", forbidden)
    monkeypatch.setattr("ciw.impact_reference.reference_values", forbidden)
    assert validate(bundle, request, result, report) == bundle
    assert build(request, result, report) == bundle


def test_malformed_result_cannot_receive_typed_preservation_bridge():
    request, result, report, bundle = fixture()
    malformed = deepcopy(result)
    malformed["units"]["force_n"] = "Pa"
    seal(malformed)
    rejection = verify(request, malformed)
    assert rejection["status"] == "FAIL"
    with pytest.raises(ValueError):
        build(request, malformed, rejection)
