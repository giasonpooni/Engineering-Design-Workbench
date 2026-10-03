"""One JSON-in/JSON-out FSRT operation for a pinned workbench subprocess.

The first operation is deliberately a *single simultaneous* two-reservoir
snapshot. Its full channel covariance is retained. A temporal batch requires a
different operation that models shared calibration uncertainty across time;
accepting one here and feeding only its diagonal to a filter would be wrong.

Scientific calculations remain in the existing FSRT estimator and reconciliation
kernel. The workbench supplies execution/evidence identities; this module creates
none and never writes or re-labels source observations.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

from ..lcm import check_spd, chi2_quantile, consistency_stat, reconcile
from ..schema import ConstraintSet, Observation
from ..testbed.estimators import KalmanFilter
from .ciw_covariance import CovarianceRefusal, OPERATION_ID as V2_OPERATION_ID, evaluate_inputs

OPERATION_ID = "fsrt.tank-reconstruct.v1"
MODEL_KIND = "reservoir2-linear-v1"
RESPONSE_SCHEMA = "ciw.adapter-response.v1"
MAX_REQUEST_BYTES = 1_000_000


class InputRefusal(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _object(value, name, required, optional=()):
    if not isinstance(value, dict):
        raise InputRefusal("invalid_input", f"{name} must be an object")
    missing, extra = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or extra:
        raise InputRefusal("invalid_input", f"{name}: missing {sorted(missing)}, unknown {sorted(extra)}")
    return value


def _number(value, name, *, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputRefusal("invalid_input", f"{name} must be a finite JSON number")
    if (minimum is not None and value < minimum) or (positive and value <= 0):
        raise InputRefusal("invalid_input", f"{name} is outside its declared domain")
    return float(value)


def _pair(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise InputRefusal("invalid_input", f"{name} must contain exactly two entries")
    return value


def _strings(value, name):
    result = _pair(value, name)
    if any(not isinstance(v, str) or not v.strip() for v in result) or len(set(result)) != 2:
        raise InputRefusal("invalid_input", f"{name} requires two distinct nonempty strings")
    return tuple(result)


def _optional_numbers(values):
    """Missing innovations become JSON null, never fabricated zero or NaN."""
    return [float(x) if np.isfinite(x) else None for x in values]


def _evaluate(inputs):
    inputs = _object(inputs, "inputs", ("model", "observations"))
    model = _object(inputs["model"], "model", (
        "kind", "prior_mean", "prior_std", "total_mass_kg", "total_mass_variance_kg2",
    ))
    if model["kind"] != MODEL_KIND:
        raise InputRefusal("unsupported_model", f"Only {MODEL_KIND} is supported")
    prior = np.array([_number(v, "prior_mean", minimum=0) for v in _pair(model["prior_mean"], "prior_mean")])
    prior_std = _number(model["prior_std"], "prior_std", positive=True)
    total = _number(model["total_mass_kg"], "total_mass_kg", minimum=0)
    total_variance = _number(model["total_mass_variance_kg2"], "total_mass_variance_kg2", minimum=0)
    observations = inputs["observations"]
    if not isinstance(observations, list) or len(observations) != 1:
        raise InputRefusal("unsupported_temporal_covariance", "v1 requires exactly one simultaneous snapshot; temporal batches are not supported")
    record = _object(observations[0], "observation", (
        "t", "arrival_t", "values", "covariance", "mask", "source_ids", "evidence_ids", "unit",
    ))
    if record["unit"] != "kg":
        raise InputRefusal("unsupported_unit", "Both reservoir observations must be calibrated masses in kg")
    sample_time = _number(record["t"], "t")
    arrival_time = _number(record["arrival_t"], "arrival_t")
    if arrival_time < sample_time:
        raise InputRefusal("invalid_input", "arrival_t must not precede the physical sample time")
    mask = _pair(record["mask"], "mask")
    if any(type(v) is not bool for v in mask):
        raise InputRefusal("invalid_input", "mask entries must be JSON booleans")
    if not any(mask):
        raise InputRefusal("insufficient_observations", "No reservoir observation is present")
    values = _pair(record["values"], "values")
    for value, present in zip(values, mask):
        if present:
            _number(value, "present mass", minimum=0)
        elif value is not None:
            raise InputRefusal("invalid_input", "Absent observations must use null and mask=false")
    covariance = _pair(record["covariance"], "covariance")
    covariance = np.array([[_number(v, "covariance entry") for v in _pair(row, "covariance row")]
                           for row in covariance])
    # Fail before computation if a declared covariance cannot support this filter.
    check_spd(covariance, "observation covariance")
    source_ids = _strings(record["source_ids"], "source_ids")
    evidence_ids = _strings(record["evidence_ids"], "evidence_ids")
    obs = Observation(
        t=sample_time, arrival_t=arrival_time,
        y=np.array([np.nan if v is None else v for v in values]), R=covariance,
        mask=np.array(mask), source_ids=source_ids, evidence_ids=evidence_ids,
    )

    # No prediction step is performed: commanded transfer is irrelevant to this
    # simultaneous snapshot and no hidden truth or estimated command is accepted.
    estimator = KalmanFilter(prior, prior_std, 1.0, np.zeros(1))
    estimator.ingest(obs, 0)
    mean, posterior_covariance = estimator.report(0)
    constraint = ConstraintSet(
        version="ciw-two-reservoir-total-v1", A=np.array([[1., 1.]]),
        b=np.array([total]), b_var=np.array([total_variance]), row_units=("kg",),
        description="Declared total mass of the two reservoirs, independent of the observations.",
    )
    score = consistency_stat(mean, posterior_covariance, constraint)
    threshold = chi2_quantile(constraint.rank, 0.999)
    disagreement = score > threshold
    result = reconcile(
        mean, posterior_covariance, constraint, mode="hard", hold=disagreement,
        stat=score, threshold=threshold, t=sample_time, model_version=MODEL_KIND,
    )
    if not np.all(np.isfinite(result.x)) or not np.all(np.isfinite(result.P)):
        raise FloatingPointError("FSRT produced a non-finite state or covariance")
    if np.any(result.x < 0) or np.any(mean < 0):
        raise InputRefusal("physical_model_refusal", "A Gaussian estimate has negative mass; the nonnegative reservoir domain is not satisfied")
    diagnostic_status = "physical_model_disagreement" if disagreement else "consistent"
    # One total-mass balance cannot tell a sensor bias from a stale total, leak,
    # or omitted physical process. A missing sensor makes attribution weaker.
    attribution = "confounded_or_unidentifiable" if disagreement or not all(mask) else "not_tested"
    return {
        "model": model,
        "calibrated_observation": record,
        "estimate": {"kind": "estimated_state", "values": result.x.tolist(),
                     "covariance": result.P.tolist(), "unit": "kg", "t": sample_time},
        "unprojected_estimate": {"values": mean.tolist(), "covariance": posterior_covariance.tolist(), "unit": "kg"},
        "residuals": {
            "innovation": _optional_numbers(estimator.innov[0]),
            "innovation_variance": _optional_numbers(estimator.innov_var[0]),
            "balance_before": result.residual_pre.tolist(),
            "balance_after": None if result.residual_post is None else result.residual_post.tolist(),
            "correction": None if result.correction is None else result.correction.tolist(),
            "unit": "kg",
        },
        "diagnostics": {
            "physical_model_status": diagnostic_status,
            "reconciliation_status": result.status.value,
            "fault_attribution": attribution,
            "consistency_statistic": score, "consistency_threshold": threshold,
            "confidence": 0.999, "missing_sources": [s for s, present in zip(source_ids, mask) if not present],
            "physical_truth_verified": False,
            "state_domain_status": "nonnegative_masses",
            "scope": "One simultaneous two-reservoir snapshot; no temporal or fault-identification model.",
        },
        "assumptions": {
            "prior_independent_of_observations": True,
            "declared_total_independent_of_observations": True,
            "topology": {"reservoirs": list(source_ids), "balance_coefficients": [1, 1]},
            "temporal_covariance": "not_applicable_single_snapshot",
        },
        "observation_evidence_ids": list(evidence_ids),
    }


def evaluate(request):
    """Return a scientific result or an explicit refusal without partial results."""
    try:
        request = _object(request, "request", ("schema", "operation_id", "inputs"))
        if request["schema"] != "ciw.adapter-request.v1":
            raise InputRefusal("unsupported_schema", "Expected ciw.adapter-request.v1")
        if request["operation_id"] not in (OPERATION_ID, V2_OPERATION_ID):
            raise InputRefusal("unsupported_operation", f"Expected {OPERATION_ID}")
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            data = (evaluate_inputs(request["inputs"], _evaluate)
                    if request["operation_id"] == V2_OPERATION_ID else _evaluate(request["inputs"]))
        # The wire protocol is strict JSON, including every numeric output.
        json.dumps(data, allow_nan=False)
        return {"schema": RESPONSE_SCHEMA, "status": "ok", "data": data}
    except (InputRefusal, CovarianceRefusal) as error:
        code = error.code
        message = str(error)
    except (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError) as error:
        code = "numerical_refusal"
        message = str(error)
    return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {"code": code, "message": message}}


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number {value} is forbidden")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r} is forbidden")
        result[key] = value
    return result


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request exceeds one megabyte")
        request = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    except (ValueError, UnicodeError) as error:
        response = {"schema": RESPONSE_SCHEMA, "status": "refused",
                    "refusal": {"code": "invalid_json", "message": str(error)}}
    else:
        response = evaluate(request)
    print(json.dumps(response, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
