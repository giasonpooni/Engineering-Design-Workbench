from copy import deepcopy

import pytest

from ciw.atmosphere_moist_compiler import compile_atmosphere
from ciw.atmosphere_moist_contract import EXPANSION_OBSERVABLES, example_request
from ciw.atmosphere_moist_preservation import (
    CLAIMS, DEFINITIONS, MORPHISM, PROPERTY_IDS, SCHEMA, SOURCE, TARGET, build, validate,
)
from ciw.atmosphere_moist_verification import CHECK_TOLERANCES, verify
from ciw.operations.runner import digest, seal


def fixture(request=None, result=None):
    request = example_request() if request is None else request
    result = compile_atmosphere(request) if result is None else result
    report = verify(request, result)
    return request, result, report, build(request, result, report)


@pytest.fixture(scope="module")
def qualified():
    return fixture()


def test_existing_typed_substrate_binds_three_artifacts_and_only_eligibility(qualified):
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


def test_distinct_model_signal_morphism_preserves_declarations_and_fixed_composition(qualified):
    request, result, report, bundle = qualified
    registry = bundle["registry"]
    assert registry["representations"][SOURCE]["role"] == "MODEL"
    assert registry["representations"][TARGET]["role"] == "SIGNAL"
    assert registry["representations"][SOURCE]["schema_id"] == "ciw.atmosphere-moist-request.v1"
    assert registry["representations"][TARGET]["schema_id"] == "ciw.atmosphere-moist-result.v1"
    morphism = registry["morphisms"][MORPHISM]
    assert morphism["kind"] == "SIMULATE"
    assert morphism["semantic_capability"] is None
    assert morphism["domain_representation_id"] == SOURCE
    assert morphism["codomain_representation_id"] == TARGET
    assert morphism["provenance_refs"] == [digest(request), result["record_digest"], report["record_digest"]]
    assert {"reference.context", "reference.frame", "reference.height_origin_m", "sampling.height_m",
            "profile.water_mixing_ratio_kg_per_kg_dry_air", "profile.composition"} <= set(morphism["parameter_names"])
    assert registry["representations"][TARGET]["scale"]["length_m"] == 1000.0
    assert registry["representations"][TARGET]["scale"]["time_s"] is None
    assert registry["representations"][TARGET]["scale"]["resolution"] is None
    assert "fixed constituent heat capacities" in morphism["validity"]["assumptions"]


def test_every_check_including_continuous_unsaturation_and_local_are_required(qualified):
    request, result, report, bundle = qualified
    rows = {row["property_id"]: row for row in bundle["verification"]["checks"]}
    aggregate = rows["atmosphere.moist.independent-report-acceptance.v1"]
    assert {row["name"] for row in report["checks"]} == set(CHECK_TOLERANCES)
    assert all(name in aggregate["notes"] for name in CHECK_TOLERANCES)
    assert "continuous_unsaturation" in aggregate["notes"]
    assert "sampled_unsaturation" in aggregate["notes"]
    assert "dry_limit_water_state" in aggregate["notes"]
    assert aggregate["status"] == "VERIFIED"
    assert aggregate["method"] == "NUMERICAL_BOUND"
    assert aggregate["evidence_ref"] == report["record_digest"]
    assert set(bundle["contract"]["requires"]) == {
        "atmosphere.moist.independent-report-acceptance.v1", "atmosphere.moist.local-qualification.v1",
    }
    assert rows["atmosphere.moist.local-qualification.v1"]["status"] == "VERIFIED"
    assert all(row["method"] != "FORMAL_PROOF" for row in rows.values())


