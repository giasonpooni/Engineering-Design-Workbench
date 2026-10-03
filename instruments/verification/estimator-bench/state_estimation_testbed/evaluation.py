"""Small declared-reference evaluator; this module never computes an estimate."""

from __future__ import annotations

import math
from fractions import Fraction
from collections.abc import Mapping, Sequence

from .contracts import (ContractError, _components, _finite, _record, _text,
                        validate_covariance, validate_result_artifact)
from .replay import canonical_bytes


def _exact_float(value: object, name: str) -> float:
    number = _finite(value, name)
    if isinstance(value, int) and int(number) != value:
        raise ContractError(f"{name} cannot be represented exactly as float64")
    return number


def _quadratic(residual: Sequence[float], covariance: object) -> float | None:
    verdict = validate_covariance(covariance)
    if verdict.dimension != len(residual):
        raise ContractError("metric residual and covariance dimensions differ")
    # No pseudoinverse: singular covariance does not justify silently dropping
    # uncertainty directions or assigning zero error to an unsupported vector.
    if verdict.effective_rank != verdict.dimension:
        return None
    matrix = [[_exact_float(value, "metric covariance") for value in row]
              for row in covariance["matrix"]]
    n = len(residual)
    scales = [math.sqrt(matrix[i][i]) for i in range(n)]
    correlation = [[matrix[i][j] / max(scales[i], scales[j]) /
                    min(scales[i], scales[j]) for j in range(n)] for i in range(n)]
    if any(matrix[i][j] != matrix[j][i] for i in range(n) for j in range(n)):
        return None  # Eligibility tolerance is not permission to repair a metric.
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = correlation[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if value <= 0 or not math.isfinite(value):
                    return None
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]
    solved: list[float] = []
    for i in range(n):
        value = (residual[i] / scales[i] - math.fsum(lower[i][j] * solved[j] for j in range(i))) / lower[i][i]
        if not math.isfinite(value):
            raise ContractError("normalized metric overflowed")
        solved.append(value)
    norm = math.hypot(*solved)
    result = norm * norm
    if not math.isfinite(result):
        raise ContractError("normalized metric overflowed")
    if result == 0.0 and any(value != 0.0 for value in residual):
        raise ContractError("normalized metric underflowed to false zero")
    return result


def evaluate_samples(samples: object, *, model_ref: str) -> dict[str, object]:
    """Report bias/RMSE/NEES/NIS against explicitly supplied reference samples.

    Each sample contains a validated ``result`` exchange artifact. Optional
    ``truth_components`` follow the same ordered name/unit/value structure;
    optional ``innovation`` numeric vector requires ``innovation_covariance``.
    Truth is caller-declared reference data, never an inferred physical fact.
    Unknown, singular, or asymmetrically stored covariance has no NEES/NIS.
    There are no automatic pass thresholds or coverage/calibration claims.
    """
    model_ref = _text(model_ref, "model_ref")
    if not isinstance(samples, (list, tuple)) or not samples:
        raise ContractError("samples must be a non-empty ordered array")
    errors: list[list[float]] = []
    nees: list[float] = []
    nis: list[float] = []
    unavailable: list[dict[str, object]] = []
    expected = None
    expected_frame = None
    result_refs: list[str] = []
    for index, raw in enumerate(samples):
        sample = _record(raw, f"samples[{index}]")
        result = _record(sample.get("result"), "sample.result")
        validate_result_artifact(result)
        if model_ref not in result["model_refs"]:
            raise ContractError("each estimate must retain the declared evaluation model_ref")
        shape = _components(result["components"])
        if expected is not None and shape != expected:
            raise ContractError("all estimates must retain one ordered variable/unit space")
        expected = shape
        frame = canonical_bytes(result["covariance"]["frame"])
        if expected_frame is not None and frame != expected_frame:
            raise ContractError("all estimates must retain the same complete coordinate frame")
        expected_frame = frame
        if "truth_frame" in sample and canonical_bytes(sample["truth_frame"]) != frame:
            raise ContractError("truth_frame must match the estimate coordinate frame")
        result_refs.append(result["result_id"])
        truth = sample.get("truth_components")
        if truth is not None:
            if _components(truth) != shape:
                raise ContractError("truth components must match estimate order and units")
            error = [_exact_float(c["value"], "estimate") - _exact_float(t["value"], "truth")
                     for c, t in zip(result["components"], truth)]
            if any(not math.isfinite(value) for value in error):
                raise ContractError("estimate-reference error overflowed")
            errors.append(error)
            value = _quadratic(error, result["covariance"])
            if value is None:
                unavailable.append({"sample": index, "metric": "NEES", "reason": "known full-rank exactly symmetric covariance required"})
            else:
                nees.append(value)
        innovation = sample.get("innovation")
        innovation_covariance = sample.get("innovation_covariance")
        if (innovation is None) != (innovation_covariance is None):
            raise ContractError("innovation and innovation_covariance must be supplied together")
        if innovation is not None:
            if not isinstance(innovation, (list, tuple)) or not innovation:
                raise ContractError("innovation must be a non-empty numeric vector")
            residual = [_exact_float(value, "innovation[]") for value in innovation]
            value = _quadratic(residual, innovation_covariance)
            if value is None:
                unavailable.append({"sample": index, "metric": "NIS", "reason": "known full-rank exactly symmetric covariance required"})
            else:
                nis.append(value)
    if len(set(result_refs)) != len(result_refs):
        raise ContractError("evaluation samples must have distinct result identities")
    count = len(errors)
    bias = [] if count else None
    rmse = [] if count else None
    if count:
        for i in range(len(expected[0])):
            # Exact summation avoids creating false zero by dividing each
            # subnormal sample before summation, or overflow before averaging.
            exact_mean = sum((Fraction.from_float(row[i]) for row in errors), Fraction()) / count
            mean = float(exact_mean)
            scale = max(abs(row[i]) for row in errors)
            root_mean_square = (math.hypot(*(row[i] / scale for row in errors)) /
                                math.sqrt(count) * scale) if scale else 0.0
            if (mean == 0.0 and exact_mean != 0) or (root_mean_square == 0.0 and scale != 0.0):
                raise ContractError("evaluation metric underflowed to false zero")
            bias.append(mean)
            rmse.append(root_mean_square)
    if bias is not None and any(not math.isfinite(value) for value in bias + rmse):
        raise ContractError("evaluation metric overflowed")
    return {
        "operation_id": "set.evaluate-declared-reference.v1", "model_ref": model_ref,
        "result_refs": result_refs, "variables": list(expected[0]), "units": list(expected[1]),
        "frame": result["covariance"]["frame"],
        "sample_count": len(samples), "reference_sample_count": count,
        "bias": bias, "rmse": rmse, "nees": nees, "nis": nis,
        "unavailable": unavailable,
        "claim_scope": "declared-reference-numerical-evaluation-only",
        "limitations": ["Reference truth and model are declared inputs, not established physical truth.",
                        "No coverage, calibration, fault isolation, or stability inference from these descriptive metrics.",
                        "No cross-sample independence is assumed; aggregate confidence intervals are not reported."],
    }
