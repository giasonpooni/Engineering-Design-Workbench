from copy import deepcopy

import pytest

from ciw.impact_plate_contract import EXPANSION_OBSERVABLES, MODEL_FIELDS, example_request
from ciw.impact_plate_preservation import (
    CLAIMS, MORPHISM, PROPERTY_IDS, SCHEMA, SOURCE, TARGET, TRACE_LABELS, build, validate,
)
from ciw.impact_plate_solver import simulate
from ciw.impact_plate_verification import verify
from ciw.operations.runner import digest, seal


def fixture(request=None):
    request = example_request() if request is None else request
    result = simulate(request)
    report = verify(request, result)
    return request, result, report, build(request, result, report)


@pytest.fixture(scope="module")
def qualified():
    return fixture()


def test_existing_typed_substrate_and_exact_identity_bindings(qualified):
    request, result, report, bundle = qualified
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    assert validate(bundle, request, result, report) == bundle
    assert bundle["schema"] == SCHEMA
    assert bundle["request_digest"] == digest(request)
    assert bundle["result_digest"] == result["record_digest"]
    assert bundle["report_digest"] == report["record_digest"]
    assert len({bundle[name] for name in ("request_digest", "result_digest", "report_digest")}) == 3
    assert bundle["registry"]["schema"] == "ciw.morphism-registry.v1"
    assert bundle["contract"]["schema"] == "ciw.preservation-contract.v1"
    assert bundle["verification"]["schema"] == "ciw.preservation-verification.v1"
    assert bundle["verification"]["source_state_ref"] == digest(request)
    assert bundle["verification"]["candidate_state_ref"] == result["record_digest"]
    assert bundle["verification"]["status"] == "VERIFIED"
    assert bundle["admission_gate"]["decision"] == "ELIGIBLE"
    assert bundle["admission_gate"]["claims"]["state_admission_performed"] is False
    assert len({SOURCE, TARGET, MORPHISM, bundle["contract"]["contract_id"],
                bundle["verification"]["verification_id"], bundle["admission_gate"]["gate_id"]}) == 6


def test_declared_geometry_and_contact_parameter_handoff_is_bound(qualified):
    request, result, report, bundle = qualified
    morphism = bundle["registry"]["morphisms"][MORPHISM]
    assert morphism["kind"] == "SIMULATE"
    assert morphism["semantic_capability"] is None
    assert morphism["domain_representation_id"] == SOURCE
    assert morphism["codomain_representation_id"] == TARGET
    assert MODEL_FIELDS <= set(morphism["parameter_names"])
    assert {"modes_per_axis", "spatial_refinement_increment", "steps_per_contact"} <= set(morphism["parameter_names"])
    assert morphism["preservation"]["interventions"] == []
    assert morphism["provenance_refs"] == [digest(request), result["record_digest"], report["record_digest"]]
    for name in ("length_x_m", "thickness_m", "young_modulus_pa", "patch_center_x_m", "patch_width_y_m"):
        changed = deepcopy(request)
        changed["model"][name] *= 1.01
        with pytest.raises(ValueError):
            validate(bundle, changed, result, report)


def test_claims_protect_finite_model_and_evidence_authority_limits(qualified):
    request, result, report, bundle = qualified
    assert bundle["claims"] == CLAIMS
    for claim, value in CLAIMS.items():
        if claim not in {"uses_existing_preservation_contracts", "synthetic_numerical_scope_only"}:
            assert value is False
    assert CLAIMS["total_striker_plate_momentum_conservation_established"] is False
    assert CLAIMS["continuum_convergence_established"] is False
    assert CLAIMS["cross_scale_commutative_witness_supplied"] is False
    assert CLAIMS["state_admission_performed"] is False
    assert CLAIMS["physical_validation_established"] is False
    momentum = next(effect for effect in bundle["contract"]["effects"]
                    if effect["property_id"] == "impact.plate-striker-momentum-balance.v1")
    assert momentum["bound"]["metric"] == "maximum_absolute_striker_momentum_residual"
    assert all("support-impulse" not in effect["property_id"] for effect in bundle["contract"]["effects"])


