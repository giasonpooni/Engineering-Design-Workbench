"""Bounded declared temperature-processing inputs; no physical qualification.

The canonical observation commitment identifies the submitted JSON declaration,
not the original instrument acquisition bytes. All evidence references and
applicability statements are declarations whose physical truth is not checked.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import content_ref, detached, keys, number, text
from .core.covariance import _validate_matrix
from .core.identities import canonical_json
from .operations.runner import digest

SCHEMA = "ciw.temperature-processing-request.v1"
REPORT_SCHEMA = "ciw.temperature-processing-report.v1"
MAX_SAMPLES = 64
MAX_BYTES = 2 * 1024 * 1024
AUTHORITY = {
    "physical_qualification": "not_established",
    "calibration_traceability": "not_established",
    "origin_authentication": "not_established",
    "proof": "not_generated",
    "model_inference": "not_run",
}
NUMERICAL_CONTRACT = {
    "id": "net.temperature.affine-first-order.v1",
    "arithmetic": "binary64; ordered math.fsum products; math.sqrt standard uncertainties",
    "transformation": "T_i = gain * raw_i + offset_K",
    "propagation": "J C_joint J^T + sum(C_independent_K2)",
    "approximation": "first-order Taylor propagation; product second-order terms not included",
    "axes": "raw:<sample_id> in acquisition order, gain, offset_K",
    "additional_sources": "declared independent of joint inputs and each other",
    "covariance_validation": "exact symmetry; dimensionless PSD tolerance 1e-10; no repair",
    "invalid_samples": "retained; derived values and covariance rows/columns unavailable",
    "acceptance": "Outward-rounded closed interval containment of reported binary64 value +/- k*u; k is not a coverage probability",
    "acceptance_rounding": "Exact rational endpoints from reported binary64 value/u/k, then outward binary64 rounding; does not enclose previous propagation roundoff",
    "acceptance_scope": "Submitted sample instants only; no guarantee of continuous-cycle temperatures, excursions or peaks between samples",
    "maximum_samples": MAX_SAMPLES,
    "byte_commitment": "UTF-8 CIW canonical JSON of raw_observations; not acquisition file bytes",
}
BUDGET_CATEGORIES = (
    "reference", "calibration_fit", "resolution", "repeatability", "drift",
    "environment", "timing", "installation", "model_discrepancy",
)


def _bounded(value):
    result = number(value)
    if abs(result) > 1e12:
        raise ValueError("Temperature contract scalar exceeds 1e12 bound")
    return result


def _interval(value, *, positive=False):
    if type(value) is not list or len(value) != 2:
        raise ValueError("Require a two-number closed interval")
    low, high = map(_bounded, value)
    if low >= high or positive and low <= 0:
        raise ValueError("Invalid ordered applicability interval")


def _strings(value, *, nonempty=True):
    if type(value) is not list or len(value) > 64 or nonempty and not value:
        raise ValueError("Require a bounded declaration list")
    for item in value:
        text(item)
    if len(set(value)) != len(value):
        raise ValueError("Duplicate declared identity")


def _covariance(value, size):
    if type(value) is not list or len(value) != size:
        raise ValueError("Covariance size differs from explicit sample order")
    for row in value:
        if type(row) is not list or len(row) != size:
            raise ValueError("Require a full square covariance matrix")
        for entry in row:
            number(entry)
            if abs(entry) > 1e24:
                raise ValueError("Covariance entry exceeds numerical bound")
    if any(value[i][j] != value[j][i] for i in range(size) for j in range(size)):
        raise ValueError("Covariance must be exactly symmetric; no repair is performed")
    _validate_matrix(value, size)


def covariance_order(request):
    return ["raw:" + row["sample_id"] for row in request["raw_observations"]["samples"]] + ["gain", "offset_K"]


def _source(value, source_ids, dependencies):
    sid = text(value["source_id"])
    if sid in source_ids:
        raise ValueError("Duplicate uncertainty source identity")
    source_ids.add(sid)
    _strings(value["dependency_ids"])
    if dependencies.intersection(value["dependency_ids"]):
        raise ValueError("Uncertainty dependencies overlap: possible double-counting or unsupported correlation")
    dependencies.update(value["dependency_ids"])
    content_ref(value["evidence_ref"])


def validate_request(value: dict) -> dict:
    """Validate declarations without inferring calibration or physical authority."""
    keys(value, {"schema", "source_kind", "identity", "clock", "conditions", "raw_observations",
                 "calibration", "joint_covariance", "contributions", "budget", "installed_correction", "acceptance"})
    request = detached(value)
    if len(canonical_json(request).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Temperature request exceeds 2 MiB")
    if request["schema"] != SCHEMA or request["source_kind"] not in {"synthetic", "retained_observation"}:
        raise ValueError("Require temperature schema and explicit observation source kind")
    identity = request["identity"]
    keys(identity, {"cycle_id", "material_id", "specimen_id", "sensor_id", "readout_id", "installation_id", "location_id", "clock_id"})
    for item in identity.values():
        text(item)
    clock = request["clock"]
    keys(clock, {"id", "start_s", "end_s", "max_latency_s"})
    text(clock["id"])
    start, end, latency = (_bounded(clock[key]) for key in ("start_s", "end_s", "max_latency_s"))
    if clock["id"] != identity["clock_id"] or not 0 <= start < end or latency < 0:
        raise ValueError("Require aligned bounded cycle clock and nonnegative latency limit")
    conditions = request["conditions"]
    keys(conditions, {"ambient_temperature_K", "maximum_heating_rate_K_s"})
    if _bounded(conditions["ambient_temperature_K"]) <= 0 or _bounded(conditions["maximum_heating_rate_K_s"]) < 0:
        raise ValueError("Require positive ambient temperature and nonnegative maximum heating rate")
    raw = request["raw_observations"]
    keys(raw, {"unit", "samples"})
    if raw["unit"] not in {"V", "mV", "ohm", "count", "K"}:
        raise ValueError("Unsupported raw unit; units are never implicitly converted")
    samples = raw["samples"]
    if type(samples) is not list or not 1 <= len(samples) <= MAX_SAMPLES:
        raise ValueError("Require 1..64 retained observation samples")
    ids, previous = set(), None
    for sample in samples:
        keys(sample, {"sample_id", "time_s", "received_time_s", "value", "status"})
        sid = text(sample["sample_id"])
        stamp, receipt = (_bounded(sample[key]) for key in ("time_s", "received_time_s"))
        if sid in ids or not start <= stamp <= end or previous is not None and stamp <= previous:
            raise ValueError("Require unique sample IDs and strictly increasing cycle times")
        if receipt < stamp:
            raise ValueError("Receipt cannot precede acquisition on the declared aligned clock")
        if sample["status"] not in {"ok", "missing", "saturated", "invalid"}:
            raise ValueError("Unsupported acquisition status")
        if sample["value"] is None:
            if sample["status"] not in {"missing", "invalid"}:
                raise ValueError("Null observations require missing or invalid status")
        else:
            _bounded(sample["value"])
            if sample["status"] == "missing":
                raise ValueError("A missing observation must have a null value")
            if raw["unit"] == "count" and sample["value"] != int(sample["value"]):
                raise ValueError("Raw count observations must be integral")
        ids.add(sid)
        previous = stamp
    n = len(samples)
    calibration = request["calibration"]
    keys(calibration, {"calibration_id", "transformation", "input_unit", "output_unit", "gain", "offset_K",
                       "coefficient_covariance", "sensor_id", "readout_id", "clock_id", "valid_time_s", "input_range",
                       "output_range_K", "ambient_range_K", "heating_rate_range_K_s", "reference_refs"})
    text(calibration["calibration_id"])
    if calibration["transformation"] != "affine" or calibration["input_unit"] != raw["unit"] or calibration["output_unit"] != "K":
        raise ValueError("Require explicit affine calibration with matching input unit and K output")
    if _bounded(calibration["gain"]) == 0:
        raise ValueError("Calibration gain cannot be zero")
    _bounded(calibration["offset_K"])
    for key in ("sensor_id", "readout_id", "clock_id"):
        text(calibration[key])
    for key in ("valid_time_s", "input_range", "output_range_K", "ambient_range_K", "heating_rate_range_K_s"):
        _interval(calibration[key], positive=key in {"output_range_K", "ambient_range_K"})
    _covariance(calibration["coefficient_covariance"], 2)
    _strings(calibration["reference_refs"], nonempty=False)
    for ref in calibration["reference_refs"]:
        content_ref(ref)
    joint = request["joint_covariance"]
    keys(joint, {"source_id", "order", "matrix", "dependency_ids", "evidence_ref", "cross_covariance_policy"})
    if joint["order"] != covariance_order(request):
        raise ValueError("Joint covariance order differs from raw observations, gain and offset")
    if joint["cross_covariance_policy"] not in {"declared", "declared_zero"}:
        raise ValueError("Unknown joint cross-covariance cannot be silently zeroed")
    _covariance(joint["matrix"], n + 2)
    if [row[-2:] for row in joint["matrix"][-2:]] != calibration["coefficient_covariance"]:
        raise ValueError("Joint calibration block differs from coefficient covariance")
    if joint["cross_covariance_policy"] == "declared_zero" and any(joint["matrix"][i][j] != 0 for i in range(n + 2) for j in range(n + 2) if i != j):
        raise ValueError("Declared-zero covariance contradicts supplied cross terms")
    source_ids, dependencies = set(), set()
    _source(joint, source_ids, dependencies)
    contributions = request["contributions"]
    if type(contributions) is not list or len(contributions) > 16:
        raise ValueError("At most 16 explicitly independent added contributions")
    for contribution in contributions:
        keys(contribution, {"source_id", "dependency_ids", "evidence_ref", "correlation_policy", "covariance_K2"})
        if contribution["correlation_policy"] != "independent_of_all_other_sources":
            raise ValueError("Unsupported cross-source correlation in this profile; requires another joint model")
        _source(contribution, source_ids, dependencies)
        _covariance(contribution["covariance_K2"], n)
    correction = request["installed_correction"]
    if correction is not None:
        keys(correction, {"source_id", "dependency_ids", "evidence_ref", "correlation_policy", "offsets_K", "covariance_K2",
                          "installation_id", "location_id", "material_id", "specimen_id", "valid_time_s",
                          "ambient_range_K", "heating_rate_range_K_s"})
        if correction["correlation_policy"] != "independent_of_all_other_sources":
            raise ValueError("Installed correction must declare independence; shared dependencies are unsupported")
        _source(correction, source_ids, dependencies)
        if type(correction["offsets_K"]) is not list or len(correction["offsets_K"]) != n:
            raise ValueError("Installed correction must preserve the complete sample order")
        for offset in correction["offsets_K"]:
            _bounded(offset)
        _covariance(correction["covariance_K2"], n)
        for key in ("installation_id", "location_id", "material_id", "specimen_id"):
            text(correction[key])
        for key in ("valid_time_s", "ambient_range_K", "heating_rate_range_K_s"):
            _interval(correction[key], positive=key == "ambient_range_K")
    budget = request["budget"]
    if type(budget) is not list or len(budget) > len(BUDGET_CATEGORIES):
        raise ValueError("Require a bounded budget declaration")
    categories, allocated = set(), set()
    for item in budget:
        keys(item, {"category", "status", "source_ids", "reason", "evidence_ref"})
        if item["category"] not in BUDGET_CATEGORIES or item["category"] in categories:
            raise ValueError("Unknown or duplicate uncertainty budget category")
        categories.add(item["category"])
        if item["status"] not in {"included", "not_applicable", "omitted"}:
            raise ValueError("Unknown uncertainty budget status")
        text(item["reason"])
        _strings(item["source_ids"], nonempty=item["status"] == "included")
        if not set(item["source_ids"]) <= source_ids or item["status"] != "included" and item["source_ids"]:
            raise ValueError("Budget allocation must refer to included sources exactly")
        allocated.update(item["source_ids"])
        if item["evidence_ref"] is None:
            if item["status"] != "omitted":
                raise ValueError("Included/not-applicable budget declarations need an evidence reference")
        else:
            content_ref(item["evidence_ref"])
    if allocated != source_ids:
        raise ValueError("Every covariance source must be allocated to the uncertainty budget")
    policy = request["acceptance"]
    if policy is not None:
        keys(policy, {"policy_id", "quantity", "unit", "lower", "upper", "coverage_factor", "rule", "evidence_ref"})
        text(policy["policy_id"])
        if policy["quantity"] not in {"calibrated_sensor_temperature", "polymer_temperature"} or policy["unit"] != "K":
            raise ValueError("Acceptance must name the exact temperature quantity in K")
        low, high, factor = (_bounded(policy[key]) for key in ("lower", "upper", "coverage_factor"))
        if not 0 < low < high or not 1 <= factor <= 6 or policy["rule"] != "uncertainty_interval_contained":
            raise ValueError("Require positive closed acceptance bounds and multiplier in [1,6]")
        content_ref(policy["evidence_ref"])
    return request


def example_request() -> dict:
    """Synthetic software fixture, never a proposed hardware calibration."""
    synthetic = digest({"synthetic_temperature_fixture": 1})
    identity = {key: "synthetic." + key for key in ("cycle_id", "material_id", "specimen_id", "sensor_id", "readout_id", "installation_id", "location_id", "clock_id")}
    samples = [{"sample_id": "s0", "time_s": 0.0, "received_time_s": 0.1, "value": 1.0, "status": "ok"},
               {"sample_id": "s1", "time_s": 1.0, "received_time_s": 1.1, "value": 2.0, "status": "ok"}]
    budget = [{"category": category, "status": "included", "source_ids": ["joint"],
               "reason": "Synthetic covariance allocation; no real evidence", "evidence_ref": synthetic}
              for category in ("reference", "calibration_fit", "resolution", "repeatability")]
    budget += [{"category": category, "status": "omitted", "source_ids": [],
                "reason": "No installed-chain evidence supplied", "evidence_ref": None}
               for category in BUDGET_CATEGORIES[4:]]
    request = {
        "schema": SCHEMA, "source_kind": "synthetic", "identity": identity,
        "clock": {"id": identity["clock_id"], "start_s": 0.0, "end_s": 1.0, "max_latency_s": 0.5},
        "conditions": {"ambient_temperature_K": 295.0, "maximum_heating_rate_K_s": 10.0},
        "raw_observations": {"unit": "V", "samples": samples},
        "calibration": {"calibration_id": "synthetic.linear-calibration", "transformation": "affine", "input_unit": "V",
                        "output_unit": "K", "gain": 10.0, "offset_K": 290.0, "coefficient_covariance": [[0.04, 0.0], [0.0, 0.25]],
                        "sensor_id": identity["sensor_id"], "readout_id": identity["readout_id"], "clock_id": identity["clock_id"],
                        "valid_time_s": [0.0, 100.0], "input_range": [0.0, 5.0], "output_range_K": [280.0, 350.0],
                        "ambient_range_K": [290.0, 300.0], "heating_rate_range_K_s": [0.0, 20.0], "reference_refs": []},
        "joint_covariance": {"source_id": "joint", "order": ["raw:s0", "raw:s1", "gain", "offset_K"],
                             "matrix": [[0.0001, 0.0, 0.0, 0.0], [0.0, 0.0001, 0.0, 0.0], [0.0, 0.0, 0.04, 0.0], [0.0, 0.0, 0.0, 0.25]],
                             "dependency_ids": ["synthetic.raw-noise", "synthetic.coefficients"], "evidence_ref": synthetic,
                             "cross_covariance_policy": "declared_zero"},
        "contributions": [], "budget": budget, "installed_correction": None,
        "acceptance": {"policy_id": "synthetic.temperature-interval", "quantity": "calibrated_sensor_temperature", "unit": "K",
                       "lower": 295.0, "upper": 315.0, "coverage_factor": 2.0, "rule": "uncertainty_interval_contained", "evidence_ref": synthetic},
    }
    return validate_request(request)
