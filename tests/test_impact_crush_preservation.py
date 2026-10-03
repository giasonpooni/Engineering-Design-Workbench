from copy import deepcopy

import pytest

from ciw.impact_crush_contract import EXPANSION_OBSERVABLES, example_request
from ciw.impact_crush_preservation import CLAIMS, PROPERTY_IDS, build, validate
from ciw.impact_crush_solver import simulate
from ciw.impact_crush_verification import verify
from ciw.operations.runner import digest, seal


def fixture(request=None):
    request = example_request() if request is None else request
    result = simulate(request)
    report = verify(request, result)
    return request, result, report, build(request, result, report)


@pytest.fixture(scope="module")
def yielding():
    return fixture()


def test_exact_binding_existing_typed_substrate_and_narrow_claims(yielding):
    request, result, report, bundle = yielding
    assert report["status"] == "PASS"
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
    assert bundle["claims"] == CLAIMS
    for claim in ("physical_validation_established", "hardness_established", "material_damage_established",
                  "molecular_response_established", "scale_preservation_established",
                  "cross_scale_commutative_witness_supplied", "canonical_state_mutated",
                  "state_admission_performed", "execution_authority"):
        assert bundle["claims"][claim] is False
    morphism = next(iter(bundle["registry"]["morphisms"].values()))
    assert morphism["kind"] == "SIMULATE"
    assert morphism["semantic_capability"] is None
    assert morphism["preservation"]["interventions"] == []
    assert "yield_force_n" in morphism["parameter_names"]


def test_yielding_work_energy_and_residual_receipts_bind_exact_checks(yielding):
    request, result, report, bundle = yielding
    reference = report["reference"]
    assert reference["branch"] == "plastic"
    assert reference["plastic_work_j"] == pytest.approx(1.5)
    assert reference["rebound_energy_j"] == pytest.approx(0.5)
    assert reference["initial_energy_j"] == pytest.approx(2.0)
    assert reference["residual_compression_m"] == pytest.approx(0.015)
    checks = {check["property_id"]: check for check in bundle["verification"]["checks"]}
    assert "primary.maximum_energy_drift" in checks[PROPERTY_IDS["energy_accounting"]]["notes"]
    assert "refined.maximum_energy_drift" in checks[PROPERTY_IDS["energy_accounting"]]["notes"]
    assert "primary.plastic_work" in checks[PROPERTY_IDS["plastic_work"]]["notes"]
    assert "refined.residual_compression" in checks[PROPERTY_IDS["residual_compression"]]["notes"]
    assert "rebound_energy_loss" in checks["impact.crush-rebound-energy-loss.v1"]["notes"]
    plastic_requirement = checks["impact.crush-plastic-state-law.v1"]
    for label in ("primary", "refined"):
        for name in ("plastic_nonnegative", "plastic_monotonic", "return_mapping", "plastic_work_algebra", "yield_branch"):
            assert label + "." + name in plastic_requirement["notes"]
    assert all(check["evidence_ref"] == report["record_digest"]
               for check in checks.values() if check["kind"] in {"REQUIRE", "BOUND"})


def test_five_history_bounds_and_aggregate_bounds_use_matching_si_normalizations(yielding):
    request, result, report, bundle = yielding
    effects = {effect["property_id"]: effect for effect in bundle["contract"]["effects"]}
    reference = report["reference"]
    cases = [
        ("impact.crush-compression-history.v1", "analytic_normalized", reference["maximum_compression_m"], "m"),
        ("impact.crush-velocity-history.v1", "analytic_normalized", request["model"]["initial_speed_m_per_s"], "m/s"),
        (PROPERTY_IDS["force_time"], "analytic_normalized", reference["peak_force_n"], "N"),
        ("impact.crush-plastic-compression-history.v1", "analytic_normalized", reference["maximum_compression_m"], "m"),
        ("impact.crush-plastic-work-history.v1", "analytic_normalized", reference["initial_energy_j"], "J"),
        (PROPERTY_IDS["impulse"], "impulse_relative", reference["support_impulse_n_s"], "N*s"),
        (PROPERTY_IDS["energy_accounting"], "energy_relative", reference["initial_energy_j"], "J"),
        (PROPERTY_IDS["plastic_work"], "analytic_normalized", reference["initial_energy_j"], "J"),
        (PROPERTY_IDS["residual_compression"], "analytic_normalized", reference["maximum_compression_m"], "m"),
        (PROPERTY_IDS["restitution"], "restitution_absolute", 1.0, "1"),
        (PROPERTY_IDS["separation_time"], "separation_relative", reference["contact_duration_s"], "s"),
    ]
    for identity, tolerance, normalization, unit in cases:
        effect = effects[identity]
        assert effect["effect"] == "BOUND"
        assert effect["bound"]["unit"] == unit
        assert effect["bound"]["upper_bound"] == request["tolerances"][tolerance] * normalization
    assert all(check["method"] == "NUMERICAL_BOUND"
               for check in bundle["verification"]["checks"] if check["kind"] == "BOUND")
    refinement = next(check for check in bundle["verification"]["checks"]
                      if check["property_id"] == "impact.crush-timestep-refinement.v1")
    assert "refinement.plastic_compression_m" in refinement["notes"]
    assert "refinement.plastic_work_j" in refinement["notes"]
    assert "refinement.residual_compression" in refinement["notes"]