def test_primary_refined_and_spatial_evidence_all_bind_to_report(qualified):
    request, result, report, bundle = qualified
    checks = {row["property_id"]: row for row in bundle["verification"]["checks"]}
    assert result["primary"]["modes_per_axis"] == result["refined"]["modes_per_axis"]
    assert result["spatial"]["modes_per_axis"] == result["primary"]["modes_per_axis"] + 2
    assert result["refined"]["dt_s"] == result["spatial"]["dt_s"] == result["primary"]["dt_s"] / 2
    for property_id, families in (
        (PROPERTY_IDS["force_time"], ("analytic.force_n",)),
        (PROPERTY_IDS["plate_modes"], ("analytic.modal_displacement_m", "analytic.modal_velocity_m_per_s")),
        (PROPERTY_IDS["energy_accounting"], ("maximum_energy_drift",)),
        ("impact.plate-recorded-linear-regime.v1", ("small_deflection_ratio", "small_slope_bound")),
        ("impact.plate-first-release-single-contact.v1", ("separation_event", "single_contact")),
    ):
        check = checks[property_id]
        for label in TRACE_LABELS:
            for family in families:
                assert label + "." + family in check["notes"]
        assert check["evidence_ref"] == report["record_digest"]
        assert check["status"] == "VERIFIED"
        assert check["method"] == "NUMERICAL_BOUND"
    assert "time_refinement." in checks["impact.plate-timestep-refinement.v1"]["notes"]
    assert "spatial_refinement." in checks["impact.plate-spatial-refinement.v1"]["notes"]
    for prefix, identity in (("time_refinement", "impact.plate-timestep-refinement.v1"),
                             ("spatial_refinement", "impact.plate-spatial-refinement.v1")):
        for name in ("modal_displacement_m", "modal_velocity_m_per_s", "displacement_field_bound"):
            assert prefix + "." + name in checks[identity]["notes"]
    assert all(check["evidence_ref"] == report["record_digest"]
               for check in checks.values() if check["kind"] in {"REQUIRE", "BOUND"})


def test_si_error_bounds_use_exact_nominal_report_scales(qualified):
    request, result, report, bundle = qualified
    effects = {effect["property_id"]: effect for effect in bundle["contract"]["effects"]}
    scales = report["reference"]["scales"]
    states = report["reference"]["state_normalizations"]
    state_cases = [
        ("impact.plate-striker-displacement-history.v1", "striker_displacement_m", "m"),
        ("impact.plate-striker-velocity-history.v1", "velocity_m_per_s", "m/s"),
        (PROPERTY_IDS["force_time"], "force_n", "N"),
        (PROPERTY_IDS["plate_deformation"], "plate_contact_displacement_m", "m"),
        ("impact.plate-patch-velocity-history.v1", "plate_contact_velocity_m_per_s", "m/s"),
        ("impact.plate-modal-displacement-history.v1", "modal_displacement_m", "m"),
        ("impact.plate-modal-velocity-history.v1", "modal_velocity_m_per_s", "m/s"),
    ]
    for identity, field, unit in state_cases:
        bound = effects[identity]["bound"]
        assert bound["unit"] == unit
        assert bound["upper_bound"] == request["tolerances"]["analytic_normalized"] * max(
            states[label][field] for label in ("primary", "spatial"))
    cases = [
        (PROPERTY_IDS["impulse"], "impulse_relative", "impulse_n_s", "N*s"),
        ("impact.plate-striker-momentum-balance.v1", "momentum_relative", "impulse_n_s", "N*s"),
        (PROPERTY_IDS["energy_accounting"], "energy_relative", "energy_j", "J"),
        (PROPERTY_IDS["separation_time"], "separation_relative", "time_s", "s"),
    ]
    for identity, tolerance, scale_name, unit in cases:
        effect = effects[identity]
        assert effect["effect"] == "BOUND"
        assert effect["bound"]["unit"] == unit
        assert effect["bound"]["upper_bound"] == request["tolerances"][tolerance] * scales[scale_name]
    assert effects[PROPERTY_IDS["plate_modes"]]["bound"]["unit"] == "1"
    assert effects["impact.plate-timestep-refinement.v1"]["bound"]["upper_bound"] == request["tolerances"]["refinement_normalized"]
    assert effects["impact.plate-spatial-refinement.v1"]["bound"]["upper_bound"] == request["tolerances"]["spatial_refinement_normalized"]


