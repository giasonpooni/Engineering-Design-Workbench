"""Retained thermal mathematics -> recheckable, read-only display data.

The thermal provider still owns inference and sensor selection. This adapter
adds bounded covariance geometry and innovation whitening for inspection.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

import numpy as np

from . import uncertainty_display as algebra
from .control_contracts import _base, bytes_ref, content_ref, json_tree, keys, number, save_new, text
from .operations.runner import seal
from .scientific_observations import SCHEMA as VIEW_SCHEMA, validate_view
from .session import loads_json
from .telemetry import canonical

SCHEMA = "ciw.thermal-math-inspection.v1"
INFORMATION_SCHEMA = "ciw.thermal-math-inspection.v2"
MAX_SOURCE_BYTES = 65536
POLICY = {"profile": algebra.PROFILE, "contour_segments": algebra.CONTOUR_SEGMENTS,
          "condition_limit": algebra.CONDITION_LIMIT, "radius_options": [1, 2, 3],
          "contours": "Mahalanobis_radius_not_coverage_probability",
          "bands": "marginal_standard_deviations_not_simultaneous_confidence",
          "whitening_basis": "lower_Cholesky_in_retained_active_sensor_order",
          "derived_rtol": 1e-10, "derived_atol": 1e-12}
AUTHORITY = {"kind": "derived_numerical_display", "read_only": True,
             "new_estimator_execution": "not_performed", "verification_id": None,
             "state_admission": "not_performed", "physical_validation": "not_established",
             "statistical_coverage": "not_established", "source_authentication": "not_established_by_hashes",
             "cross_tick_covariance": "not_supplied"}


def _parse(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        raise ValueError("Math inspection requires 1..65536 exact input bytes")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    if type(value) is not dict or value.get("schema") != VIEW_SCHEMA:
        raise ValueError("This mathematical inspector accepts a retained thermal observation view")
    validate_view(value)
    return value


def _project(view: dict) -> tuple[dict, list]:
    step = view["native_step"]
    request, native = step["request"], step["result"]["data"]
    rows = native["observer"]["trace"]
    if not 1 <= len(rows) <= 128:
        raise ValueError("Display supports one to 128 retained thermal ticks")
    retained = {"binding": view["binding"], "entity_id": view["entity_id"],
                "execution_id": step["execution_id"], "result_id": step["result_id"],
                "source_stage": view["stage"], "coordinate_order": view["coordinate_order"],
                "time_basis": view["time_basis"],
                "clock_id": view["stream"]["observations"][0]["clock"]["id"],
                "time_s": [(i + 1) * request["sample_interval_s"] for i in range(len(rows))],
                "frame": view["stream"]["observations"][0]["frame"], "unit": "K",
                "measurements": request["observations"], "inputs": request["inputs"],
                "model": native["model"], "parameters": request["model"],
                "observation_noise_covariance": request["observation_noise_covariance"],
                "noise_assumption": native["observer"]["noise_assumption"],
                "trace": rows, "selection": native["selection"],
                "selection_policy": request["selection"]}
    diagnostics = []
    for row in rows:
        predicted = algebra.covariance_geometry(row["predicted_covariance"])
        posterior = algebra.covariance_geometry(row["posterior_covariance"])
        whitened = algebra.whiten_innovation(row["innovation"], row["innovation_covariance"])
        if whitened["status"] == "available" and not math.isclose(
                whitened["squared_norm"], number(row["nis"]), rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("Whitened innovation norm contradicts the retained native NIS")
        diagnostics.append({"predicted": predicted, "posterior": posterior, "whitened": whitened,
            "conditioning_gain_nats": algebra.conditioning_gain(predicted, posterior),
            "update_delta_k": [number(b - a) for a, b in zip(row["predicted_mean"], row["posterior_mean"])]})
    return deepcopy(retained), diagnostics


def analyze(raw: bytes, *, expected_sha256: str) -> dict:
    """Explicit derived numerical display, not a new inference/verification occurrence."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        raise ValueError("Math inspection requires 1..65536 exact input bytes")
    content_ref(expected_sha256)
    if type(raw) is not bytes or bytes_ref(raw) != expected_sha256:
        raise ValueError("Math source differs from the selected SHA256")
    view = _parse(raw)
    retained, derived = _project(view)
    return seal({"schema": SCHEMA,
        "source": {"schema": VIEW_SCHEMA, "sha256": expected_sha256, "utf8": raw.decode("utf-8")},
        "policy": deepcopy(POLICY), "retained": retained, "derived": derived,
        "producer": {"profile": algebra.PROFILE, "numpy_version": np.__version__,
                     "display_kernel_sha256": bytes_ref(Path(algebra.__file__).read_bytes().replace(b'\r\n', b'\n'))},
        "authority": deepcopy(AUTHORITY)})


