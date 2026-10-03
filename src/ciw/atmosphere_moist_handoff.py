"""Sealed data-only moist environmental declarations for fixed receivers.

One retained height sample is selected without interpolation. The caller owns
fresh numerical verification and LOCAL export policy. Content and occurrence
bindings do not establish that such an audit happened or activate a provider.
"""
from __future__ import annotations

from copy import deepcopy

from .atmosphere_moist_contract import CLAIM_SCOPE, UNITS, validate_request, validate_result
from .control_contracts import content_ref, detached, keys
from .core.identities import validate_identity
from .operations.runner import check_seal, digest, seal

SCHEMA = "ciw.atmosphere-moist-handoff.v1"
BINDING_KEYS = {
    "source_evidence_id", "source_result_id", "source_execution_id",
    "source_record_digest", "verification_id", "recomputed_report_digest",
}
MIXTURE_ENVIRONMENT_FIELDS = (
    "water_mixing_ratio_kg_per_kg_dry_air", "water_mass_fraction",
)
MOISTURE_FIELDS = (
    "water_vapour_pressure_pa", "relative_humidity", "liquid_equilibrium_dew_point_k",
    *MIXTURE_ENVIRONMENT_FIELDS,
)
PROVIDER_FIELDS = {
    "impact": (
        "temperature_k", "pressure_pa", "density_kg_per_m3", "wind_enu_m_per_s",
        "frozen_sound_speed_m_per_s", *MOISTURE_FIELDS,
    ),
    "fluid": (
        "temperature_k", "pressure_pa", "dry_air_partial_pressure_pa",
        "density_kg_per_m3", "dry_air_density_kg_per_m3", "water_vapour_density_kg_per_m3",
        "wind_enu_m_per_s", "frozen_sound_speed_m_per_s", *MOISTURE_FIELDS,
    ),
    "render": (
        "temperature_k", "pressure_pa", "density_kg_per_m3", "wind_enu_m_per_s",
        *MOISTURE_FIELDS,
    ),
}
ENVIRONMENT_UNITS = {
    **UNITS, "water_mixing_ratio_kg_per_kg_dry_air": "kg/kg dry air",
    "water_mass_fraction": "1",
}
CLAIMS = {
    "data_only_environmental_boundary": True,
    "exact_retained_sample": True,
    "interpolation_performed": False,
    "physical_validation_established": False,
    "receiver_model_validated": False,
    "moist_transport_law_established": False,
    "phase_change_established": False,
    "wmo_humidity_conformance_established": False,
    "material_conditioning_established": False,
    "forces_computed": False,
    "visual_scattering_established": False,
    "geodetic_transform_performed": False,
    "coordinate_transfer_validated": False,
    "canonical_state_mutated": False,
    "state_admission_performed": False,
    "execution_authority": False,
}
FORGOTTEN = (
    "other_height_samples", "continuous_height_profile", "phase_change", "latent_heat",
    "condensate", "ice_response", "precipitation", "clouds", "turbulence",
    "weather_evolution", "chemical_reactions", "radiation", "visual_scattering",
    "material_temperature", "material_moisture_content", "material_conditioning",
    "humidity_history", "aerodynamic_forces", "fluid_dynamics", "transport_law",
    "dynamic_viscosity_pa_s", "kinematic_viscosity_m2_per_s", "moist_adiabatic_response",
)
FRAME_REQUIREMENT = "Validate declared local ENU frame, reference origin and context time against the receiver's frame and time before using boundary values or wind."
TRANSPORT_REQUIREMENT = "Supply and qualify a moist-mixture transport law independently; no dynamic or kinematic viscosity is supplied by this handoff."
ACOUSTIC_REQUIREMENT = "Validate frozen-composition acoustics against the receiver's timescale and regime before using frozen_sound_speed_m_per_s; no equilibrium or phase-changing acoustic response is supplied."
MOISTURE_REQUIREMENT = "Treat relative humidity and liquid-equilibrium dew point as pure-liquid ideal-mixture Magnus diagnostics without pressure enhancement; independently qualify phase, ice and condensation assumptions."
RECEIVER_REQUIREMENTS = {
    "impact": [
        FRAME_REQUIREMENT,
        "Validate the impact provider's atmospheric boundary schema and applicable flow regime.",
        TRANSPORT_REQUIREMENT, ACOUSTIC_REQUIREMENT, MOISTURE_REQUIREMENT,
        "Specify aerodynamic geometry and laws before computing environmental forces.",
        "Supply independent specimen temperature, moisture-content and conditioning-history evidence; ambient humidity does not establish material state.",
    ],
    "fluid": [
        FRAME_REQUIREMENT,
        "Validate the fluid provider's boundary schema, governing equations and flow regime.",
        TRANSPORT_REQUIREMENT, ACOUSTIC_REQUIREMENT, MOISTURE_REQUIREMENT,
        "Declare domain, boundary geometry, initial state and any evolving composition or phase laws independently.",
    ],
    "render": [
        FRAME_REQUIREMENT,
        "Validate the renderer's environmental input schema and artistic or physical model.",
        MOISTURE_REQUIREMENT,
        "Supply optical composition, scattering, illumination and cloud inputs independently; humidity alone does not establish optical state.",
    ],
}


