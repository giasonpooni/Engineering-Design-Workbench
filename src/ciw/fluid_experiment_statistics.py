"""Small fixed-parameter Gaussian compatibility calculation (NumPy only).

The backend uses Cholesky whitening and NumPy interpolation. The verifier uses
an explicit bracket interpolation and eigen whitening. Neither fits parameters.
"""
from __future__ import annotations
from copy import deepcopy
import bisect
import math
import numpy as np
from .operations.runner import seal
from . import fluid_experiment_contract as c


def validate_covariances(metadata):
    """PSD checks in dimensionless coordinates; never clip, repair or symmetrize."""
    for name in c.TERMS:
        matrix = metadata["uncertainty"][name]["matrix"]
        if matrix is None:
            continue
        a = np.asarray(matrix, dtype=float)
        scale = np.sqrt(np.diag(a))
        active = scale > 0
        if np.any(active):
            normalized = a[np.ix_(active, active)] / np.outer(scale[active], scale[active])
            if float(np.linalg.eigvalsh(normalized)[0]) < -1e-12:
                raise ValueError("Declared " + name + " covariance is not positive semidefinite")


def chi_square_survival(x, df):
    """Regularized upper incomplete gamma for bounded positive integer df."""
    if x <= 0:
        return 1.0
    z = x / 2.0
    if df % 2 == 0:
        logs = [-z + j * math.log(z) - math.lgamma(j + 1) for j in range(df // 2)]
        largest = max(logs)
        answer = math.exp(largest) * sum(math.exp(item - largest) for item in logs)
    else:
        answer = math.erfc(math.sqrt(z))
        for j in range((df - 1) // 2):
            s = 0.5 + j
            answer += math.exp(s * math.log(z) - z - math.lgamma(s + 1))
    return max(0.0, min(1.0, answer))


def critical_value(alpha, df):
    lower, upper = 0.0, float(df)
    while chi_square_survival(upper, df) > alpha:
        upper *= 2.0
    for _ in range(80):
        middle = (lower + upper) / 2.0
        if chi_square_survival(middle, df) > alpha:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def project(metadata, rows, trace, *, independent=False):
    heldout = [row for row in rows if row["role"] == "holdout"]
    times = [row["time_s"] + metadata["clock"]["offset_s"] for row in heldout]
    grid = trace["time_s"]
    sigma = metadata["clock"]["offset_standard_uncertainty_s"]
    margin = 0.0 if sigma is None else 3.0 * sigma
    if any(t - margin < grid[0] or t + margin > grid[-1] for t in times):
        raise ValueError("Aligned observation and declared three-sigma clock envelope must stay inside retained model grid")
    values, slopes = [], []
    fields = [row["model_field"] for row in metadata["observation_operator"]["channels"]]
    for t in times:
        index = min(max(bisect.bisect_right(grid, t) - 1, 0), len(grid) - 2)
        interval = grid[index + 1] - grid[index]
        for field in fields:
            y = trace[field]
            slope = (y[index + 1] - y[index]) / interval
            if independent:
                fraction = (t - grid[index]) / interval
                prediction = (1.0 - fraction) * y[index] + fraction * y[index + 1]
            else:
                prediction = float(np.interp(t, grid, y))
            values.append(float(prediction))
            slopes.append(float(slope))
    return times, values, slopes


def compute(source, metadata, rows, model, *, independent=False):
    validate_covariances(metadata)
    trace = model["candidate"]["data"]["resolutions"]["finer"]["trace"]
    times, predictions, slopes = project(metadata, rows, trace, independent=independent)
    observations = [value for row in rows if row["role"] == "holdout" for value in row["values"]]
    residual = [x - y for x, y in zip(observations, predictions)]
    size = len(residual)
    covariance = {name: deepcopy(metadata["uncertainty"][name]["matrix"]) for name in c.TERMS}
    unknown = [name for name in c.TERMS if covariance[name] is None]
    sigma = metadata["clock"]["offset_standard_uncertainty_s"]
    clock = None if sigma is None else (np.outer(slopes, slopes) * sigma ** 2).tolist()
    if clock is None:
        unknown.append("clock_common_offset")
    covariance.update(clock_common_offset=clock, unknown_terms=unknown,
                      semantics="full_stacked_covariance_axis_units_products_no_repair")
    total = None if unknown else sum((np.asarray(covariance[name]) for name in (*c.TERMS, "clock_common_offset")), np.zeros((size, size)))
    covariance["total"] = None if total is None else total.tolist()
    stats = {"method": "fixed_parameter_gaussian_mahalanobis_upper_tail.v1", "degrees_of_freedom": size,
             "chi_square": None, "upper_tail_probability": None, "critical_chi_square": None,
             "alpha": metadata["uncertainty"]["alpha"], "reason": "Unknown uncertainty prevents aggregate compatibility"}
    outcome = "INCONCLUSIVE"
    if total is not None:
        scale = np.sqrt(np.diag(total))
        if np.any(scale <= 0):
            stats["reason"] = "Total covariance is singular; no unqualified chi-square degrees of freedom are invented"
        else:
            normalized = total / np.outer(scale, scale)
            eigenvalues = np.linalg.eigvalsh(normalized)
            if float(eigenvalues[0]) <= 1e-12 or float(eigenvalues[-1] / eigenvalues[0]) > 1e12:
                stats["reason"] = "Total covariance is singular or poorly conditioned in dimensionless coordinates"
            else:
                r = np.asarray(residual) / scale
                if independent:
                    eigenvalues, eigenvectors = np.linalg.eigh(normalized)
                    whitened = (eigenvectors.T @ r) / np.sqrt(eigenvalues)
                else:
                    whitened = np.linalg.solve(np.linalg.cholesky(normalized), r)
                chi = float(whitened @ whitened)
                if not math.isfinite(chi) or chi > 1e150:
                    raise ValueError("Compatibility statistic exceeds bounded floating-point scope")
                probability = chi_square_survival(chi, size)
                threshold = critical_value(stats["alpha"], size)
                stats.update(chi_square=chi, upper_tail_probability=probability, critical_chi_square=threshold,
                             reason="Upper-tail Gaussian non-rejection for fixed prior parameters; no physical validation")
                if abs(probability - stats["alpha"]) <= 1e-10:
                    stats["reason"] = "Decision lies inside numerical boundary tolerance"
                else:
                    outcome = "EMPIRICALLY_COMPATIBLE" if probability > stats["alpha"] else "INCOMPATIBLE"
    support = {"source_kind": metadata["provenance"]["source_kind"],
               "conditional_measured_support": metadata["provenance"]["source_kind"] == "declared_measured" and outcome == "EMPIRICALLY_COMPATIBLE",
               "scope": "declared_heldout_observables_times_baseline_and_uncertainty_only", "authority": deepcopy(c.AUTHORITY)}
    return seal({"schema": c.RESULT_SCHEMA, "evidence_id": source["evidence_id"], "model_digest": model["record_digest"],
                 "model_result_id": model["candidate"]["result_id"], "model_execution_id": model["candidate"]["execution_id"],
                 "model_verification_id": model["fresh_verification"]["verification_id"], "axes": deepcopy(metadata["uncertainty"]["axes"]),
                 "aligned_time_s": times, "observed": observations, "predicted": predictions, "residual": residual,
                 "prediction_slopes": slopes, "covariance": covariance, "statistics": stats, "outcome": outcome,
                 "support": support, "limitations": ["Declaration of measurement and calibration is not authenticated",
                    "Only held-out lumped observables at declared times and preloaded baseline are compared",
                    "Common clock-offset covariance is linearized; three-sigma grid containment is a declared policy, not a Gaussian support bound",
                    "Gaussian zero-mean independent-term assumptions and supplied covariance are operator declarations",
                    "No parameter fitting, universal physical validation, state admission or hardware actuation"]})
