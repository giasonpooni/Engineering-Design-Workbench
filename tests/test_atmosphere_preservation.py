from copy import deepcopy

import pytest

from ciw.atmosphere_compiler import compile_atmosphere
from ciw.atmosphere_contract import EXPANSION_OBSERVABLES, example_request
from ciw.atmosphere_preservation import CLAIMS, MORPHISM, PROPERTY_IDS, SCHEMA, SOURCE, TARGET, build, validate
from ciw.atmosphere_verification import verify
from ciw.operations.runner import digest, seal


def fixture(request=None, result=None):
    request = example_request() if request is None else request
    result = compile_atmosphere(request) if result is None else result
    report = verify(request, result)
    return request, result, report, build(request, result, report)


@pytest.fixture(scope="module")
def qualified():
    return fixture()


def test_existing_typed_substrate_exact_content_bindings_and_loss_policy(qualified):
    request, result, report, bundle = qualified
    assert validate(bundle, request, result, report) == bundle
    assert bundle["schema"] == SCHEMA
    assert bundle["request_digest"] == digest(request)
    assert bundle["result_digest"] == result["record_digest"]
    assert bundle["report_digest"] == report["record_digest"]
    assert len({bundle[name] for name in ("request_digest", "result_digest", "report_digest")}) == 3
    assert bundle["registry"]["schema"] == "ciw.morphism-registry.v1"
    assert bundle["contract"]["schema"] == "ciw.preservation-contract.v1"
    assert bundle["verification"]["schema"] == "ciw.preservation-verification.v1"
    assert bundle["verification"]["status"] == "VERIFIED"
    assert bundle["admission_gate"]["decision"] == "ELIGIBLE"
    assert bundle["admission_gate"]["claims"]["eligibility_not_admission"] is True
    assert bundle["admission_gate"]["claims"]["state_admission_performed"] is False
    assert len({SOURCE, TARGET, MORPHISM, bundle["contract"]["contract_id"],
                bundle["verification"]["verification_id"], bundle["admission_gate"]["gate_id"]}) == 6


def test_model_to_signal_finite_profile_and_context_remain_explicit(qualified):
    request, result, report, bundle = qualified
    registry = bundle["registry"]
    assert registry["representations"][SOURCE]["role"] == "MODEL"
    assert registry["representations"][TARGET]["role"] == "SIGNAL"
    morphism = registry["morphisms"][MORPHISM]
    assert morphism["kind"] == "SIMULATE"
    assert morphism["domain_representation_id"] == SOURCE
    assert morphism["codomain_representation_id"] == TARGET
    assert morphism["semantic_capability"] is None
    assert morphism["provenance_refs"] == [digest(request), result["record_digest"], report["record_digest"]]
    assert morphism["preservation"]["interventions"] == []
    assert {"reference.context", "reference.frame", "reference.height_origin_m", "sampling.height_m",
            "profile.lapse_rate_k_per_m", "profile.wind_enu_m_per_s"} <= set(morphism["parameter_names"])
    assert registry["representations"][TARGET]["scale"]["length_m"] == 10000.0
    assert registry["representations"][TARGET]["scale"]["time_s"] is None
    assert registry["representations"][TARGET]["scale"]["resolution"] is None


def test_every_independent_check_and_local_qualification_are_gate_requirements(qualified):
    request, result, report, bundle = qualified
    aggregate = next(row for row in bundle["verification"]["checks"]
                     if row["property_id"] == "atmosphere.independent-report-acceptance.v1")
    assert len(report["checks"]) == 17
    assert all(row["name"] in aggregate["notes"] for row in report["checks"])
    assert aggregate["status"] == "VERIFIED"
    assert aggregate["method"] == "NUMERICAL_BOUND"
    assert aggregate["evidence_ref"] == report["record_digest"]
    assert "atmosphere.independent-report-acceptance.v1" in bundle["contract"]["requires"]
    assert "atmosphere.local-qualification.v1" in bundle["contract"]["requires"]
    local = next(row for row in bundle["verification"]["checks"]
                 if row["property_id"] == "atmosphere.local-qualification.v1")
    assert local["status"] == "VERIFIED"
    assert local["method"] == "EXACT_ALGEBRA"
    assert all(row["method"] != "FORMAL_PROOF" for row in bundle["verification"]["checks"])


def test_normalized_numerical_bounds_bind_each_exact_report_threshold(qualified):
    request, result, report, bundle = qualified
    effects = {row["property_id"]: row for row in bundle["contract"]["effects"]}
    reports = {row["name"]: row for row in report["checks"]}
    for name, check in (("temperature", "prescribed_temperature"), ("pressure", "cumulative_pressure_profile"),
                        ("density", "equation_of_state"), ("sound_speed", "sound_speed"),
                        ("potential_temperature", "potential_temperature"), ("wind", "prescribed_wind"),
                        ("hydrostatic_profile", "segment_hydrostatic_balance")):
        bound = effects[PROPERTY_IDS[name]]["bound"]
        assert bound["unit"] == "1"
        assert bound["upper_bound"] == reports[check]["tolerance"]
        assert reports[check]["value"] <= bound["upper_bound"]
    assert effects[PROPERTY_IDS["viscosity"]]["bound"]["upper_bound"] == request["tolerances"]["constitutive_relative"]
    assert all(row["bound"]["composition"] == "ADDITIVE_ABSOLUTE"
               for row in effects.values() if row["effect"] == "BOUND")