def test_elastic_branch_zero_plastic_state_has_finite_nonzero_receipt_bounds():
    request = example_request()
    request["model"]["yield_force_n"] = 400.0
    request, result, report, bundle = fixture(request)
    assert report["status"] == "PASS"
    assert report["reference"]["branch"] == "elastic"
    for label in ("primary", "refined"):
        assert set(result[label]["plastic_compression_m"]) == {0.0}
        assert set(result[label]["plastic_work_j"]) == {0.0}
    effects = {effect["property_id"]: effect for effect in bundle["contract"]["effects"]}
    assert effects[PROPERTY_IDS["plastic_work"]]["bound"]["upper_bound"] > 0
    assert effects[PROPERTY_IDS["residual_compression"]]["bound"]["upper_bound"] > 0
    assert bundle["verification"]["status"] == "VERIFIED"
    assert bundle["admission_gate"]["decision"] == "ELIGIBLE"
    assert validate(bundle, request, result, report) == bundle


def test_unsupported_physical_observables_expand_but_forbid_typed_admission():
    request = example_request()
    request["desired_observables"] += ["plate_deformation", "rate_response", "thermal_response", "damage", "fracture", "hardness", "molecular_response"]
    request, result, report, bundle = fixture(request)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "EXPAND"
    assert bundle["verification"]["status"] == "VERIFIED"
    gate = bundle["admission_gate"]
    assert gate["decision"] == "REFUSED"
    expected = sorted(PROPERTY_IDS[name] for name in request["desired_observables"] if name in EXPANSION_OBSERVABLES)
    assert gate["forbidden_forgets"] == expected
    assert gate["policy_violations"] == expected
    forgotten = {effect["property_id"] for effect in bundle["contract"]["effects"] if effect["effect"] == "FORGET"}
    assert forgotten == {PROPERTY_IDS[name] for name in EXPANSION_OBSERVABLES}
    for check in bundle["verification"]["checks"]:
        if check["kind"] == "FORGET":
            assert check["method"] == "EXACT_ALGEBRA"
            assert check["evidence_ref"] == result["record_digest"]
    assert validate(bundle, request, result, report) == bundle


def test_numerical_failure_refutes_receipt_and_refuses_gate():
    request = example_request()
    request["integration"]["steps_per_contact"] = 32
    request, result, report, bundle = fixture(request)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert "preservation_verification_refuted" in bundle["admission_gate"]["reasons"]
    assert any(check["status"] == "REFUTED" for check in bundle["verification"]["checks"])
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("mutation", ["bound", "receipt_ref", "receipt_status", "obligation", "claim", "result_ref"])
def test_resealed_receipt_corruption_is_rejected(yielding, mutation):
    request, result, report, bundle = yielding
    altered = deepcopy(bundle)
    if mutation == "bound":
        altered["contract"]["effects"][0]["bound"]["upper_bound"] *= 2
    elif mutation == "receipt_ref":
        altered["verification"]["checks"][0]["evidence_ref"] = result["record_digest"]
    elif mutation == "receipt_status":
        altered["verification"]["checks"][0]["status"] = "REFUTED"
    elif mutation == "obligation":
        altered["verification"]["checks"].pop()
    elif mutation == "claim":
        altered["claims"]["physical_validation_established"] = True
    elif mutation == "result_ref":
        altered["result_digest"] = digest(request)
    for name in ("contract", "verification", "admission_gate"):
        seal(altered[name])
    seal(altered)
    with pytest.raises(ValueError):
        validate(altered, request, result, report)


def test_retained_build_and_validation_do_not_execute_numerical_engines(yielding, monkeypatch):
    request, result, report, bundle = yielding

    def forbidden(*args, **kwargs):
        raise AssertionError("retained preservation inspection must not execute numerical engines")

    monkeypatch.setattr("ciw.impact_crush_solver.simulate", forbidden)
    monkeypatch.setattr("ciw.impact_crush_verification.verify", forbidden)
    monkeypatch.setattr("ciw.impact_crush_verification.reference_values", forbidden)
    monkeypatch.setattr("ciw.impact_crush_verification._metrics", forbidden)
    monkeypatch.setattr("ciw.impact_crush_reference.sample", forbidden)
    monkeypatch.setattr("ciw.impact_crush_reference.reference_values", forbidden)
    assert validate(bundle, request, result, report) == bundle
    assert build(request, result, report) == bundle


def test_changed_yield_force_cannot_rebind_retained_evidence(yielding):
    request, result, report, bundle = yielding
    changed = deepcopy(request)
    changed["model"]["yield_force_n"] *= 1.1
    with pytest.raises(ValueError):
        validate(bundle, changed, result, report)


def test_wrong_plastic_work_units_cannot_receive_preservation_bundle(yielding):
    request, result, report, bundle = yielding
    malformed = deepcopy(result)
    malformed["units"]["plastic_work_j"] = "Pa"
    seal(malformed)
    rejection = verify(request, malformed)
    assert rejection["status"] == "FAIL"
    with pytest.raises(ValueError):
        build(request, malformed, rejection)