def _bindings(bindings: dict) -> dict:
    keys(bindings, BINDING_KEYS)
    for name in ("source_evidence_id", "source_record_digest", "recomputed_report_digest"):
        content_ref(bindings[name])
    for name, kind in (("source_result_id", "result"), ("source_execution_id", "execution"),
                       ("verification_id", "verification")):
        if type(bindings[name]) is not str:
            raise ValueError("Handoff occurrence identities must be exact strings")
        validate_identity(bindings[name], kind)
    return deepcopy(bindings)


def build_handoff(request: dict, result: dict, bindings: dict, *, sample_index: int,
                  provider: str) -> dict:
    """Select one retained sample without engine replay or physical admission."""
    request = validate_request(request)
    result = validate_result(request, result)
    bindings = _bindings(bindings)
    if type(provider) is not str or provider not in PROVIDER_FIELDS:
        raise ValueError("Require one fixed provider: impact, fluid or render")
    if type(sample_index) is not int or not 0 <= sample_index < len(result["profile"]["height_m"]):
        raise ValueError("sample_index must be an integer inside the exact retained height grid")
    profile, reference = result["profile"], request["reference"]
    height = profile["height_m"][sample_index]
    fields = PROVIDER_FIELDS[provider]
    environment = {
        name: deepcopy(result["mixture"][name] if name in MIXTURE_ENVIRONMENT_FIELDS
                       else profile[name][sample_index])
        for name in fields
    }
    provider_omissions = sorted(set(ENVIRONMENT_UNITS) - set(fields) - {"height_m"})
    effects = [
        {"property": name, "effect": "PRESERVE", "scope": "one exact retained sample"}
        for name in fields
    ]
    effects.extend({"property": name, "effect": "FORGET", "scope": "unrepresented or unselected"}
                   for name in sorted(set(FORGOTTEN) | set(provider_omissions)))
    return seal({
        "schema": SCHEMA, "request_digest": digest(request),
        "atmosphere_result_digest": result["record_digest"], **bindings,
        "provider": provider, "claim_scope": CLAIM_SCOPE,
        "sample_index": sample_index, "height_m": height,
        "reference_height_origin_m": reference["height_origin_m"],
        "absolute_height_m": reference["height_origin_m"] + height,
        "height_interpretation": request["sampling"]["interpretation"],
        "frame": reference["frame"], "context": deepcopy(reference["context"]),
        "composition": request["profile"]["composition"],
        "gravity_m_per_s2": request["profile"]["gravity_m_per_s2"],
        "environment": environment,
        "units": {"height_m": "m", "reference_height_origin_m": "m", "absolute_height_m": "m",
                  "gravity_m_per_s2": "m/s^2", **{name: ENVIRONMENT_UNITS[name] for name in fields}},
        "effects": effects, "receiver_requirements": deepcopy(RECEIVER_REQUIREMENTS[provider]),
        "interpretation": "Declared frozen-composition moist atmospheric boundary at one retained height. Liquid-water humidity and dew point are diagnostics, not phase or material state. absolute_height_m is reference origin plus relative height in the declared coordinate; no geodetic transformation, interpolation, operational activation or receiver qualification.",
        "claims": deepcopy(CLAIMS),
    })


def validate_handoff(request: dict, result: dict, payload: dict, bindings: dict) -> dict:
    """Reject stale fields, identities, units and claims by exact static binding."""
    keys(payload, {
        "schema", "request_digest", "atmosphere_result_digest", *BINDING_KEYS,
        "provider", "claim_scope", "sample_index", "height_m", "reference_height_origin_m",
        "absolute_height_m", "height_interpretation", "frame", "context", "composition",
        "gravity_m_per_s2", "environment", "units", "effects", "receiver_requirements",
        "interpretation", "claims", "record_digest",
    })
    check_seal(payload)
    expected = build_handoff(request, result, bindings, sample_index=payload["sample_index"],
                             provider=payload["provider"])
    if digest(payload) != digest(expected):
        raise ValueError("Moist atmosphere handoff differs from its exact retained sample or binding")
    return detached(payload)