def test_retained_finite_displacement_field_refinement_bounds_have_si_receipts(qualified):
    request, result, report, bundle = qualified
    effects = {effect["property_id"]: effect for effect in bundle["contract"]["effects"]}
    receipts = {check["property_id"]: check for check in bundle["verification"]["checks"]}
    for prefix, identity, tolerance in (
        ("time_refinement", "impact.plate-timestep-displacement-field.v1", "refinement_normalized"),
        ("spatial_refinement", "impact.plate-spatial-displacement-field.v1", "spatial_refinement_normalized"),
    ):
        effect, receipt = effects[identity], receipts[identity]
        normalized = report["metrics"][prefix]["aligned_state_changes_normalized"]["displacement_field_bound"]
        scale = report["reference"]["scales"]["displacement_m"]
        assert effect["effect"] == "BOUND"
        assert effect["bound"]["unit"] == "m"
        assert effect["bound"]["upper_bound"] == request["tolerances"][tolerance] * scale
        assert normalized * scale <= effect["bound"]["upper_bound"]
        assert receipt["kind"] == "BOUND"
        assert receipt["status"] == "VERIFIED"
        assert receipt["method"] == "NUMERICAL_BOUND"
        assert receipt["evidence_ref"] == report["record_digest"]
        assert receipt["notes"] == "Exact retained report checks: " + prefix + ".displacement_field_bound"
    assert CLAIMS["continuum_convergence_established"] is False


def test_small_deflection_and_slope_are_gate_requirements_for_every_trace(qualified):
    request, result, report, bundle = qualified
    selected = {row["name"]: row for row in report["checks"]}
    for label in TRACE_LABELS:
        for family in ("small_deflection_ratio", "small_slope_bound"):
            check = selected[label + "." + family]
            assert check["tolerance"] == 0.1
            assert check["value"] <= 0.1
    assert "impact.plate-recorded-linear-regime.v1" in bundle["contract"]["requires"]


def test_all_canonical_report_checks_are_required_without_claiming_formal_proof(qualified):
    request, result, report, bundle = qualified
    aggregate = next(check for check in bundle["verification"]["checks"]
                     if check["property_id"] == "impact.plate-independent-report-acceptance.v1")
    names = [row["name"] for row in report["checks"] if row["name"] != "schema_integrity"]
    assert aggregate["status"] == "VERIFIED"
    assert aggregate["method"] == "NUMERICAL_BOUND"
    assert digest(names) in aggregate["notes"] or all(name in aggregate["notes"] for name in names)
    assert aggregate["evidence_ref"] == report["record_digest"]
    assert all(row["method"] != "FORMAL_PROOF" for row in bundle["verification"]["checks"])


def test_requested_unrepresented_physical_quantities_expand_and_refuse_typed_gate():
    request = example_request()
    # Seven supported plus nine unsupported fits the strict observable budget.
    wanted = ["stress", "strain", "plastic_work", "rate_response", "thermal_response",
              "hardness", "fracture", "molecular_response", "scale_preservation"]
    request["desired_observables"] += wanted
    request, result, report, bundle = fixture(request)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "EXPAND"
    assert bundle["verification"]["status"] == "VERIFIED"
    gate = bundle["admission_gate"]
    assert gate["decision"] == "REFUSED"
    expected = sorted(PROPERTY_IDS[name] for name in wanted)
    assert gate["forbidden_forgets"] == expected
    assert gate["policy_violations"] == expected
    forgotten = {effect["property_id"] for effect in bundle["contract"]["effects"] if effect["effect"] == "FORGET"}
    assert forgotten == {PROPERTY_IDS[name] for name in EXPANSION_OBSERVABLES}
    for row in bundle["verification"]["checks"]:
        if row["kind"] == "FORGET":
            assert row["method"] == "EXACT_ALGEBRA"
            assert row["evidence_ref"] == result["record_digest"]
    assert validate(bundle, request, result, report) == bundle


