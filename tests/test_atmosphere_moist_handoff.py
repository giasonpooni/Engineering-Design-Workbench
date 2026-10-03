from copy import deepcopy

import pytest

from ciw.atmosphere_moist_compiler import compile_atmosphere
from ciw.atmosphere_moist_contract import FRAME, example_request
from ciw.atmosphere_moist_handoff import (
    BINDING_KEYS, CLAIMS, MIXTURE_ENVIRONMENT_FIELDS, PROVIDER_FIELDS, SCHEMA,
    build_handoff, validate_handoff,
)
from ciw.core.identities import new_identity
from ciw.operations.runner import digest, seal


@pytest.fixture(scope="module")
def qualified():
    request = example_request()
    request["reference"]["height_origin_m"] = 237.0
    request["reference"]["context"] = {
        "source_kind": "declared_environment", "source_ref": "declared.moist.fixture.001",
        "valid_time_utc": "2026-10-03T06:00:00Z",
    }
    request["profile"]["wind_enu_m_per_s"] = [2.0, -3.0, 0.5]
    result = compile_atmosphere(request)
    bindings = {
        "source_evidence_id": digest({"declared_evidence": request}),
        "source_result_id": new_identity("result"),
        "source_execution_id": new_identity("execution"),
        "source_record_digest": digest({"outer_result": result}),
        "verification_id": new_identity("verification"),
        "recomputed_report_digest": digest({"audit_occurrence": result["record_digest"]}),
    }
    return request, result, bindings


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
@pytest.mark.parametrize("index", [0, 2, 4])
def test_exact_sample_mixture_units_context_and_separate_bindings(qualified, provider, index):
    request, result, bindings = qualified
    handoff = build_handoff(request, result, bindings, sample_index=index, provider=provider)
    assert validate_handoff(request, result, handoff, bindings) == handoff
    assert handoff["schema"] == SCHEMA
    assert handoff["request_digest"] == digest(request)
    assert handoff["atmosphere_result_digest"] == result["record_digest"]
    assert all(handoff[name] == value for name, value in bindings.items())
    assert len(set(bindings.values())) == 6
    assert handoff["sample_index"] == index
    assert handoff["height_m"] == result["profile"]["height_m"][index]
    assert handoff["absolute_height_m"] == 237.0 + handoff["height_m"]
    assert handoff["height_interpretation"] == "height_above_reference"
    assert handoff["frame"] == FRAME
    assert handoff["context"] == request["reference"]["context"]
    assert handoff["composition"] == "dry_air_water_vapour"
    assert set(handoff["environment"]) == set(PROVIDER_FIELDS[provider])
    for field in PROVIDER_FIELDS[provider]:
        expected = (result["mixture"][field] if field in MIXTURE_ENVIRONMENT_FIELDS
                    else result["profile"][field][index])
        assert handoff["environment"][field] == expected
    assert handoff["units"]["water_mixing_ratio_kg_per_kg_dry_air"] == "kg/kg dry air"
    assert handoff["units"]["water_mass_fraction"] == "1"
    assert handoff["units"]["relative_humidity"] == "1"
    assert handoff["units"]["liquid_equilibrium_dew_point_k"] == "K"
    assert handoff["environment"]["wind_enu_m_per_s"] == [2.0, -3.0, 0.5]
    assert handoff["claims"] == CLAIMS