def _derived_equal(actual, expected) -> None:
    if type(expected) is dict:
        keys(actual, set(expected))
        for key in expected:
            _derived_equal(actual[key], expected[key])
    elif type(expected) is list:
        if type(actual) is not list or len(actual) != len(expected):
            raise ValueError("Derived display dimensions differ")
        for a, b in zip(actual, expected):
            _derived_equal(a, b)
    elif type(expected) is int:
        if type(actual) is not int or actual != expected:
            raise ValueError("Derived display integer structure differs")
    elif type(expected) is float:
        if not math.isclose(number(actual), expected, rel_tol=POLICY["derived_rtol"], abs_tol=POLICY["derived_atol"]):
            raise ValueError("Derived display mathematics contradicts its source")
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("Derived display semantics differ")


def validate_report(value: dict) -> None:
    if type(value) is dict and value.get("schema") == INFORMATION_SCHEMA:
        _validate_information_report(value)
        return
    _base(value, "thermal-math-inspection", {"source", "policy", "retained", "derived", "producer", "authority"})
    if canonical(value["authority"]) != canonical(AUTHORITY) or canonical(value["policy"]) != canonical(POLICY):
        raise ValueError("Display policy or authority cannot be changed")
    keys(value["source"], {"schema", "sha256", "utf8"})
    source = value["source"]
    content_ref(source["sha256"])
    if type(source["utf8"]) is not str or source["schema"] != VIEW_SCHEMA:
        raise ValueError("Missing retained source text/schema")
    raw = source["utf8"].encode("utf-8")
    if bytes_ref(raw) != source["sha256"]:
        raise ValueError("Retained source bytes contradict their digest")
    view = _parse(raw)
    keys(value["producer"], {"profile", "numpy_version", "display_kernel_sha256"})
    if value["producer"]["profile"] != algebra.PROFILE:
        raise ValueError("Unsupported display algorithm profile")
    text(value["producer"]["numpy_version"])
    content_ref(value["producer"]["display_kernel_sha256"])
    retained, derived = _project(view)
    if canonical(value["retained"]) != canonical(retained):
        raise ValueError("Retained mathematical context differs from the original source")
    _derived_equal(value["derived"], derived)



def _information(retained: dict) -> dict:
    from . import information_display as info
    rows = [info.contraction_geometry(row["predicted_covariance"], row["posterior_covariance"])
            for row in retained["trace"]]
    forecast = []
    for candidate in retained["selection"]["candidates"]:
        geometry = info.contraction_geometry(retained["selection"]["prior_covariance"],
                                             candidate["posterior_covariance"])
        if geometry["status"] == "available" and not math.isclose(
                geometry["information_gain_nats"], number(candidate["information_gain_nats"]),
                rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("Covariance contraction contradicts the native sensor information score")
        forecast.append({"mask": candidate["mask"], "geometry": geometry})
    return {"profile": info.PROFILE, "basis": "prior_lower_Cholesky_coordinates_not_sensor_axes",
        "direction_samples": info.DIRECTION_SAMPLES, "relation_tolerance": info.RELATION_TOLERANCE,
        "scope": "retained_covariance_pairs_only; no_new_inference_or_selection",
        "rows": rows, "forecast": forecast}


def analyze_information(raw: bytes, *, expected_sha256: str) -> dict:
    """Opt-in v2 superset. The default v1 report and its reader remain supported."""
    value = analyze(raw, expected_sha256=expected_sha256)
    value["schema"] = INFORMATION_SCHEMA
    value["information"] = _information(value["retained"])
    from . import information_display as info
    value["information"]["producer"] = {
        "kernel_sha256": bytes_ref(Path(info.__file__).read_bytes().replace(b'\r\n', b'\n')),
        "numpy_version": np.__version__}
    return seal(value)


def _validate_information_report(value: dict) -> None:
    from .operations.runner import check_seal
    json_tree(value)
    keys(value, {"schema", "source", "policy", "retained", "derived", "producer", "authority",
                 "information", "record_digest"})
    check_seal(value)
    # Validate every v1 field through the unchanged reader, never through a relaxed subset.
    base = deepcopy(value)
    base.pop("information")
    base["schema"] = SCHEMA
    seal(base)
    validate_report(base)
    expected = _information(value["retained"])
    keys(value["information"], set(expected) | {"producer"})
    producer = value["information"]["producer"]
    keys(producer, {"kernel_sha256", "numpy_version"})
    content_ref(producer["kernel_sha256"])
    text(producer["numpy_version"])
    _derived_equal({k: v for k, v in value["information"].items() if k != "producer"}, expected)


def analyze_file(path: Path, *, expected_sha256: str, information_geometry: bool = False) -> dict:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    operation = analyze_information if information_geometry else analyze
    return operation(raw, expected_sha256=expected_sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net math", description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--information-geometry", action="store_true", help="Add prior-normalized conditioning and sensor-candidate geometry (v2)")
    args = parser.parse_args(argv)
    try:
        value = analyze_file(args.source, expected_sha256=args.expected_sha256, information_geometry=args.information_geometry)
        save_new(args.output, value)
        print(json.dumps({"schema": value["schema"], "output": str(args.output), "samples": len(value["derived"]),
                          "record_digest": value["record_digest"], "authority": value["authority"]}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
