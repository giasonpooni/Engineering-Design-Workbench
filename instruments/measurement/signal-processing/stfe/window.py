# SPDX-License-Identifier: MPL-2.0
"""A strict, scalar, causal window mean over at most 32 retained samples.

Numerical inputs are binary64 numbers. Exact rational accumulation and PSD
elimination operate on those stored inputs, with a single final rounding.
No covariance triangle is averaged, diagonalized, jittered, or clamped.
"""

from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import math
import re
import sys
from typing import Any

OPERATION_ID = "stfe.window-mean.v1"
MAX_SAMPLES = 32
MAX_PRESENTED = 4096
BACKEND = "python-fraction-binary64.v1"


class ContractError(ValueError):
    """The bounded operation cannot honor the supplied declaration."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return "sha256:" + sha256(canonical(value).encode("utf-8")).hexdigest()


def _record(value: Any, fields: set[str], name: str,
            optional: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    if set(value) - fields - optional or fields - set(value):
        raise ContractError(f"{name} fields differ from the versioned contract")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ContractError(f"{name} must be a nonempty string of at most 1024 characters")
    return value


def _number(value: Any, name: str) -> float:
    # bool, strings and numpy scalar coercions are intentionally not accepted.
    if type(value) not in (int, float):
        raise ContractError(f"{name} must be a JSON number, not a coercible value")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ContractError(f"{name} must be finite binary64") from exc
    if not math.isfinite(result):
        raise ContractError(f"{name} must be finite binary64")
    if type(value) is int and int(result) != value:
        raise ContractError(f"{name} integer is not exactly representable as binary64")
    return 0.0 if result == 0.0 else result


def _rounded(value: Fraction, name: str) -> float:
    try:
        result = float(value)
    except OverflowError as exc:
        raise ContractError(f"{name} exceeds binary64 range") from exc
    if not math.isfinite(result) or (value != 0 and result == 0.0):
        raise ContractError(f"{name} overflow/underflow would misrepresent a nonzero result")
    return 0.0 if result == 0.0 else result


def _refs(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_PRESENTED:
        raise ContractError(f"{name} must be a bounded ordered array")
    result = [_text(item, name) for item in value]
    if len(result) != len(set(result)):
        raise ContractError(f"{name} must not repeat references")
    return result


def _utc(value: Any) -> str:
    value = _text(value, "created_at")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise ContractError("created_at must be explicit UTC, at most microsecond precision")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("created_at must be a valid UTC instant") from exc
    return value


def _covariance(value: Any, refs: list[str]) -> tuple[dict, float | None]:
    claim = _record(value, {"status", "crosscov_policy", "matrix", "observation_refs"},
                    "uncertainty")
    if _refs(claim["observation_refs"], "uncertainty.observation_refs") != refs:
        raise ContractError("covariance order must exactly match consumed observation references")
    status, policy = claim["status"], claim["crosscov_policy"]
    if status == "unknown":
        if policy != "unknown" or claim["matrix"] is not None:
            raise ContractError("unknown covariance requires unknown policy and null matrix")
        return dict(claim), None
    if status != "known" or policy not in ("declared", "declared_zero"):
        raise ContractError("known covariance requires declared full matrix or declared_zero crosscov")
    raw = claim["matrix"]
    count = len(refs)
    if not isinstance(raw, list) or len(raw) != count or any(
        not isinstance(row, list) or len(row) != count for row in raw
    ):
        raise ContractError("covariance must be a full N by N matrix, including cross-covariance")
    matrix = [[_number(item, "covariance entry") for item in row] for row in raw]
    if any(matrix[i][j] != matrix[j][i] for i in range(count) for j in range(count)):
        raise ContractError("covariance must be exactly symmetric; no implicit repair")
    if policy == "declared_zero" and any(
        matrix[i][j] != 0.0 for i in range(count) for j in range(count) if i != j
    ):
        raise ContractError("declared_zero crosscov contradicts a nonzero off-diagonal")
    exact = [[Fraction(item) for item in row] for row in matrix]
    work = [row[:] for row in exact]
    # Exact symmetric elimination proves PSD of the represented matrix. This
    # conservative contract refuses even tiny negative pivots; it never repairs.
    for pivot in range(count):
        diagonal = work[pivot][pivot]
        if diagonal < 0:
            raise ContractError("covariance is not positive semidefinite")
        if diagonal == 0:
            if any(work[pivot][j] != 0 for j in range(pivot + 1, count)):
                raise ContractError("zero covariance pivot has nonzero coupling")
            continue
        for i in range(pivot + 1, count):
            for j in range(i, count):
                updated = work[i][j] - work[i][pivot] * work[pivot][j] / diagonal
                work[i][j] = work[j][i] = updated
    variance = sum((sum(row, Fraction()) for row in exact), Fraction()) / (count * count)
    if variance < 0:
        raise ContractError("propagated variance is negative")
    return {**claim, "matrix": matrix}, _rounded(variance, "mean variance")


def window_mean(request: dict) -> dict:
    """Compute ``stfe.window-mean.v1``; return detached JSON-native artifacts.

    Only caller-declared references are bound here. Source bytes and mapping
    applicability must be checked by the composing replay verifier. No signature,
    independent verification, sensor truth or canonical admission is claimed.
    """
    request = _record(request, {
        "operation_id", "source_batch_ref", "source_batch_digest", "samples", "window",
        "channel_id", "value_unit", "frame", "clock_basis", "clock_mapping_ref",
        "frame_mapping_ref", "calibration_refs", "uncertainty", "execution_id",
        "created_at", "implementation_revision",
    }, "request", {"replay_ref"})
    if request["operation_id"] != OPERATION_ID:
        raise ContractError("unsupported operation_id")
    source_ref = _text(request["source_batch_ref"], "source_batch_ref")
    source_digest = _text(request["source_batch_digest"], "source_batch_digest")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_digest):
        raise ContractError("source_batch_digest must be a lowercase SHA-256 digest")
    revision = _text(request["implementation_revision"], "implementation_revision")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ContractError("implementation_revision must be a full Git revision")
    channel = _text(request["channel_id"], "channel_id")
    unit = _text(request["value_unit"], "value_unit")
    frame = _text(request["frame"], "frame")
    clock = _text(request["clock_basis"], "clock_basis")
    clock_map = _text(request["clock_mapping_ref"], "clock_mapping_ref")
    frame_map = _text(request["frame_mapping_ref"], "frame_mapping_ref")
    calibration = _refs(request["calibration_refs"], "calibration_refs")
    execution_id = _text(request["execution_id"], "execution_id")
    created_at = _utc(request["created_at"])
    replay_ref = request.get("replay_ref")
    if replay_ref is not None:
        replay_ref = _text(replay_ref, "replay_ref")
    raw_window = _record(request["window"], {
        "start", "end", "received_by", "decision_time", "sample_period", "max_lateness",
    }, "window")
    window = {key: _number(item, f"window.{key}") for key, item in raw_window.items()}
    start, end = window["start"], window["end"]
    period = window["sample_period"]
    if period <= 0 or start >= end or window["max_lateness"] < 0:
        raise ContractError("window must have positive duration/period and nonnegative max_lateness")
    if not end <= window["received_by"] <= window["decision_time"]:
        raise ContractError("causal support end <= received_by <= decision_time is required")
    count_ratio = (Fraction(end) - Fraction(start)) / Fraction(period)
    if count_ratio.denominator != 1 or not 1 <= count_ratio <= MAX_SAMPLES:
        raise ContractError(f"window must contain exactly 1 to {MAX_SAMPLES} regular sample positions")
    expected_count = int(count_ratio)
    presented = request["samples"]
    if not isinstance(presented, list) or not len(presented) <= MAX_PRESENTED:
        raise ContractError(f"samples must be an ordered array of at most {MAX_PRESENTED} records")
    consumed = []
    previous_receipt: float | None = None
    for raw in presented:
        raw = _record(raw, {"observation_ref", "event_time", "received_at", "value", "missing"},
                      "sample")
        event = _number(raw["event_time"], "sample.event_time")
        if not start <= event < end:
            # Out-of-support samples cannot change a previous numerical result.
            continue
        receipt = _number(raw["received_at"], "sample.received_at")
        if not event <= receipt <= window["received_by"]:
            raise ContractError("sample availability violates event/receipt/cutoff ordering")
        if Fraction(receipt) - Fraction(event) > Fraction(window["max_lateness"]):
            raise ContractError("late sample exceeds the declared latency bound")
        if previous_receipt is not None and receipt < previous_receipt:
            raise ContractError("out-of-order delivery is unsupported")
        if raw["missing"] is not False:
            raise ContractError("missing samples are refused, never filled with zero")
        position = len(consumed)
        if Fraction(event) != Fraction(start) + position * Fraction(period):
            raise ContractError("duplicate, missing, irregular or out-of-order event time")
        previous_receipt = receipt
        consumed.append({
            "observation_ref": _text(raw["observation_ref"], "sample.observation_ref"),
            "event_time": event, "received_at": receipt,
            "value": _number(raw["value"], "sample.value"), "missing": False,
        })
    if len(consumed) != expected_count:
        raise ContractError("window is incomplete; missing samples are not imputed")
    refs = _refs([item["observation_ref"] for item in consumed], "consumed observation refs")
    if source_ref in refs:
        raise ContractError("batch identity must differ from individual observation identities")
    claimed_uncertainty, variance = _covariance(request["uncertainty"], refs)
    mean = _rounded(sum((Fraction(item["value"]) for item in consumed), Fraction()) /
                    expected_count, "mean")
    config = {
        "operation_id": OPERATION_ID, "mode": "causal", "window": window,
        "support": "half_open", "channel_id": channel, "value_unit": unit,
        "frame": frame, "clock_basis": clock, "clock_mapping_ref": clock_map,
        "frame_mapping_ref": frame_map, "sample_order": "event_and_receipt_nondecreasing",
        "missingness_policy": "reject", "late_data_policy": "reject_beyond_bound",
        "out_of_order_policy": "reject", "padding": "none", "detrending": "none",
        "window_function": "rectangular", "state": "stateless", "hop": "caller_declared_window",
        "feature": "arithmetic_mean", "backend": BACKEND,
    }
    config_ref = "stfe-config:" + digest(config).split(":")[1]
    window_record = {
        "schema": "notation.stfe.telemetry-window.v1", "source_batch_ref": source_ref,
        "source_batch_digest": source_digest, "source_observation_refs": refs,
        "samples": consumed, "sample_count": expected_count, "missing_count": 0,
        "operation_config": config, "calibration_refs": calibration,
        "uncertainty": claimed_uncertainty,
    }
    window_ref = "stfe-window:" + digest(window_record).split(":")[1]
    window_record["window_id"] = window_ref
    roles = [source_ref, *refs, *calibration, OPERATION_ID, config_ref, window_ref]
    if execution_id in roles or execution_id in (clock_map, frame_map, replay_ref):
        raise ContractError("execution identity must differ from evidence, operation, mapping and replay")
    if OPERATION_ID in [source_ref, *refs, *calibration] or config_ref in [source_ref, *refs]:
        raise ContractError("operation identity must differ from evidence identity")
    feature_name = channel + ".mean"
    numerical = {
        "schema": "notation.stfe.numerical-result.v1", "operation_id": OPERATION_ID,
        "config": config, "sample_values": [item["value"] for item in consumed],
        "sample_event_times": [item["event_time"] for item in consumed],
        "covariance_status": claimed_uncertainty["status"],
        "crosscov_policy": claimed_uncertainty["crosscov_policy"],
        "input_covariance": claimed_uncertainty["matrix"], "mean": mean, "variance": variance,
    }
    numerical_id = "stfe-numerical:" + digest(numerical).split(":")[1]
    covariance = {
        "status": "propagated" if variance is not None else "unknown",
        "matrix": [[variance]] if variance is not None else None,
        "variables": [feature_name], "units": [unit],
        "frame": {"id": "stfe-feature:" + frame, "semantics": "feature_space", "basis": [feature_name]},
        "method": "exact-binary64-rational w R w^T, w_i=1/N; final binary64 rounding",
        "source_refs": [source_ref, window_ref], "calibration_refs": calibration,
        "crosscov_policy": claimed_uncertainty["crosscov_policy"],
    }
    execution = {
        "execution_id": execution_id, "operation_id": OPERATION_ID,
        "operation_config_ref": config_ref, "implementation_revision": revision,
        "backend": BACKEND, "python_version": sys.version.split()[0], "created_at": created_at,
        "reference_status": "caller_declared_not_scr_committed", "replay_ref": replay_ref,
    }
    quality = {
        "schema": "notation.stfe.stream-quality.v1", "window_ref": window_ref,
        "operation_ref": OPERATION_ID, "execution_ref": execution_id,
        "sample_count": expected_count, "missing_count": 0, "warmup_status": "complete",
        "sample_period": period, "time_unit": "s", "status": "nominal_under_declared_grid",
        "physical_validity": "not_established", "clock_mapping_validity": "caller_declared",
    }
    quality["quality_id"] = "stfe-quality:" + digest(quality).split(":")[1]
    artifact = {
        "schema": "notation.instrument.result-artifact.v1", "execution_ref": execution_id,
        "input_refs": [source_ref, window_ref, *refs],
        "model_refs": [OPERATION_ID, config_ref, clock_map, frame_map],
        "calibration_refs": calibration, "created_at": created_at,
        "components": [{"name": feature_name, "value": mean, "unit": unit}],
        "covariance": covariance, "numerical_result_id": numerical_id,
        "window_ref": window_ref, "quality_ref": quality["quality_id"],
        "source_binding": {"batch_ref": source_ref, "canonical_json_digest": source_digest,
                           "status": "caller_supplied_digest_not_source_authentication"},
        "execution_binding": execution,
        "applicability": "Scalar regular-grid causal window mean; no estimator or physical truth claim",
        "authority": {"may_authorize": False, "independent_verification": "not_performed"},
    }
    # Shared exchange identity is domain separated, unlike companion records.
    artifact["result_id"] = "sha256:" + sha256(
        artifact["schema"].encode("utf-8") + b"\x00" + canonical(artifact).encode("utf-8")
    ).hexdigest()
    return json.loads(canonical({
        "schema": "notation.stfe.window-mean-receipt.v1", "operation_id": OPERATION_ID,
        "result_artifact": artifact, "window": window_record, "quality": quality,
        "execution": execution, "numerical_result": numerical, "numerical_result_id": numerical_id,
    }))