def test_no_unqualified_transport_phase_optical_material_or_coordinate_admission(qualified):
    request, result, bindings = qualified
    for provider in PROVIDER_FIELDS:
        handoff = build_handoff(request, result, bindings, sample_index=2, provider=provider)
        forgotten = {row["property"] for row in handoff["effects"] if row["effect"] == "FORGET"}
        assert {
            "other_height_samples", "continuous_height_profile", "phase_change", "latent_heat",
            "condensate", "ice_response", "transport_law", "dynamic_viscosity_pa_s",
            "kinematic_viscosity_m2_per_s", "clouds", "turbulence", "weather_evolution",
            "visual_scattering", "material_temperature", "material_moisture_content",
            "material_conditioning", "humidity_history", "aerodynamic_forces", "fluid_dynamics",
        } <= forgotten
        preserved = {row["property"] for row in handoff["effects"] if row["effect"] == "PRESERVE"}
        assert preserved == set(PROVIDER_FIELDS[provider])
        assert not any("viscosity" in field for field in handoff["environment"])
        assert "sound_speed_m_per_s" not in handoff["environment"]
        assert all(value is False for name, value in handoff["claims"].items()
                   if name not in {"data_only_environmental_boundary", "exact_retained_sample"})
        assert any("frame" in value and "time" in value for value in handoff["receiver_requirements"])
        assert any("pressure enhancement" in value for value in handoff["receiver_requirements"])
        assert "operation" not in handoff and "command" not in handoff
    for provider in ("impact", "fluid"):
        handoff = build_handoff(request, result, bindings, sample_index=2, provider=provider)
        assert "frozen_sound_speed_m_per_s" in handoff["environment"]
        assert any("transport law" in value for value in handoff["receiver_requirements"])
        assert any("timescale" in value for value in handoff["receiver_requirements"])
    render = build_handoff(request, result, bindings, sample_index=2, provider="render")
    assert "frozen_sound_speed_m_per_s" not in render["environment"]
    assert any("optical" in value for value in render["receiver_requirements"])


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
def test_zero_water_has_zero_humidity_and_null_dew_point_without_coercion(provider):
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.0
    result = compile_atmosphere(request)
    bindings = {
        "source_evidence_id": digest(request), "source_result_id": new_identity("result"),
        "source_execution_id": new_identity("execution"), "source_record_digest": digest(result),
        "verification_id": new_identity("verification"),
        "recomputed_report_digest": digest({"dry_limit": True}),
    }
    handoff = build_handoff(request, result, bindings, sample_index=4, provider=provider)
    assert handoff["environment"]["liquid_equilibrium_dew_point_k"] is None
    for field in ("water_vapour_pressure_pa", "relative_humidity", *MIXTURE_ENVIRONMENT_FIELDS):
        assert handoff["environment"][field] == 0.0
    assert validate_handoff(request, result, handoff, bindings) == handoff


@pytest.mark.parametrize("index", [-1, 5, True, False, 1.0, "1", None])
def test_selection_requires_exact_in_domain_integer(qualified, index):
    request, result, bindings = qualified
    with pytest.raises(ValueError):
        build_handoff(request, result, bindings, sample_index=index, provider="impact")


@pytest.mark.parametrize("provider", ["Impact", "impact ", "weather", "../impact", True, 1, None])
def test_receiver_names_are_fixed_and_exact(qualified, provider):
    request, result, bindings = qualified
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
def test_occurrence_and_content_identity_classes_remain_separate(qualified, field, bad):
    request, result, bindings = qualified
    altered = deepcopy(bindings)
    altered[field] = bad
    with pytest.raises(ValueError):
        build_handoff(request, result, altered, sample_index=0, provider="impact")


