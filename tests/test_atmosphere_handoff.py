from copy import deepcopy

import pytest

from ciw.atmosphere_compiler import compile_atmosphere
from ciw.atmosphere_contract import FRAME, example_request
from ciw.atmosphere_handoff import CLAIMS, PROVIDER_FIELDS, SCHEMA, build_handoff, validate_handoff
from ciw.atmosphere_verification import verify
from ciw.core.identities import new_identity
from ciw.operations.runner import digest, seal


@pytest.fixture(scope="module")
def qualified():
    request = example_request()
    request["reference"]["height_origin_m"] = 237.0
    request["reference"]["context"] = {"source_kind": "declared_environment", "source_ref": "declared.fixture.001",
                                       "valid_time_utc": "2026-10-03T06:00:00Z"}
    request["profile"]["wind_enu_m_per_s"] = [2.0, -3.0, 0.5]
    result = compile_atmosphere(request)
    report = verify(request, result)
    bindings = {
        "source_evidence_id": digest({"synthetic_evidence": request}),
        "source_result_id": new_identity("result"), "source_execution_id": new_identity("execution"),
        "source_record_digest": digest({"outer_result": result}),
        "verification_id": new_identity("verification"), "recomputed_report_digest": report["record_digest"],
    }
    return request, result, report, bindings


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
@pytest.mark.parametrize("index", [0, 5, 10])
def test_exact_sample_provider_fields_units_context_and_identity_bindings(qualified, provider, index):
    request, result, report, bindings = qualified
    handoff = build_handoff(request, result, bindings, sample_index=index, provider=provider)
    assert validate_handoff(request, result, handoff, bindings) == handoff
    assert handoff["schema"] == SCHEMA
    assert handoff["request_digest"] == digest(request)
    assert handoff["atmosphere_result_digest"] == result["record_digest"]
    assert all(handoff[name] == value for name, value in bindings.items())
    assert handoff["sample_index"] == index
    assert handoff["height_m"] == result["profile"]["height_m"][index]
    assert handoff["reference_height_origin_m"] == 237.0
    assert handoff["absolute_height_m"] == 237.0 + handoff["height_m"]
    assert handoff["height_interpretation"] == "height_above_reference"
    assert handoff["frame"] == FRAME
    assert handoff["context"] == request["reference"]["context"]
    assert handoff["composition"] == "dry_air"
    assert set(handoff["environment"]) == set(PROVIDER_FIELDS[provider])
    for field in PROVIDER_FIELDS[provider]:
        assert handoff["environment"][field] == result["profile"][field][index]
        assert handoff["units"][field] == result["units"][field]
    assert handoff["environment"]["wind_enu_m_per_s"] == [2.0, -3.0, 0.5]
    assert handoff["claims"] == CLAIMS


def test_provider_handoff_is_environment_only_and_explicitly_forgets_unresolved_physics(qualified):
    request, result, report, bindings = qualified
    for provider in PROVIDER_FIELDS:
        handoff = build_handoff(request, result, bindings, sample_index=5, provider=provider)
        forgotten = {row["property"] for row in handoff["effects"] if row["effect"] == "FORGET"}
        assert {"other_height_samples", "continuous_height_profile", "humidity", "clouds", "turbulence",
                "weather_evolution", "visual_scattering", "material_temperature", "material_conditioning",
                "aerodynamic_forces", "fluid_dynamics"} <= forgotten
        preserved = {row["property"] for row in handoff["effects"] if row["effect"] == "PRESERVE"}
        assert preserved == set(PROVIDER_FIELDS[provider])
        assert all(row["scope"] == "one exact retained sample" for row in handoff["effects"]
                   if row["effect"] == "PRESERVE")
        assert all(handoff["claims"][name] is False for name in (
            "interpolation_performed", "physical_validation_established", "receiver_model_validated",
            "material_conditioning_established", "forces_computed", "visual_scattering_established",
            "geodetic_transform_performed", "coordinate_transfer_validated",
            "canonical_state_mutated", "state_admission_performed", "execution_authority"))
        assert handoff["receiver_requirements"]
        assert any("frame" in requirement and "time" in requirement for requirement in handoff["receiver_requirements"])
        assert "operation" not in handoff and "command" not in handoff
    impact = build_handoff(request, result, bindings, sample_index=5, provider="impact")
    assert "temperature_k" in impact["environment"]
    assert "material_temperature" not in impact["environment"]
    render = build_handoff(request, result, bindings, sample_index=5, provider="render")
    assert "cloud_color" not in render["environment"]
    assert "optical_depth" not in render["environment"]
    assert "sound_speed_m_per_s" not in render["environment"]


@pytest.mark.parametrize("index", [-1, 11, True, False, 1.0, "1", None])
def test_sample_index_is_exact_in_domain_integer_without_coercions(qualified, index):
    request, result, report, bindings = qualified
    with pytest.raises(ValueError):
        build_handoff(request, result, bindings, sample_index=index, provider="impact")


@pytest.mark.parametrize("provider", ["Impact", "impact ", "weather", "../impact", True, 1, None])
def test_only_fixed_exact_provider_names_are_accepted(qualified, provider):
    request, result, report, bindings = qualified
    with pytest.raises(ValueError):
        build_handoff(request, result, bindings, sample_index=0, provider=provider)


