"""Bounded, data-only atmospheric reference and acceptance declarations.

These records preserve provenance and uncertainty declarations. A seal does
not authenticate a measurement, validate a calibration, or establish physical
independence. Only exact retained height samples can be compared.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import re
from urllib.parse import urlsplit

from . import atmosphere_contract as dry
from . import atmosphere_moist_contract as moist
from .adapters.protocol import InstrumentManifest
from .control_contracts import content_ref, keys, number
from .core.identities import evidence_id, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.runner import check_seal, digest, seal

REFERENCE_SCHEMA = "ciw.atmosphere-reference.v1"
POLICY_SCHEMA = "ciw.atmosphere-comparison-policy.v1"
COMPARISON_SCHEMA = "ciw.atmosphere-comparison.v1"
RULE = "absolute_plus_relative_plus_reference_bound"
FIELD_UNITS = {
    "temperature_k": "K", "pressure_pa": "Pa",
    "density_kg_per_m3": "kg/m^3", "water_vapour_pressure_pa": "Pa",
    "relative_humidity": "1", "liquid_water_saturation_pressure_pa": "Pa",
}
FIELD_BOUNDS = {
    "temperature_k": (1e-20, 1e6), "pressure_pa": (1e-20, 1e9),
    "density_kg_per_m3": (1e-20, 1e6),
    "water_vapour_pressure_pa": (0.0, 1e9),
    "relative_humidity": (0.0, 2.0),
    "liquid_water_saturation_pressure_pa": (1e-20, 1e9),
}
MAX_OBSERVATIONS = 129
MAX_SCALARS = MAX_OBSERVATIONS * len(FIELD_UNITS)
PURE_LIQUID_CONVENTION = "pure_liquid_magnus_17_62_243_12.v1"
HUMIDITY_CONVENTIONS = {
    "not_applicable", PURE_LIQUID_CONVENTION,
    "pressure_enhanced_relative_humidity",
}
BINDING_KEYS = {
    "source_evidence_id", "source_result_id", "source_execution_id",
    "source_record_digest", "verification_id", "recomputed_report_digest",
    "reference_evidence_id",
}
CLAIMS = {
    "exact_retained_samples": True,
    "interpolation_performed": False,
    "independence_declared": False,  # Bound to the reference declaration below.
    "independence_established": False,
    "measurement_authenticity_established": False,
    "calibration_validation": False,
    "physical_validation": "not_established",
    "statistical_significance_established": False,
    "canonical_state_mutated": False,
    "state_admission_performed": False,
    "execution_authority": False,
}


def _text(value, label: str, maximum: int = 512) -> None:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"Require bounded nonempty {label}")


def _bounded(value, lower: float, upper: float, label: str) -> float:
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _nonnegative(value, upper: float, label: str) -> float:
    value = _bounded(value, 0.0, upper, label)
    # With bounded candidate states and positive references, this lower limit
    # keeps every acceptance residual inside the substrate's finite budget.
    if 0.0 < value < 1e-60:
        raise ValueError(f"A nonzero {label} must be at least 1e-60")
    return value


def _utc(value) -> None:
    if value is None:
        return
    if (type(value) is not str or len(value) > 40
            or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
                value,
            ) is None):
        raise ValueError("valid_time_utc must be an ISO UTC timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid valid_time_utc timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("valid_time_utc must be UTC")


def _url(value) -> None:
    if value is None:
        return
    if (type(value) is not str or not 1 <= len(value) <= 2048
            or any(character.isspace() or ord(character) < 32 or ord(character) == 127
                   for character in value)):
        raise ValueError("source_url must be a bounded HTTP(S) URL or null")
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                 and parsed.username is None and parsed.password is None)
        parsed.port  # Reject malformed declared ports without fetching a URL.
    except ValueError as exc:
        raise ValueError("Malformed source_url") from exc
    if not valid:
        raise ValueError("source_url must declare HTTP(S), a host and no credentials")


def validate_reference(reference: dict) -> dict:
    """Validate a sealed bounded declaration without fetching or authenticating it."""
    keys(reference, {"schema", "provenance", "context", "observations", "record_digest"})
    if reference["schema"] != REFERENCE_SCHEMA:
        raise ValueError("Unsupported atmospheric reference schema")
    provenance = reference["provenance"]
    keys(provenance, {"kind", "source_ref", "source_url", "independent_of_candidate"})
    kind = provenance["kind"]
    if type(kind) is not str or kind not in {
        "synthetic_fixture", "published_reference", "declared_measurements"
    }:
        raise ValueError("Declare synthetic, published or measurement reference provenance")
    _text(provenance["source_ref"], "source_ref", 160)
    _url(provenance["source_url"])
    if type(provenance["independent_of_candidate"]) is not bool:
        raise ValueError("Reference independence must be a boolean declaration")
    context = reference["context"]
    keys(context, {"frame", "height_origin_m", "valid_time_utc", "humidity_convention"})
    _text(context["frame"], "reference frame", 160)
    _bounded(context["height_origin_m"], -500.0, 10000.0, "height_origin_m")
    _utc(context["valid_time_utc"])
    if (type(context["humidity_convention"]) is not str
            or context["humidity_convention"] not in HUMIDITY_CONVENTIONS):
        raise ValueError("Declare an explicit supported humidity convention")
    if kind == "declared_measurements" and context["valid_time_utc"] is None:
        raise ValueError("Declared measurements require a nonnull UTC context time")
    observations = reference["observations"]
    if type(observations) is not list or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise ValueError("Require 1..129 atmospheric reference observations")
    previous = -1
    for observation in observations:
        keys(observation, {"sample_index", "height_m", "quantities"})
        index = observation["sample_index"]
        if type(index) is not int or not 0 <= index <= 128 or index <= previous:
            raise ValueError("Reference sample indices must be unique, strictly increasing integers")
        previous = index
        _bounded(observation["height_m"], 0.0, 11000.0, "height_m")
        quantities = observation["quantities"]
        if (type(quantities) is not dict or not quantities
                or not set(quantities).issubset(FIELD_UNITS)):
            raise ValueError("Reference quantities must be a nonempty bounded SI field subset")
        if ("relative_humidity" in quantities
                and context["humidity_convention"] == "not_applicable"):
            raise ValueError("Relative humidity observations require a declared humidity convention")
        for field, datum in quantities.items():
            keys(datum, {"value", "unit", "uncertainty", "instrument_ref", "calibration_ref"})
            measured = _bounded(datum["value"], *FIELD_BOUNDS[field], field)
            if 0.0 < measured < 1e-20:
                raise ValueError("Nonzero reference quantities must be at least 1e-20")
            if datum["unit"] != FIELD_UNITS[field]:
                raise ValueError("Atmospheric reference quantities require exact SI units")
            uncertainty = datum["uncertainty"]
            keys(uncertainty, {"kind", "absolute_bound", "coverage_factor", "reference"})
            uncertainty_kind = uncertainty["kind"]
            if type(uncertainty_kind) is not str or uncertainty_kind not in {
                "declared_expanded", "declared_absolute_bound", "rounding_bound", "exact_fixture"
            }:
                raise ValueError("Declare the reference uncertainty bound interpretation")
            bound = _nonnegative(uncertainty["absolute_bound"], 1e9, "absolute_bound")
            _text(uncertainty["reference"], "uncertainty reference")
            if uncertainty_kind == "declared_expanded":
                _bounded(uncertainty["coverage_factor"], 1e-20, 10.0, "coverage_factor")
            elif uncertainty["coverage_factor"] is not None:
                raise ValueError("Only declared_expanded uncertainty has a coverage factor")
            if uncertainty_kind == "exact_fixture":
                if kind != "synthetic_fixture" or bound != 0.0:
                    raise ValueError("Only synthetic exact fixtures can declare a zero exact bound")
            elif uncertainty_kind == "rounding_bound" and kind != "published_reference":
                raise ValueError("Rounding bounds require published reference provenance")
            for name in ("instrument_ref", "calibration_ref"):
                if datum[name] is not None:
                    _text(datum[name], name)
            if kind == "declared_measurements":
                if bound == 0.0 or datum["instrument_ref"] is None:
                    raise ValueError("Measurements require nonzero uncertainty and an instrument reference")
    check_seal(reference)
    return deepcopy(reference)


def reference_fields(reference: dict) -> set[str]:
    return {field for observation in reference["observations"] for field in observation["quantities"]}


def validate_policy(reference: dict, policy: dict) -> dict:
    reference = validate_reference(reference)
    keys(policy, {"schema", "rule", "thresholds", "record_digest"})
    if policy["schema"] != POLICY_SCHEMA or policy["rule"] != RULE:
        raise ValueError("Unsupported atmospheric comparison policy or rule")
    keys(policy["thresholds"], reference_fields(reference))
    for thresholds in policy["thresholds"].values():
        keys(thresholds, {"absolute_tolerance", "relative_tolerance"})
        _nonnegative(thresholds["absolute_tolerance"], 1e6, "absolute_tolerance")
        _nonnegative(thresholds["relative_tolerance"], 0.05, "relative_tolerance")
    check_seal(policy)
    return deepcopy(policy)


def validate_bindings(bindings: dict) -> dict:
    keys(bindings, BINDING_KEYS)
    for name in ("source_evidence_id", "source_record_digest", "recomputed_report_digest",
                 "reference_evidence_id"):
        content_ref(bindings[name])
    for name, kind in (("source_result_id", "result"), ("source_execution_id", "execution"),
                       ("verification_id", "verification")):
        if type(bindings[name]) is not str:
            raise ValueError("Comparison occurrence identities must be exact strings")
        validate_identity(bindings[name], kind)
    return deepcopy(bindings)


def validate_inputs(request: dict, result: dict, reference: dict, policy: dict,
                    bindings: dict) -> tuple[dict, dict, dict, dict, dict]:
    """Validate content and fixed profiles; do not execute a physical provider."""
    if type(request) is not dict:
        raise ValueError("Require an atmospheric request object")
    schema = request.get("schema")
    if schema == dry.REQUEST_SCHEMA:
        contract = dry
    elif schema == moist.REQUEST_SCHEMA:
        contract = moist
    else:
        raise ValueError("Unsupported atmospheric request schema")
    request = contract.validate_request(request)
    result = contract.validate_result(request, result)
    reference = validate_reference(reference)
    policy = validate_policy(reference, policy)
    bindings = validate_bindings(bindings)
    if bindings["reference_evidence_id"] != make_reference_source(reference)["evidence_id"]:
        raise ValueError("Comparison reference evidence binding differs from retained content")
    return request, result, reference, policy, bindings


def make_reference_source(reference: dict) -> dict:
    """Capture a reference artifact as evidence, without treating height as time."""
    reference = validate_reference(reference)
    frame = reference["context"]["frame"]
    manifest = InstrumentManifest(
        instrument_id="atmosphere-reference-declaration.v1",
        role="declared_reference_artifact", units={"reference_record_declaration": "1"},
        frames=(frame,),
        sampling={"kind": "one_reference_artifact_declaration",
                  "time_semantics": "synthetic_selection_envelope"},
        supported_operations=("atmosphere.compare.v1", "atmosphere.compare-verify.v1"),
        calibration_requirements={"calibration_certification": "none"},
    )
    source = {
        "run_schema": "run.v1", "run_id": "run-atmosphere-reference-" + digest(reference)[7:23],
        "instrument": manifest.instrument_id,
        "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                     "coordinate_frame": frame, "manifest": manifest.to_dict(),
                     "reference": reference,
                     "provenance": {"source": "declared reference artifact; not an acquired sensor stream",
                                    "generator": "ciw.atmosphere_comparison_contract.make_reference_source",
                                    "generator_version": 1}},
        "time_s": [0.0],
        "channels": {"reference_record_declaration": {"unit": "1", "values": [1.0]}},
        "render": {},
    }
    source["evidence_id"] = evidence_id(source)
    validate_run_structure(source)
    validate_evidence_identity(source)
    return source


def reference_from_source(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    reference = validate_reference(source["metadata"].get("reference"))
    if digest(source) != digest(make_reference_source(reference)):
        raise ValueError("Reference evidence must retain the exact declared reference artifact")
    return reference


def example_reference(request: dict) -> dict:
    """Declare origin T/p only; this fixture never samples a generated profile."""
    if type(request) is not dict:
        raise ValueError("Require an atmospheric request object")
    if request.get("schema") == dry.REQUEST_SCHEMA:
        request = dry.validate_request(request)
    elif request.get("schema") == moist.REQUEST_SCHEMA:
        request = moist.validate_request(request)
    else:
        raise ValueError("Unsupported atmospheric request schema")
    origin = request["reference"]
    quantities = {}
    for field in ("temperature_k", "pressure_pa"):
        quantities[field] = {
            "value": origin[field], "unit": FIELD_UNITS[field],
            "uncertainty": {"kind": "exact_fixture", "absolute_bound": 0.0,
                            "coverage_factor": None,
                            "reference": "Declared reference configuration; synthetic lifecycle fixture."},
            "instrument_ref": None, "calibration_ref": None,
        }
    return validate_reference(seal({
        "schema": REFERENCE_SCHEMA,
        "provenance": {"kind": "synthetic_fixture", "source_ref": "atmosphere.reference-example",
                       "source_url": None, "independent_of_candidate": False},
        "context": {"frame": origin["frame"], "height_origin_m": origin["height_origin_m"],
                    "valid_time_utc": origin["context"]["valid_time_utc"],
                    "humidity_convention": "not_applicable"},
        "observations": [{"sample_index": 0, "height_m": 0.0, "quantities": quantities}],
    }))


def example_policy(reference: dict) -> dict:
    reference = validate_reference(reference)
    allowances = {"temperature_k": 1.0, "pressure_pa": 100.0,
                  "density_kg_per_m3": 0.01, "water_vapour_pressure_pa": 10.0,
                  "relative_humidity": 0.01, "liquid_water_saturation_pressure_pa": 10.0}
    return validate_policy(reference, seal({
        "schema": POLICY_SCHEMA, "rule": RULE,
        "thresholds": {field: {"absolute_tolerance": allowances[field], "relative_tolerance": 0.0}
                       for field in sorted(reference_fields(reference))},
    }))