@pytest.mark.parametrize("mutation", [
    "schema", "scope", "sample", "sample_alias", "temperature", "humidity", "mixing_ratio",
    "dew_point", "height", "frame", "context", "units", "provider", "composition", "viscosity",
    "source_result", "source_record", "recomputed_report", "forget", "claim", "claim_alias",
    "extra", "receiver",
])
def test_resealed_edits_cannot_rebind_values_profile_units_or_authority(qualified, mutation):
    request, result, bindings = qualified
    handoff = build_handoff(request, result, bindings, sample_index=0, provider="impact")
    changed = deepcopy(handoff)
    if mutation == "schema":
        changed["schema"] = "ciw.atmosphere-handoff.v1"
    elif mutation == "scope":
        changed["claim_scope"] = "dry_hydrostatic_constant_gravity_column"
    elif mutation == "sample":
        changed["sample_index"] = 1
    elif mutation == "sample_alias":
        changed["sample_index"] = False
    elif mutation == "temperature":
        changed["environment"]["temperature_k"] += 1
    elif mutation == "humidity":
        changed["environment"]["relative_humidity"] += 0.01
    elif mutation == "mixing_ratio":
        changed["environment"]["water_mixing_ratio_kg_per_kg_dry_air"] += 0.001
    elif mutation == "dew_point":
        changed["environment"]["liquid_equilibrium_dew_point_k"] += 1.0
    elif mutation == "height":
        changed["absolute_height_m"] += 1
    elif mutation == "frame":
        changed["frame"] = "atmosphere.world_ecef.v1"
    elif mutation == "context":
        changed["context"]["source_ref"] = "another.source"
    elif mutation == "units":
        changed["units"]["water_mixing_ratio_kg_per_kg_dry_air"] = "kg/kg wet air"
    elif mutation == "provider":
        changed["provider"] = "fluid"
    elif mutation == "composition":
        changed["composition"] = "dry_air"
    elif mutation == "viscosity":
        changed["environment"]["dynamic_viscosity_pa_s"] = 1.8e-5
    elif mutation == "source_result":
        changed["source_result_id"] = new_identity("result")
    elif mutation == "source_record":
        changed["source_record_digest"] = result["record_digest"]
    elif mutation == "recomputed_report":
        changed["recomputed_report_digest"] = result["record_digest"]
    elif mutation == "forget":
        changed["effects"] = [row for row in changed["effects"] if row["property"] != "transport_law"]
    elif mutation == "claim":
        changed["claims"]["physical_validation_established"] = True
    elif mutation == "claim_alias":
        changed["claims"]["execution_authority"] = 0
    elif mutation == "extra":
        changed["command"] = "invoke receiver"
    elif mutation == "receiver":
        changed["receiver_requirements"] = []
    seal(changed)
    with pytest.raises(ValueError):
        validate_handoff(request, result, changed, bindings)


@pytest.mark.parametrize("part", ["request", "result", "bindings"])
def test_changed_source_or_execution_cannot_rebind_a_receipt(qualified, part):
    request, result, bindings = deepcopy(qualified)
    handoff = build_handoff(request, result, bindings, sample_index=2, provider="impact")
    if part == "request":
        request["reference"]["context"]["source_ref"] = "new.reference"
    elif part == "result":
        result["profile"]["relative_humidity"][2] += 0.01
        seal(result)
    else:
        bindings["source_execution_id"] = new_identity("execution")
    with pytest.raises(ValueError):
        validate_handoff(request, result, handoff, bindings)


def test_selection_and_validation_are_detached_and_never_replay(qualified, monkeypatch):
    request, result, bindings = qualified
    before = deepcopy(qualified)
    handoff = build_handoff(request, result, bindings, sample_index=2, provider="impact")

    def forbidden(*args, **kwargs):
        raise AssertionError("retained data selection must not run an engine")

    import ciw.atmosphere_moist_compiler as compiler
    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    assert build_handoff(request, result, bindings, sample_index=2, provider="impact") == handoff
    assert validate_handoff(request, result, handoff, bindings) == handoff
    handoff["environment"]["wind_enu_m_per_s"][0] += 1
    handoff["context"]["source_ref"] = "mutated.copy"
    assert qualified == before


@pytest.mark.parametrize("field", sorted(BINDING_KEYS))
def test_each_identity_binding_is_required(qualified, field):
    request, result, bindings = qualified
    changed = {key: value for key, value in bindings.items() if key != field}
    with pytest.raises(ValueError):
        build_handoff(request, result, changed, sample_index=0, provider="impact")


def test_extra_binding_unsealed_handoff_or_dry_source_is_rejected(qualified):
    request, result, bindings = qualified
    with pytest.raises(ValueError):
        build_handoff(request, result, {**bindings, "operation_id": "atmosphere.moist-compile.v1"},
                      sample_index=0, provider="impact")
    handoff = build_handoff(request, result, bindings, sample_index=0, provider="impact")
    handoff["environment"]["relative_humidity"] += 0.01
    with pytest.raises(ValueError):
        validate_handoff(request, result, handoff, bindings)
    from ciw.atmosphere_contract import example_request as dry_request
    from ciw.atmosphere_compiler import compile_atmosphere as dry_compile
    dry = dry_request()
    with pytest.raises(ValueError):
        build_handoff(dry, dry_compile(dry), bindings, sample_index=0, provider="impact")
