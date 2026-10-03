"""Sealed, data-only environmental boundary declarations for fixed providers.

An exact retained height sample is selected without interpolation. The receipt
binds existing evidence, result, execution and verification identities; none
of those references activate an operation or establish physical validity.
"""
from __future__ import annotations

from copy import deepcopy

from .atmosphere_contract import CLAIM_SCOPE, UNITS, validate_request, validate_result
from .control_contracts import content_ref, detached, keys
from .core.identities import validate_identity
from .operations.runner import check_seal, digest, seal

SCHEMA = "ciw.atmosphere-handoff.v1"
BINDING_KEYS = {
    "source_evidence_id", "source_result_id", "source_execution_id",
    "source_record_digest", "verification_id", "recomputed_report_digest",
}
PROVIDER_FIELDS = {
    "impact": (
        "temperature_k", "pressure_pa", "density_kg_per_m3", "wind_enu_m_per_s",
        "sound_speed_m_per_s", "dynamic_viscosity_pa_s", "kinematic_viscosity_m2_per_s",
    ),
    "fluid": (
        "density_kg_per_m3", "dynamic_viscosity_pa_s", "kinematic_viscosity_m2_per_s",
        "pressure_pa", "temperature_k", "wind_enu_m_per_s",
    ),
    "render": ("temperature_k", "pressure_pa", "density_kg_per_m3", "wind_enu_m_per_s"),
}
CLAIMS = {
    "data_only_environmental_boundary": True,
    "exact_retained_sample": True,
    "interpolation_performed": False,
    "physical_validation_established": False,
    "receiver_model_validated": False,
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
    "other_height_samples", "continuous_height_profile", "humidity", "precipitation",
    "clouds", "turbulence", "weather_evolution", "chemical_reactions", "radiation",
    "visual_scattering", "material_temperature", "material_conditioning",
    "aerodynamic_forces", "fluid_dynamics",
)
RECEIVER_REQUIREMENTS = {
    "impact": [
        "Validate declared local ENU frame, reference origin and context time against the receiver's frame and time before using boundary values or wind.",
        "Validate the impact provider's atmospheric boundary schema and applicable flow regime.",
        "Specify aerodynamic geometry and laws before computing environmental forces.",
        "Supply independent specimen temperature and conditioning evidence for material response.",
    ],
    "fluid": [
        "Validate declared local ENU frame, reference origin and context time against the receiver's frame and time before using boundary values or wind.",
        "Validate the fluid provider's boundary schema, governing equations and flow regime.",
        "Declare domain, boundary geometry, initial state and transport model independently.",
    ],
    "render": [
        "Validate declared local ENU frame, reference origin and context time against the receiver's frame and time before using boundary values or wind.",
        "Validate the renderer's environmental input schema and artistic or physical model.",
        "Supply optical composition, scattering, illumination and cloud inputs independently.",
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
    """Select one exact sample from already retained data, without engine replay.

    The caller owns fresh verification of this exact retained snapshot before
    export. A syntactically valid binding is not evidence that such an audit
    was performed; its occurrence remains visible and separately typed.
    """
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
    environment = {name: deepcopy(profile[name][sample_index]) for name in fields}
    provider_omissions = sorted(set(UNITS) - set(fields) - {"height_m"})
    effects = [
        {"property": name, "effect": "PRESERVE", "scope": "one exact retained sample"}
        for name in fields
    ]
    effects.extend({"property": name, "effect": "FORGET", "scope": "unrepresented or unselected"}
                   for name in (*FORGOTTEN, *provider_omissions))
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
                  "gravity_m_per_s2": "m/s^2", **{name: UNITS[name] for name in fields}},
        "effects": effects, "receiver_requirements": deepcopy(RECEIVER_REQUIREMENTS[provider]),
        "interpretation": "Declared dry atmospheric boundary at one retained height. absolute_height_m is reference origin plus relative height in the declared coordinate; no terrain, geoid or geodetic transformation, interpolation, operational activation or receiver qualification.",
        "claims": deepcopy(CLAIMS),
    })


def validate_handoff(request: dict, result: dict, payload: dict, bindings: dict) -> dict:
    """Reject stale values, identities, units or claims by exact static binding."""
    # Validate the envelope before reading the discriminators used to rebuild.
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
    # Canonical JSON content comparison preserves bool/int/float distinctions
    # that Python's structural equality deliberately collapses.
    if digest(payload) != digest(expected):
        raise ValueError("Atmosphere handoff differs from its exact retained sample or binding")
    return detached(payload)