def test_numeric_bounds_name_exact_frozen_observations_and_report_thresholds(qualified):
    request, result, report, bundle = qualified
    effects = {row["property_id"]: row for row in bundle["contract"]["effects"]}
    checks = {row["name"]: row for row in report["checks"]}
    for observable, check in DEFINITIONS:
        identity = PROPERTY_IDS.get(observable, "atmosphere.moist." + observable.replace("_", "-") + ".v1")
        bound = effects[identity]["bound"]
        assert bound["unit"] == "1"
        assert bound["upper_bound"] == checks[check]["tolerance"]
        assert checks[check]["value"] <= bound["upper_bound"]
        assert bound["composition"] == "ADDITIVE_ABSOLUTE"
    assert effects[PROPERTY_IDS["sound_speed"]]["bound"]["metric"] == "maximum_declared_normalized_frozen_sound_speed_residual"
    assert effects[PROPERTY_IDS["frozen_potential_temperature"]]["bound"]["metric"] == "maximum_declared_normalized_frozen_potential_temperature_residual"


def test_transport_latent_phase_weather_and_material_state_are_explicit_losses(qualified):
    request, result, report, bundle = qualified
    forgotten = {row["property_id"] for row in bundle["contract"]["effects"] if row["effect"] == "FORGET"}
    assert {PROPERTY_IDS[name] for name in EXPANSION_OBSERVABLES} <= forgotten
    assert {"atmosphere.moist." + name + ".v1" for name in (
        "transport-law", "dynamic-viscosity", "kinematic-viscosity", "latent-heat", "condensate",
        "continuous-height-profile", "material-moisture-content", "material-temperature", "humidity-history",
    )} <= forgotten
    assert bundle["claims"] == CLAIMS
    assert all(value is False for name, value in bundle["claims"].items() if name not in {
        "uses_existing_preservation_contracts", "synthetic_numerical_scope_only", "finite_retained_profile_only",
    })
    for row in bundle["verification"]["checks"]:
        if row["kind"] == "FORGET":
            assert row["status"] == "VERIFIED"
            assert row["method"] == "EXACT_ALGEBRA"
            assert row["evidence_ref"] == result["record_digest"]


@pytest.mark.parametrize("observable", sorted(EXPANSION_OBSERVABLES))
def test_every_unrepresented_query_expands_and_refuses_typed_gate(observable):
    request = example_request()
    request["desired_observables"].append(observable)
    request, result, report, bundle = fixture(request)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "EXPAND"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert bundle["admission_gate"]["forbidden_forgets"] == [PROPERTY_IDS[observable]]
    assert bundle["admission_gate"]["policy_violations"] == [PROPERTY_IDS[observable]]
    assert validate(bundle, request, result, report) == bundle