def test_all_omitted_physics_is_forgotten_and_cannot_become_physical_admission(qualified):
    request, result, report, bundle = qualified
    forgotten = {row["property_id"] for row in bundle["contract"]["effects"] if row["effect"] == "FORGET"}
    assert {PROPERTY_IDS[name] for name in EXPANSION_OBSERVABLES} <= forgotten
    for name in ("continuous-height-profile", "horizontal-structure", "time-evolution", "material-temperature",
                 "aerodynamic-forces", "optical-composition"):
        assert "atmosphere." + name + ".v1" in forgotten
    assert bundle["claims"] == CLAIMS
    for name in ("physical_validation_established", "weather_forecast_established", "wind_dynamics_established",
                 "material_conditioning_established", "visual_scattering_established",
                 "cross_scale_commutative_witness_supplied", "canonical_state_mutated",
                 "state_admission_performed", "execution_authority"):
        assert bundle["claims"][name] is False
    for row in bundle["verification"]["checks"]:
        if row["kind"] == "FORGET":
            assert row["status"] == "VERIFIED"
            assert row["method"] == "EXACT_ALGEBRA"
            assert row["evidence_ref"] == result["record_digest"]


@pytest.mark.parametrize("observable", sorted(EXPANSION_OBSERVABLES))
def test_each_unrepresented_query_expands_and_refuses_typed_gate(observable):
    request = example_request()
    request["desired_observables"].append(observable)
    request, result, report, bundle = fixture(request)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "EXPAND"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert PROPERTY_IDS[observable] in bundle["admission_gate"]["forbidden_forgets"]
    assert bundle["admission_gate"]["policy_violations"] == [PROPERTY_IDS[observable]]
    assert validate(bundle, request, result, report) == bundle


def test_quadrature_failure_refuses_eligibility_even_with_exact_compiler_properties():
    request = example_request()
    request["sampling"]["height_m"] = [0.0, 11000.0]
    request["profile"]["lapse_rate_k_per_m"] = 0.009
    request["tolerances"]["quadrature_relative"] = 1e-12
    request, result, report, bundle = fixture(request)
    failed = [row["name"] for row in report["checks"] if row["status"] == "FAIL"]
    assert failed == ["quadrature_refinement"]
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("field", ["temperature_k", "pressure_pa", "density_kg_per_m3", "sound_speed_m_per_s",
                                  "dynamic_viscosity_pa_s", "kinematic_viscosity_m2_per_s", "potential_temperature_k",
                                  "wind_enu_m_per_s"])
def test_corrupt_finite_profile_properties_cannot_retain_local_gate(field):
    request = example_request()
    result = compile_atmosphere(request)
    if field == "wind_enu_m_per_s":
        result["profile"][field][5][0] += 1.0
    else:
        result["profile"][field][5] *= 1.01
    seal(result)
    request, result, report, bundle = fixture(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("mutation", ["bound", "receipt_ref", "receipt_status", "obligation", "claim",
                                     "claim_alias", "request_ref", "report_ref", "parameter", "local_requirement"])
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
        altered["claims"]["physical_validation_established"] = True
    elif mutation == "claim_alias":
        altered["claims"]["execution_authority"] = 0
    elif mutation == "request_ref":
        altered["request_digest"] = result["record_digest"]
    elif mutation == "report_ref":
        altered["report_digest"] = result["record_digest"]
    elif mutation == "parameter":
        altered["registry"]["morphisms"][MORPHISM]["parameter_names"].remove("reference.context")
    elif mutation == "local_requirement":
        altered["contract"]["requires"].remove("atmosphere.local-qualification.v1")
    for name in ("registry", "contract", "verification", "admission_gate"):
        seal(altered[name])
    seal(altered)
    with pytest.raises(ValueError):
        validate(altered, request, result, report)


@pytest.mark.parametrize("part", ["request", "result", "report"])
def test_changed_source_cannot_rebind_receipt(qualified, part):
    request, result, report, bundle = deepcopy(qualified)
    if part == "request":
        request["reference"]["context"]["source_ref"] += ".changed"
    elif part == "result":
        result["profile"]["temperature_k"][5] += 0.01
        seal(result)
    else:
        report["metrics"]["residuals"]["equation_of_state"] += 0.01
        seal(report)
    with pytest.raises(ValueError):
        validate(bundle, request, result, report)


def test_retained_build_and_validation_do_not_replay_compiler_or_quadrature(qualified, monkeypatch):
    request, result, report, bundle = qualified

    def forbidden(*args, **kwargs):
        raise AssertionError("retained typed receipts must not execute a numerical engine")

    import ciw.atmosphere_compiler as compiler
    import ciw.atmosphere_verification as verifier
    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    for name in ("verify", "_integrate_segment", "_quadrature_reference", "_residuals"):
        monkeypatch.setattr(verifier, name, forbidden)
    assert build(request, result, report) == bundle
    assert validate(bundle, request, result, report) == bundle


def test_wrong_property_units_cannot_receive_preservation_receipts(qualified):
    request, result, report, bundle = qualified
    malformed = deepcopy(result)
    malformed["units"]["dynamic_viscosity_pa_s"] = "m^2/s"
    seal(malformed)
    with pytest.raises(ValueError):
        build(request, malformed, report)