def test_numerical_failure_refutes_receipt_and_refuses_gate():
    request = example_request()
    request["tolerances"]["analytic_normalized"] = 1e-12
    request, result, report, bundle = fixture(request)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert "preservation_verification_refuted" in bundle["admission_gate"]["reasons"]
    assert validate(bundle, request, result, report) == bundle


def test_exceeding_recorded_linear_regime_refuses_even_an_elastic_numerical_path():
    request = example_request()
    request["model"]["initial_speed_m_per_s"] = 3.0
    request, result, report, bundle = fixture(request)
    guards = [row for row in report["checks"]
              if row["name"].endswith((".small_deflection_ratio", ".small_slope_bound"))]
    assert any(row["status"] == "FAIL" for row in guards)
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("mutation", ["bound", "receipt_ref", "receipt_status", "obligation", "claim", "result_ref", "source_geometry", "spatial_requirement", "field_refinement_bound"])
def test_resealed_receipt_corruption_is_rejected(qualified, mutation):
    request, result, report, bundle = qualified
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
        altered["claims"]["continuum_convergence_established"] = True
    elif mutation == "result_ref":
        altered["result_digest"] = digest(request)
    elif mutation == "source_geometry":
        altered["registry"]["morphisms"][MORPHISM]["parameter_names"].remove("thickness_m")
    elif mutation == "spatial_requirement":
        selected = next(row for row in altered["verification"]["checks"]
                        if row["property_id"] == "impact.plate-recorded-linear-regime.v1")
        selected["notes"] = selected["notes"].replace("spatial.small_deflection_ratio", "primary.small_deflection_ratio")
    elif mutation == "field_refinement_bound":
        selected = next(row for row in altered["contract"]["effects"]
                        if row["property_id"] == "impact.plate-spatial-displacement-field.v1")
        selected["bound"]["upper_bound"] *= 2
    for name in ("registry", "contract", "verification", "admission_gate"):
        seal(altered[name])
    seal(altered)
    with pytest.raises(ValueError):
        validate(altered, request, result, report)


@pytest.mark.parametrize("label", TRACE_LABELS)
def test_changed_trace_cannot_rebind_retained_report(qualified, label):
    request, result, report, bundle = qualified
    changed = deepcopy(result)
    changed[label]["modal_displacement_m"][0][20] += 1e-7
    seal(changed)
    with pytest.raises(ValueError):
        validate(bundle, request, changed, report)


def test_retained_build_and_validation_do_not_execute_numerical_engines(qualified, monkeypatch):
    request, result, report, bundle = qualified

    def forbidden(*args, **kwargs):
        raise AssertionError("retained preservation must not execute numerical engines")

    import ciw.impact_plate_reference as reference
    import ciw.impact_plate_solver as solver
    import ciw.impact_plate_verification as verification
    import numpy as np

    monkeypatch.setattr(solver, "simulate", forbidden)
    monkeypatch.setattr(verification, "verify", forbidden)
    monkeypatch.setattr(verification, "_metrics", forbidden)
    monkeypatch.setattr(verification, "reference", forbidden)
    monkeypatch.setattr(verification, "reference_values", forbidden)
    monkeypatch.setattr(np.linalg, "eigh", forbidden)
    # Propagation names may evolve, but any callable public numerical entry
    # point in the fixed installed reference must remain unused on inspection.
    for name in ("reference", "reference_values", "sample", "spectral_reference"):
        if hasattr(reference, name):
            monkeypatch.setattr(reference, name, forbidden)
    assert validate(bundle, request, result, report) == bundle
    assert build(request, result, report) == bundle


def test_wrong_modal_units_cannot_receive_a_preservation_bundle(qualified):
    request, result, report, bundle = qualified
    malformed = deepcopy(result)
    malformed["units"]["modal_displacement_m"] = "Pa"
    seal(malformed)
    with pytest.raises(ValueError):
        build(request, malformed, report)


def test_enlarged_basis_cannot_be_relabelled_as_time_refinement(qualified):
    request, result, report, bundle = qualified
    malformed = deepcopy(result)
    malformed["refined"], malformed["spatial"] = malformed["spatial"], malformed["refined"]
    seal(malformed)
    with pytest.raises(ValueError):
        build(request, malformed, report)