def test_supersaturated_domain_refuses_before_cloud_expansion_even_with_loose_tolerance():
    request = example_request()
    request["reference"]["temperature_k"] = 293.15
    request["reference"]["pressure_pa"] = 110000.0
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
    request["sampling"]["height_m"] = [0.0, 2000.0]
    request["desired_observables"].append("clouds")
    request["tolerances"] = {name: 0.01 for name in request["tolerances"]}
    request, result, report, bundle = fixture(request)
    assert max(result["profile"]["relative_humidity"]) > 1.0
    assert report["qualification"]["action"] == "REFUSE"
    assert report["status"] == "FAIL"
    assert bundle["verification"]["status"] == "REFUTED"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("field", [
    "temperature_k", "pressure_pa", "density_kg_per_m3", "water_vapour_pressure_pa",
    "dry_air_partial_pressure_pa", "relative_humidity", "liquid_water_saturation_pressure_pa",
    "liquid_equilibrium_dew_point_k", "frozen_sound_speed_m_per_s",
    "frozen_potential_temperature_k", "wind_enu_m_per_s",
])
def test_falsified_profile_observations_cannot_retain_local_eligibility(field):
    request = example_request()
    result = compile_atmosphere(request)
    if field == "wind_enu_m_per_s":
        result["profile"][field][2][0] += 1.0
    else:
        result["profile"][field][2] *= 1.01
    seal(result)
    request, result, report, bundle = fixture(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert bundle["admission_gate"]["decision"] == "REFUSED"
    assert validate(bundle, request, result, report) == bundle


def test_zero_water_retains_null_dewpoint_and_eligible_frozen_limit():
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.0
    request, result, report, bundle = fixture(request)
    assert result["profile"]["liquid_equilibrium_dew_point_k"] == [None] * 5
    assert report["qualification"]["action"] == "LOCAL"
    assert bundle["admission_gate"]["decision"] == "ELIGIBLE"
    assert validate(bundle, request, result, report) == bundle


@pytest.mark.parametrize("mutation", [
    "schema", "bound", "receipt_ref", "receipt_status", "obligation", "claim", "claim_alias",
    "request_ref", "report_ref", "parameter", "local_requirement",
])
def test_resealed_receipt_edits_cannot_remove_obligations_or_change_authority(qualified, mutation):
    request, result, report, bundle = qualified
    altered = deepcopy(bundle)
    if mutation == "schema":
        altered["schema"] = "ciw.atmosphere-preservation.v1"
    elif mutation == "bound":
        altered["contract"]["effects"][0]["bound"]["upper_bound"] *= 2
    elif mutation == "receipt_ref":
        altered["verification"]["checks"][0]["evidence_ref"] = result["record_digest"]
    elif mutation == "receipt_status":
        altered["verification"]["checks"][0]["status"] = "REFUTED"
    elif mutation == "obligation":
        altered["verification"]["checks"].pop()
    elif mutation == "claim":
        altered["claims"]["transport_law_established"] = True
    elif mutation == "claim_alias":
        altered["claims"]["execution_authority"] = 0
    elif mutation == "request_ref":
        altered["request_digest"] = result["record_digest"]
    elif mutation == "report_ref":
        altered["report_digest"] = result["record_digest"]
    elif mutation == "parameter":
        altered["registry"]["morphisms"][MORPHISM]["parameter_names"].remove("profile.water_mixing_ratio_kg_per_kg_dry_air")
    elif mutation == "local_requirement":
        altered["contract"]["requires"].remove("atmosphere.moist.local-qualification.v1")
    for name in ("registry", "contract", "verification", "admission_gate"):
        seal(altered[name])
    seal(altered)
    with pytest.raises(ValueError):
        validate(altered, request, result, report)


@pytest.mark.parametrize("part", ["request", "result", "report"])
def test_changed_artifact_cannot_rebind_an_existing_receipt(qualified, part):
    request, result, report, bundle = deepcopy(qualified)
    if part == "request":
        request["reference"]["context"]["source_ref"] += ".changed"
    elif part == "result":
        result["profile"]["relative_humidity"][2] += 0.01
        seal(result)
    else:
        report["metrics"]["residuals"]["relative_humidity"] += 0.01
        seal(report)
    with pytest.raises(ValueError):
        validate(bundle, request, result, report)


def test_retained_receipts_do_not_replay_compiler_verifier_or_quadrature(qualified, monkeypatch):
    request, result, report, bundle = qualified

    def forbidden(*args, **kwargs):
        raise AssertionError("typed retained receipts must not run a physics engine")

    import ciw.atmosphere_moist_compiler as compiler
    import ciw.atmosphere_moist_verification as verifier
    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    for name in ("verify", "_integrate_segment", "_quadrature_reference", "_residuals"):
        monkeypatch.setattr(verifier, name, forbidden)
    assert build(request, result, report) == bundle
    assert validate(bundle, request, result, report) == bundle


def test_dry_artifacts_or_mislabeled_humidity_units_cannot_receive_moist_receipts(qualified):
    request, result, report, bundle = qualified
    bad = deepcopy(result)
    bad["units"]["relative_humidity"] = "%"
    seal(bad)
    with pytest.raises(ValueError):
        build(request, bad, report)
    from ciw.atmosphere_contract import example_request as dry_request
    from ciw.atmosphere_compiler import compile_atmosphere as dry_compile
    from ciw.atmosphere_verification import verify as dry_verify
    dry = dry_request()
    candidate = dry_compile(dry)
    with pytest.raises(ValueError):
        build(dry, candidate, dry_verify(dry, candidate))
