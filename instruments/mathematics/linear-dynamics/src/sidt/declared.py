"""Replayable declarations around fully observed LTI candidate identification.

The declared coordinate system and timing are checked, not inferred. Evidence
references are content bindings, not authenticated observations. Residuals never
become parameter covariance, including for an exact noiseless fit.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import hashlib
import json
import math

import numpy as np

from .lti import NonIdentifiableError, _aligned, evaluate_one_step, fit_lti

DECLARED_OPERATION = "sidt.declared-lti-identification.v1"
INPUT_SCHEMA = "sidt.declared-identification-input.v1"
RESULT_SCHEMA = "sidt.declared-identification-result.v1"


def _snapshot(value: object) -> object:
    def check(item: object) -> None:
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("declarations must contain explicit finite JSON values")
    check(value)
    try:
        return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError("declarations must contain explicit finite JSON values") from error


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _finite_float64(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number")
    # Python compares an int to a float without first rounding the int. Thus
    # this rejects 2**53+1 while allowing exactly representable large epochs.
    # A supplied float already declares its binary64 value; ordinary fractional
    # times retain the existing bounded interval comparison below.
    if converted != value:
        raise ValueError(f"{name} must be exactly representable as float64")
    return converted


def _positive(value: object, name: str) -> float:
    converted = _finite_float64(value, name)
    if converted <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return converted


def _object(value: object, required: set[str], optional: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing, extra = required - value.keys(), value.keys() - required - optional
    if missing or extra:
        raise ValueError(f"{name} keys mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    return value


def _refs(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a nonempty list of references")
    refs = [_text(item, name) for item in value]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{name} must be unique")
    return refs


def _trajectory(value: object, name: str, dt: float, *, holdout: bool) -> dict:
    required = {"states", "inputs", "sample_times", "sample_refs", "evidence_refs"}
    if holdout:
        required.add("independence")
    data = _object(value, required, set(), name)
    if holdout and data["independence"] != "declared_disjoint":
        raise ValueError("holdout independence must be declared_disjoint")
    # Existing numerical validation checks every matrix element and shape.
    # Timing and evidence cardinality must be checked before fitting any model.
    states = data["states"]
    if not isinstance(states, list) or len(states) < 2:
        raise ValueError(f"{name}.states must contain at least two sample rows")
    _aligned(states, data["inputs"])
    times = data["sample_times"]
    if not isinstance(times, list) or len(times) != len(states):
        raise ValueError(f"{name}.sample_times must align one-to-one with state rows")
    for time in times:
        _finite_float64(time, f"{name}.sample_times")
    # A bounded tolerance covers representation of the declared seconds, not
    # timing uncertainty. Large epochs with inadequate resolution are refused.
    tolerance = dt * 1e-9
    for previous, current in zip(times, times[1:]):
        step = _finite_float64(current - previous, f"{name}.sample_times interval")
        if step <= 0 or not math.isfinite(step) or not math.isclose(
            step, dt, rel_tol=0, abs_tol=tolerance,
        ):
            raise ValueError(f"{name}.sample_times must increase uniformly by sample_interval")
    refs = _refs(data["sample_refs"], f"{name}.sample_refs")
    if len(refs) != len(states):
        raise ValueError(f"{name}.sample_refs must align one-to-one with state rows")
    _refs(data["evidence_refs"], f"{name}.evidence_refs")
    return data


def _diagnostics(diagnostics, condition_limit: float) -> dict:
    singular = diagnostics.singular_values.tolist()
    ratio = None
    if diagnostics.rank == diagnostics.regressor_count and singular[-1] > 0:
        with np.errstate(over="ignore"):
            candidate = float(diagnostics.singular_values[0] / diagnostics.singular_values[-1])
        ratio = candidate if math.isfinite(candidate) else None
    return {
        "sample_count": diagnostics.sample_count,
        "regressor_count": diagnostics.regressor_count,
        "rank": diagnostics.rank,
        "singular_values": singular,
        "relative_rank_cutoff": float(diagnostics.relative_rank_cutoff),
        "degrees_of_freedom": diagnostics.degrees_of_freedom,
        "condition_number": ratio,
        "condition_limit": condition_limit,
        "condition_measure": "spectral_2_norm_in_declared_coordinates",
        "state_residuals": None if diagnostics.state_residuals is None else diagnostics.state_residuals.tolist(),
        "state_residual_sum_squares": None if diagnostics.state_residual_sum_squares is None else diagnostics.state_residual_sum_squares.tolist(),
    }


def identify_declared(payload: Mapping, *, execution_ref: str) -> dict:
    """Fit a conditional A/B candidate with retained timing and source evidence.

    Malformed declarations raise ``ValueError``. Rank/conditioning refusal and
    SVD failure return ``nonidentifiable``, ``ill_conditioned`` or ``unresolved``
    with no candidate. Only ``identified`` contains candidate matrices. No
    evidence is admitted and no model is adopted by this operation.
    """
    inputs = _object(_snapshot(payload), {
        "schema", "model_id", "clock_frame", "state_frame", "sample_interval",
        "state_names", "state_units", "input_names", "input_units",
        "condition_limit", "training",
    }, {"rcond", "holdout", "conditioning_reference"}, "input")
    if inputs["schema"] != INPUT_SCHEMA:
        raise ValueError(f"input schema must be {INPUT_SCHEMA}")
    model_id = _text(inputs["model_id"], "model_id")
    _text(inputs["clock_frame"], "clock_frame")
    _text(inputs["state_frame"], "state_frame")
    execution = _text(execution_ref, "execution_ref")
    dt = _positive(inputs["sample_interval"], "sample_interval")
    limit = _positive(inputs["condition_limit"], "condition_limit")
    cutoff = None if inputs.get("rcond") is None else _positive(inputs["rcond"], "rcond")
    if limit < 1:
        raise ValueError("condition_limit must be at least one")
    training = _trajectory(inputs["training"], "training", dt, holdout=False)
    holdout = None if "holdout" not in inputs else _trajectory(inputs["holdout"], "holdout", dt, holdout=True)
    refs = training["evidence_refs"] + training["sample_refs"]
    if holdout is not None:
        if (len(holdout["states"][0]) != len(training["states"][0])
                or len(holdout["inputs"][0]) != len(training["inputs"][0])):
            raise ValueError("training and holdout state/input coordinate widths must agree")
        training_refs = set(refs)
        holdout_refs = set(holdout["evidence_refs"] + holdout["sample_refs"])
        if training_refs & holdout_refs:
            raise ValueError("training and holdout evidence and sample references must be disjoint")
        training_times, holdout_times = training["sample_times"], holdout["sample_times"]
        if not (holdout_times[-1] < training_times[0] or training_times[-1] < holdout_times[0]):
            raise ValueError("training and holdout time intervals must be disjoint in the declared clock frame")
        refs += holdout["evidence_refs"] + holdout["sample_refs"]
    if inputs.get("conditioning_reference") is not None:
        refs.append(_text(inputs["conditioning_reference"], "conditioning_reference"))
    if execution == DECLARED_OPERATION or model_id in (execution, DECLARED_OPERATION):
        raise ValueError("model, operation and execution identities must remain distinct")
    if execution in refs or DECLARED_OPERATION in refs or model_id in refs:
        raise ValueError("evidence references must differ from model, operation and execution identities")
    numerical = {
        "model_id": model_id,
        "state_frame": inputs["state_frame"],
        "clock_frame": inputs["clock_frame"],
        "status": "unresolved",
        "candidate": None,
        "diagnostics": None,
        "holdout_evaluation": None,
        "parameter_covariance": {
            "status": "unknown", "matrix": None,
            "reason": "observed_regressor_errors_and_parameter_uncertainty_are_not_modelled",
        },
        "applicability": "conditional_fully_observed_discrete_lti_candidate",
        "evidence_status": "caller_declared_unattested",
    }
    metadata = {key: inputs[key] for key in (
        "state_names", "state_units", "input_names", "input_units",
    )}
    try:
        candidate = fit_lti(
            training["states"], training["inputs"], sample_interval=dt,
            conditioning_reference=inputs.get("conditioning_reference"),
            rcond=cutoff, **metadata,
        )
    except NonIdentifiableError as error:
        numerical["status"] = "nonidentifiable"
        numerical["diagnostics"] = _diagnostics(error.diagnostics, limit)
    except np.linalg.LinAlgError:
        numerical["reason"] = "svd_did_not_converge"
    else:
        diagnostics = _diagnostics(candidate.diagnostics, limit)
        numerical["diagnostics"] = diagnostics
        condition = diagnostics["condition_number"]
        if condition is None or condition > limit:
            numerical["status"] = "ill_conditioned"
        else:
            numerical["status"] = "identified"
            numerical["candidate"] = {
                "A": candidate.A.tolist(), "B": candidate.B.tolist(),
                "candidate_digest": candidate.candidate_digest,
                "metadata": asdict(candidate.metadata),
            }
            if holdout is not None:
                evaluation = evaluate_one_step(candidate, holdout["states"], holdout["inputs"])
                numerical["holdout_evaluation"] = {
                    "sample_count": evaluation.sample_count,
                    "state_residuals": evaluation.state_residuals.tolist(),
                    "state_rmse": evaluation.state_rmse.tolist(),
                    "independence": "declared_disjoint",
                    "evidence_status": "caller_declared_unattested",
                }
    numerical = _snapshot(numerical)
    result = {
        "schema": RESULT_SCHEMA,
        "operation_id": DECLARED_OPERATION,
        "execution_ref": execution,
        "input_digest": "sha256:" + _digest(inputs),
        "inputs": inputs,
        "numerical_result": numerical,
        "numerical_id": "sidt:numerical:sha256:" + _digest(numerical),
        "verification_refs": [],
    }
    result["result_id"] = "sidt:result:sha256:" + _digest(result)
    identities = [result["input_digest"], result["numerical_id"], result["result_id"], execution, DECLARED_OPERATION, model_id]
    if len(set(identities)) != len(identities) or set(identities) & set(refs):
        raise ValueError("evidence, input, model, operation, execution and result identities must remain distinct")
    return result


def replay_identification(result: Mapping, *, execution_ref: str) -> dict:
    """Recompute retained inputs, refuse edited originals, then run a fresh occurrence.

    This same-implementation check binds the retained result to the operation;
    it is not independent scientific verification or evidence authentication.
    """
    retained = _object(_snapshot(result), {
        "schema", "operation_id", "execution_ref", "input_digest", "inputs",
        "numerical_result", "numerical_id", "verification_refs", "result_id",
    }, set(), "result")
    if execution_ref == retained["execution_ref"]:
        raise ValueError("replay requires a fresh execution identity")
    expected = identify_declared(retained["inputs"], execution_ref=retained["execution_ref"])
    # JSON identity is type-sensitive: Python equality aliases True with 1 and
    # 1.0, which must never make an edited retained result reproduce.
    if _digest(retained) != _digest(expected):
        raise ValueError("retained identification result does not reproduce from its declared inputs")
    return identify_declared(retained["inputs"], execution_ref=execution_ref)
