"""Declare the bounded calibrated, time-aligned two-reservoir experiment.

FSRT owns the process case and validates its topology. Numerical clock,
calibration, observability, estimation, reconciliation and fault operations stay
in their respective repositories and are orchestrated by CIW.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import sys

import numpy as np

OPERATION_ID = "fsrt.declare-calibrated-two-channel.v1"
EXPERIMENT_SCHEMA = "fsrt.calibrated-observable-two-channel.v1"
RESULT_SCHEMA = "fsrt.calibrated-observable-declaration.v1"
RESPONSE_SCHEMA = "ciw.adapter-response.v1"
MAX_REQUEST_BYTES = 1_000_000


class DeclarationRefusal(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _refuse(condition: bool, message: str, code: str = "invalid_experiment") -> None:
    if not condition:
        raise DeclarationRefusal(code, message)


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _identities(value: object) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
            and len(set(value)) == len(value))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def experiment_digest(experiment: dict) -> str:
    return "sha256:" + sha256(EXPERIMENT_SCHEMA.encode() + b"\0" + _canonical(experiment)).hexdigest()


def validate_experiment(value: object) -> dict:
    _refuse(isinstance(value, dict), "experiment must be an object")
    required = {"schema", "experiment_id", "claim_scope", "epoch_utc", "channels",
                "calibrated_covariance", "configuration"}
    _refuse(set(value) == required, "experiment fields must match the fixed v1 declaration")
    _refuse(value["schema"] == EXPERIMENT_SCHEMA, "unsupported experiment schema")
    for field in ("experiment_id", "claim_scope", "epoch_utc"):
        _refuse(isinstance(value[field], str) and value[field].strip(), f"{field} must be nonempty")
    channels = value["channels"]
    _refuse(isinstance(channels, list) and len(channels) == 2,
            "the v1 process case requires exactly two channels")
    ids = []
    reference_frames = []
    for index, channel in enumerate(channels):
        _refuse(isinstance(channel, dict) and set(channel) == {
            "channel_id", "observation", "clock_model", "clock_joint_covariance",
            "calibration_profile", "calibration_joint_covariance",
        }, f"channel {index} has invalid fields")
        _refuse(isinstance(channel["channel_id"], str) and channel["channel_id"].strip(),
                "channel identities must be nonempty strings")
        ids.append(channel["channel_id"])
        observation = channel["observation"]
        _refuse(isinstance(observation, dict) and all(key in observation for key in (
            "observation_id", "artifact_id", "sensor_id", "quantity_id", "unit",
            "device_time", "clock_frame", "indicated_value", "raw_value",
        )), "raw observation is incomplete")
        _refuse(all(_finite(observation[key]) for key in ("device_time", "indicated_value", "raw_value")),
                "raw observation numbers must be finite")
        _refuse(all(isinstance(observation[key], str) and observation[key].strip() for key in (
            "observation_id", "artifact_id", "sensor_id", "quantity_id", "unit",
        )), "raw observation identities and unit must be nonempty strings")
        clock = channel["clock_model"]
        _refuse(isinstance(clock, dict) and _identities(clock.get("synchronization_evidence_ids")),
                "each channel requires synchronization evidence", "missing_clock_mapping")
        raw_frame = observation["clock_frame"]
        _refuse(isinstance(raw_frame, dict) and set(raw_frame) == {"clock_id", "time_scale", "unit"}
                and all(isinstance(item, str) and item.strip() for item in raw_frame.values()),
                "raw observation clock_frame must declare clock, scale and unit")
        _refuse(raw_frame == clock.get("source_frame"),
                "raw observation clock_frame differs from mapping source_frame", "clock_frame_mismatch")
        _refuse(isinstance(clock.get("reference_frame"), dict), "reference clock frame is required")
        reference_frames.append(clock["reference_frame"])
        profile = channel["calibration_profile"]
        _refuse(isinstance(profile, dict) and profile.get("sensor_id") == observation["sensor_id"]
                and profile.get("quantity_id") == observation["quantity_id"],
                "calibration identity differs from its raw observation")
        joint = channel["calibration_joint_covariance"]
        _refuse(isinstance(joint, dict) and joint.get("cross_covariance_policy") in {
            "declared", "declared_zero", "unknown"},
            "calibration cross-covariance knowledge state is required")
        _refuse(_identities(joint.get("evidence_ids")), "calibration covariance evidence is required")
    _refuse(len(set(ids)) == 2 and all(isinstance(item, str) and item for item in ids),
            "channel identities must be distinct nonempty strings")
    _refuse(reference_frames[0] == reference_frames[1],
            "both clock maps must target the same reference frame")
    covariance = value["calibrated_covariance"]
    _refuse(isinstance(covariance, dict) and set(covariance) == {
        "matrix", "cross_covariance_policy", "evidence_ids",
    }, "calibrated covariance declaration is incomplete")
    _refuse(covariance["cross_covariance_policy"] in {"declared", "declared_zero", "unknown"},
            "calibrated cross-covariance knowledge state is required")
    _refuse(_identities(covariance["evidence_ids"]), "calibrated covariance evidence is required")
    try:
        raw_matrix = np.asarray(covariance["matrix"])
        _refuse(raw_matrix.dtype.kind in "iuf", "calibrated covariance must contain real numeric values")
        matrix = np.asarray(covariance["matrix"], dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DeclarationRefusal("invalid_experiment", "calibrated covariance must be numeric") from exc
    _refuse(matrix.shape == (2, 2) and np.isfinite(matrix).all()
            and np.array_equal(matrix, matrix.T) and np.all(np.linalg.eigvalsh(matrix) >= 0),
            "calibrated covariance must be a finite symmetric PSD 2 by 2 matrix")
    configuration = value["configuration"]
    _refuse(isinstance(configuration, dict) and set(configuration) == {
        "alignment", "observability", "gsie", "cbsr", "fdir",
    }, "configuration must declare every bounded operation")
    _refuse(all(isinstance(item, dict) for item in configuration.values()),
            "every operation configuration must be an object")
    alignment = configuration["alignment"]
    _refuse(alignment.get("measurement_time_policy") ==
            "nominal_alignment_with_retained_time_uncertainty",
            "measurement time policy must explicitly retain time uncertainty")
    separation = alignment.get("maximum_nominal_separation_s")
    _refuse(_finite(separation) and separation >= 0,
            "maximum nominal separation must be finite and nonnegative")
    gsie = configuration["gsie"]
    _refuse(gsie.get("prior_measurement_crosscov_policy") == "declared_zero",
            "GSIE prior/measurement independence must be explicitly declared")
    _refuse(all(isinstance(gsie.get(key), dict) for key in (
        "prior", "dynamics", "observation_model",
    )), "GSIE prior and model declarations must be objects")
    dynamics = gsie["dynamics"]
    _refuse(dynamics.get("matrix") == [[1.0, 0.0], [0.0, 1.0]]
            and dynamics.get("process_covariance") == [[0.0, 0.0], [0.0, 0.0]],
            "nominal time alignment is bounded to a stationary hold model with F=I and Q=0")
    _refuse(configuration["observability"].get("state_names") == ids,
            "observability state order must equal channel order")
    _refuse(configuration["cbsr"].get("state_labels") == ids,
            "reconciliation state order must equal channel order")
    _refuse(configuration["fdir"].get("variable_order") == ids,
            "FDIR residual order must equal channel order")
    return deepcopy(value)


def declare(experiment: object, execution_id: str) -> dict:
    experiment = validate_experiment(experiment)
    _refuse(isinstance(execution_id, str) and execution_id.strip(),
            "execution_id must be nonempty")
    result = {
        "schema": RESULT_SCHEMA,
        "operation_id": OPERATION_ID,
        "execution_id": execution_id,
        "experiment_id": experiment["experiment_id"],
        "experiment_digest": experiment_digest(experiment),
        "channel_order": [item["channel_id"] for item in experiment["channels"]],
        "claim_scope": experiment["claim_scope"],
        "authority": {"evidence_admission": False, "physical_truth": False,
                      "calibration_certification": False},
    }
    result["result_id"] = "sha256:" + sha256(
        RESULT_SCHEMA.encode() + b"\0" + _canonical(result)
    ).hexdigest()
    return result


def evaluate(request: object) -> dict:
    try:
        _refuse(isinstance(request, dict) and set(request) == {
            "schema", "operation_id", "inputs",
        }, "request fields are invalid", "invalid_input")
        _refuse(request["schema"] == "ciw.adapter-request.v1",
                "unsupported request schema", "unsupported_schema")
        _refuse(request["operation_id"] == OPERATION_ID,
                "unsupported operation", "unsupported_operation")
        inputs = request["inputs"]
        _refuse(isinstance(inputs, dict) and set(inputs) == {"experiment", "execution_id"},
                "inputs require experiment and execution_id", "invalid_input")
        return {"schema": RESPONSE_SCHEMA, "status": "ok",
                "data": declare(inputs["experiment"], inputs["execution_id"])}
    except DeclarationRefusal as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused",
                "refusal": {"code": exc.code, "message": str(exc)}}
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError) as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused",
                "refusal": {"code": "invalid_experiment", "message": str(exc)}}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    try:
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("request exceeds one megabyte")
        request = json.loads(raw, object_pairs_hook=_unique,
                             parse_constant=lambda value: (_ for _ in ()).throw(
                                 ValueError(f"nonfinite JSON number: {value}")))
        response = evaluate(request)
    except (ValueError, UnicodeError) as exc:
        response = {"schema": RESPONSE_SCHEMA, "status": "refused",
                    "refusal": {"code": "invalid_json", "message": str(exc)}}
    print(json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
