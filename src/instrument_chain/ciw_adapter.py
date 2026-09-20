"""RCI-owned, offline calibration endpoint for a workbench subprocess.

No CIW imports, identity allocation, receiver writes, or network access. The
legacy assembly and observation formats remain unchanged. This endpoint adds
an explicit calibration binding and full first-order covariance transport.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
import math
import sys

import numpy as np

from .calibration import CalibrationError, apply_calibration
from .digest import canonical_digest
from .manifest import loads
from .observation import Observation, Quality

REQUEST_SCHEMA = "ciw.adapter-request.v1"
RESPONSE_SCHEMA = "ciw.adapter-response.v1"
OPERATION_ID = "rci.calibrate.v1"
MAX_RECORDS = 512
MAX_REQUEST_BYTES = 8 * 1024 * 1024
_OBSERVATION_KEYS = {f.name for f in fields(Observation)}


class Refusal(ValueError):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(message)


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json(text: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    return json.loads(text, object_pairs_hook=_strict_object, parse_constant=reject_constant)


def _object(value: object, required: set[str], optional: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing, extra = required - value.keys(), value.keys() - required - optional
    if missing or extra:
        raise ValueError(f"{label}: missing keys {sorted(missing)}, unknown keys {sorted(extra)}")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO 8601 timestamp with a UTC offset")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"{label} must carry a UTC offset")
    return result.astimezone(timezone.utc)


def _covariance(value: object, n: int, label: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"{label} must be {n} by {n}")
    for row in value:
        if not isinstance(row, list) or len(row) != n:
            raise ValueError(f"{label} must be {n} by {n}")
        for entry in row:
            _number(entry, label)
    matrix = np.array(value, dtype=float)
    diagonal = np.diag(matrix)
    if np.any(diagonal < 0):
        raise ValueError(f"{label} must be positive semidefinite")
    # Parameters carry different units/scales. Validate in correlation space
    # so a large variance cannot hide a materially negative small mode.
    zero = diagonal == 0
    if np.any(matrix[zero, :] != 0) or np.any(matrix[:, zero] != 0):
        raise ValueError(f"{label}: a zero variance must have zero covariance")
    standard_deviation = np.sqrt(diagonal)
    standard_deviation[zero] = 1.0
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        correlation = matrix / standard_deviation[:, None] / standard_deviation[None, :]
    tolerance = np.finfo(float).eps * n * 16
    if not np.allclose(correlation, correlation.T, rtol=0, atol=tolerance):
        raise ValueError(f"{label} must be symmetric")
    if np.linalg.eigvalsh(correlation)[0] < -tolerance:
        raise ValueError(f"{label} must be positive semidefinite")
    return matrix


def _raw_record(item: dict, assembly) -> tuple[bytes, dict, datetime]:
    _object(item, {"raw_record_b64", "observed_at"}, set(), "record")
    if not isinstance(item["raw_record_b64"], str):
        raise ValueError("raw_record_b64 must be a base64 string")
    raw_bytes = base64.b64decode(item["raw_record_b64"], validate=True)
    record = _object(
        _json(raw_bytes.decode("utf-8")), _OBSERVATION_KEYS,
        {"digest", "delivery", "delivery_history"}, "raw observation",
    )
    if "digest" in record:
        payload = {k: record[k] for k in _OBSERVATION_KEYS}
        if record["digest"] != canonical_digest(payload):
            raise Refusal("source_digest_mismatch", "The declared RCI observation digest does not match its payload")
    for key, expected in {
        "assembly_id": assembly.assembly_id, "assembly_version": assembly.version,
        "calibration_id": assembly.calibration.id, "raw_unit": assembly.calibration.raw_unit,
        "indicated_unit": assembly.calibration.output_unit,
    }.items():
        if record[key] != expected:
            raise Refusal("calibration_mismatch", f"Observation {key} does not match the assembly")
    for key in ("observation_id", "session_id", "timestamp_meaning"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"observation.{key} must be a non-empty string")
    for key in ("sequence", "device_ticks"):
        if isinstance(record[key], bool) or not isinstance(record[key], int) or record[key] < 0:
            raise ValueError(f"observation.{key} must be a non-negative integer")
    quality = _object(record["quality"], {f.name for f in fields(Quality)}, set(), "quality")
    if quality["acquisition"] != "received" or record["raw"] is None:
        raise Refusal("raw_unavailable", "Only a received raw observation can be calibrated")
    if quality["calibration"] != "applicable":
        raise Refusal("calibration_mismatch", "The observation does not declare an applicable calibration")
    if quality["timing"] not in {"device_clock", "readout_only", "unknown"}:
        raise ValueError("Unrecognized timing quality")
    if quality["inference"] not in {"not_run", "updated", "prediction_only", "outside_model"}:
        raise ValueError("Unrecognized inference quality")
    _number(record["raw"], "raw")
    return raw_bytes, record, _timestamp(item["observed_at"], "observed_at")


def calibrate(inputs: dict) -> dict:
    """Calibrate an atomic batch sharing one declared assembly and profile.

    Parameter uncertainty is shared across the entire batch. Raw covariance
    may be correlated. Raw/parameter independence and residual independence
    must be explicitly declared; no unknown covariance is replaced with zero.
    """
    _object(inputs, {"assembly_toml", "records", "raw_covariance"}, {"calibration"}, "inputs")
    if inputs.get("calibration") is None:
        raise Refusal("calibration_missing", "An explicit calibration binding is required")
    if not isinstance(inputs["assembly_toml"], str):
        raise ValueError("assembly_toml must be a string")
    assembly = loads(inputs["assembly_toml"])
    assembly_digest = hashlib.sha256(inputs["assembly_toml"].encode("utf-8")).hexdigest()
    cal = assembly.calibration
    binding = _object(inputs["calibration"], {
        "schema", "calibration_id", "assembly_id", "assembly_version", "installation_id",
        "assembly_digest", "valid_from", "valid_until", "parameter_order", "parameter_covariance",
        "residual_correlation", "raw_parameter_independent",
    }, set(), "calibration")
    for key, expected in {
        "schema": "rci-calibration-binding.v1", "calibration_id": cal.id,
        "assembly_id": assembly.assembly_id, "assembly_version": assembly.version,
        "installation_id": assembly.installation.id, "assembly_digest": assembly_digest,
    }.items():
        if binding[key] != expected:
            raise Refusal("calibration_mismatch", f"Calibration binding {key} does not match the assembly")
    # Both legacy methods implement scale*(raw-zero_raw); do not reinterpret affine.
    if binding["parameter_order"] != ["scale", "zero_raw"]:
        raise Refusal("parameter_order_mismatch", "Parameter order must be [scale, zero_raw]")
    if binding["residual_correlation"] != "independent" or binding["raw_parameter_independent"] is not True:
        raise Refusal("unsupported_uncertainty_model", "This endpoint requires explicit independent residuals and raw/parameter independence")
    if cal.output_unit != assembly.instrument.unit or cal.sigma_unit != cal.output_unit:
        raise Refusal("calibration_mismatch", "Instrument, calibrated output, and sigma units must match")
    valid_from = _timestamp(binding["valid_from"], "valid_from")
    valid_until = _timestamp(binding["valid_until"], "valid_until")
    if valid_until <= valid_from:
        raise ValueError("Calibration valid_until must be after valid_from")
    items = inputs["records"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_RECORDS:
        raise ValueError(f"records must contain between 1 and {MAX_RECORDS} observations")
    parameter_covariance = _covariance(binding["parameter_covariance"], 2, "parameter_covariance")
    raw_covariance = _covariance(inputs["raw_covariance"], len(items), "raw_covariance")
    sources = [_raw_record(item, assembly) for item in items]
    ids = [record["observation_id"] for _, record, _ in sources]
    if len(set(ids)) != len(ids):
        raise ValueError("Repeated observation IDs cannot represent independent records")
    for _, _, acquired_at in sources:
        if acquired_at < valid_from:
            raise Refusal("calibration_not_yet_valid", "Calibration was not yet valid at observation time")
        if acquired_at >= valid_until:
            raise Refusal("calibration_expired", "Calibration had expired at observation time")
    try:
        values = [apply_calibration(record["raw"], cal) for _, record, _ in sources]
    except CalibrationError as exc:
        raise Refusal("calibration_range", str(exc)) from exc
    if not all(math.isfinite(value) for value in values):
        raise Refusal("numerical_refusal", "Calibration produced a non-finite value")
    if any(value < assembly.instrument.range_min or value > assembly.instrument.range_max for value in values):
        raise Refusal("instrument_range", "Calibrated value is outside the declared instrument range")
    scale, zero = cal.theta
    jacobian = np.array([[record["raw"] - zero, -scale] for _, record, _ in sources])
    with np.errstate(over="raise", invalid="raise"):
        parameter_contribution = jacobian @ parameter_covariance @ jacobian.T
        raw_contribution = scale**2 * raw_covariance
        residual_covariance = np.eye(len(items)) * cal.sigma**2
        output_covariance = parameter_contribution + raw_contribution + residual_covariance
    if not np.all(np.isfinite(output_covariance)) or np.any(np.diag(output_covariance) < 0):
        raise Refusal("numerical_refusal", "Propagated covariance is not finite and non-negative on its diagonal")
    uncertainty = {
        "method": "first_order_linearization", "parameter_order": binding["parameter_order"],
        "parameter_units": [f"{cal.output_unit}/{cal.raw_unit}", cal.raw_unit],
        "parameter_covariance": binding["parameter_covariance"], "parameter_jacobian": jacobian.tolist(),
        "raw_covariance": inputs["raw_covariance"], "raw_covariance_unit": f"{cal.raw_unit}^2",
        "parameter_contribution_covariance": parameter_contribution.tolist(),
        "raw_contribution_covariance": raw_contribution.tolist(),
        "residual_covariance": residual_covariance.tolist(), "residual_sigma": cal.sigma,
        "residual_sigma_reason": cal.sigma_reason, "output_covariance": output_covariance.tolist(),
        "output_covariance_unit": f"{cal.output_unit}^2",
        "raw_parameter_independent": True, "residual_correlation": "independent",
        "parameter_correlation_across_records": "shared_profile",
        "traceability": "none_claimed",
    }
    uncertainty_digest = canonical_digest(uncertainty)
    calibration_digest = canonical_digest(binding)
    records = []
    for index, ((raw_bytes, source, _), item, value) in enumerate(zip(sources, items, values)):
        record = {
            "schema": "measurement-record.v1", "kind": "calibrated_observation",
            "observation_id": source["observation_id"], "observed_at": item["observed_at"],
            "observation_time_basis": "caller_declared_acquisition_time",
            "source_evidence_digest": hashlib.sha256(raw_bytes).hexdigest(),
            "raw_record_b64": item["raw_record_b64"], "assembly": assembly.as_dict(),
            "assembly_digest": assembly_digest, "calibration_digest": calibration_digest,
            "calibration_state": "applicable", "quality": dict(source["quality"]),
            "raw": {"value": source["raw"], "unit": source["raw_unit"]},
            "calibrated": {"value": value, "unit": cal.output_unit},
            "uncertainty_digest": uncertainty_digest, "covariance_row": index,
            "claim_scope": "declared_calibration_only",
        }
        record["derived_evidence_digest"] = canonical_digest(record)
        records.append(record)
    return {
        "schema": "measurement-record-batch.v1", "records": records, "uncertainty": uncertainty,
        "uncertainty_digest": uncertainty_digest, "calibration": binding,
        "calibration_digest": calibration_digest, "assembly_digest": assembly_digest,
        "assembly_toml": inputs["assembly_toml"],
    }


def handle_request(request: object) -> dict:
    """Return one result or one refusal, never a partial result."""
    try:
        _object(request, {"schema", "operation_id", "inputs"}, set(), "request")
        if request["schema"] == REQUEST_SCHEMA and request["operation_id"] == "rci.calibrate.v2":
            from .ciw_adapter_v2 import handle_request as handle_v2
            return handle_v2(request)
        if request["schema"] != REQUEST_SCHEMA or request["operation_id"] != OPERATION_ID:
            raise ValueError("Unsupported request schema or operation_id")
        data = calibrate(request["inputs"])
        return {"schema": RESPONSE_SCHEMA, "status": "ok", "data": data}
    except Refusal as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {
            "code": "calibration_unavailable", "reason_code": exc.reason, "message": str(exc),
        }}
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError, binascii.Error) as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {
            "code": "invalid_request", "message": str(exc),
        }}


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(payload) > MAX_REQUEST_BYTES:
            raise ValueError("Request exceeds 8 MiB")
        response = handle_request(_json(payload.decode("utf-8")))
    except (ValueError, UnicodeError) as exc:
        response = {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {
            "code": "invalid_request", "message": str(exc),
        }}
    print(json.dumps(response, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