@pytest.mark.parametrize("field,bad", [
    ("source_evidence_id", "execution-" + "0" * 32),
    ("source_result_id", "sha256:" + "0" * 64),
    ("source_execution_id", "result-" + "0" * 32),
    ("source_record_digest", "result-" + "0" * 32),
    ("verification_id", "execution-" + "0" * 32),
    ("recomputed_report_digest", "verification-" + "0" * 32),
    ("source_result_id", "result-" + "G" * 32),
    ("source_evidence_id", "sha256:" + "A" * 64),
    ("source_execution_id", False),
])
def test_identity_classes_cannot_be_relabelled_or_coerced(qualified, field, bad):
    request, result, report, bindings = qualified
    changed = deepcopy(bindings)
    changed[field] = bad
    with pytest.raises(ValueError):
        build_handoff(request, result, changed, sample_index=0, provider="impact")


@pytest.mark.parametrize("mutation", ["sample", "sample_alias", "temperature", "wind", "height", "frame",
                                     "context", "units", "provider", "source_result", "source_record",
                                     "recomputed_report", "forget", "claim", "claim_alias", "extra", "receiver"])
def test_resealed_handoff_edits_cannot_rebind_current_sample_or_claims(qualified, mutation):
    request, result, report, bindings = qualified
    handoff = build_handoff(request, result, bindings, sample_index=0, provider="impact")
    changed = deepcopy(handoff)
    if mutation == "sample":
        changed["sample_index"] = 1
    elif mutation == "sample_alias":
        changed["sample_index"] = False
    elif mutation == "temperature":
        changed["environment"]["temperature_k"] += 1
    elif mutation == "wind":
        changed["environment"]["wind_enu_m_per_s"][0] += 1
    elif mutation == "height":
        changed["absolute_height_m"] += 1
    elif mutation == "frame":
        changed["frame"] = "atmosphere.world_ecef.v1"
    elif mutation == "context":
        changed["context"]["source_ref"] = "another.source"
    elif mutation == "units":
        changed["units"]["dynamic_viscosity_pa_s"] = "m^2/s"
    elif mutation == "provider":
        changed["provider"] = "fluid"
    elif mutation == "source_result":
        changed["source_result_id"] = new_identity("result")
    elif mutation == "source_record":
        changed["source_record_digest"] = result["record_digest"]
    elif mutation == "recomputed_report":
        changed["recomputed_report_digest"] = result["record_digest"]
    elif mutation == "forget":
        changed["effects"] = [row for row in changed["effects"] if row["property"] != "material_conditioning"]
    elif mutation == "claim":
        changed["claims"]["physical_validation_established"] = True
    elif mutation == "claim_alias":
        changed["claims"]["execution_authority"] = 0
    elif mutation == "extra":
        changed["command"] = "invoke provider"
    elif mutation == "receiver":
        changed["receiver_requirements"] = []
    seal(changed)
    with pytest.raises(ValueError):
        validate_handoff(request, result, changed, bindings)


@pytest.mark.parametrize("part", ["request", "result", "bindings"])
def test_retained_handoff_detects_changed_context_result_or_execution(qualified, part):
    request, result, report, bindings = deepcopy(qualified)
    handoff = build_handoff(request, result, bindings, sample_index=5, provider="impact")
    if part == "request":
        request["reference"]["context"]["source_ref"] = "new.reference"
    elif part == "result":
        result["profile"]["temperature_k"][5] += 0.1
        seal(result)
    else:
        bindings["source_execution_id"] = new_identity("execution")
    with pytest.raises(ValueError):
        validate_handoff(request, result, handoff, bindings)


def test_handoff_build_validation_are_detached_and_never_replay_engines(qualified, monkeypatch):
    request, result, report, bindings = qualified
    before = deepcopy(qualified)
    handoff = build_handoff(request, result, bindings, sample_index=5, provider="impact")

    def forbidden(*args, **kwargs):
        raise AssertionError("handoff is a retained data-only exact-sample selection")

    import ciw.atmosphere_compiler as compiler
    import ciw.atmosphere_verification as verifier
    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    for name in ("verify", "_integrate_segment", "_quadrature_reference", "_residuals"):
        monkeypatch.setattr(verifier, name, forbidden)
    assert validate_handoff(request, result, handoff, bindings) == handoff
    assert build_handoff(request, result, bindings, sample_index=5, provider="impact") == handoff
    handoff["environment"]["wind_enu_m_per_s"][0] += 1.0
    assert qualified == before


def test_missing_extra_or_unsealed_bindings_are_not_accepted(qualified):
    request, result, report, bindings = qualified
    for changed in ({key: value for key, value in bindings.items() if key != "verification_id"},
                    {**bindings, "operation_id": "atmosphere.compile.v1"}):
        with pytest.raises(ValueError):
            build_handoff(request, result, changed, sample_index=0, provider="impact")
    handoff = build_handoff(request, result, bindings, sample_index=0, provider="impact")
    handoff["environment"]["temperature_k"] += 1.0
    with pytest.raises(ValueError):
        validate_handoff(request, result, handoff, bindings)
