"""Acceptance tests for the four first-release responsibilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .composition import chain_rule_jacobian, compose
from .coordinates import AffineCoordinates, apply_input_map, transform_jacobian, transform_model
from .covariance import first_order_covariance, run_covariance_experiment
from .jacobian import jacobian_at, jvp
from .metrics import DeclaredMetric
from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    residual: float
    details: str
    extra: dict[str, float]

    def raise_for_failure(self) -> None:
        if not self.passed:
            raise AssertionError(f"{self.name} failed: {self.details}")


def _residual_norm(left: Array, right: Array) -> float:
    return float(np.linalg.norm(np.asarray(left) - np.asarray(right)))


def check_derivative(
    model: DifferentiableModel,
    x: ArrayLike,
    *,
    against: str = "central",
    atol: float = 1e-6,
    rtol: float = 1e-5,
) -> CheckResult:
    """Compare the declared Jacobian with a numerical estimator."""
    point = as_vector(x, "x")
    if model.jacobian is None:
        declared = jacobian_at(model, point, source="central")
        reference = jacobian_at(model, point, source=against)  # type: ignore[arg-type]
        label = f"central vs {against}"
    else:
        declared = jacobian_at(model, point, source="analytical")
        reference = jacobian_at(model, point, source=against)  # type: ignore[arg-type]
        label = f"analytical vs {against}"
    residual = _residual_norm(declared.matrix, reference.matrix)
    scale = max(float(np.linalg.norm(reference.matrix)), 1e-16)
    passed = residual <= atol + rtol * scale
    return CheckResult(
        name=f"derivative:{model.name}",
        passed=passed,
        residual=residual,
        details=f"{label}; residual={residual:.3e}",
        extra={"relative_residual": residual / scale},
    )


def check_composition(
    models: list[DifferentiableModel] | tuple[DifferentiableModel, ...],
    x: ArrayLike,
    *,
    atol: float = 1e-7,
    rtol: float = 1e-6,
    source: str = "auto",
) -> CheckResult:
    """Stepwise chain-rule Jacobian versus Jacobian of the composed map."""
    point = as_vector(x, "x")
    composed = compose(models)
    stepwise = chain_rule_jacobian(models, point, source=source)
    whole = jacobian_at(composed, point, source="central" if composed.jacobian is None else "auto")
    residual = _residual_norm(stepwise, whole.matrix)
    scale = max(float(np.linalg.norm(whole.matrix)), 1e-16)
    passed = residual <= atol + rtol * scale
    names = " o ".join(model.name for model in models)
    return CheckResult(
        name=f"composition:{names}",
        passed=passed,
        residual=residual,
        details=f"chain-rule vs composed residual={residual:.3e}",
        extra={"relative_residual": residual / scale},
    )


def check_coordinate_consistency(
    model: DifferentiableModel,
    x: ArrayLike,
    coordinates: AffineCoordinates,
    dx: ArrayLike,
    *,
    atol: float = 1e-8,
    rtol: float = 1e-7,
    source: str = "auto",
) -> CheckResult:
    """Compare physical predictions after a consistent change of coordinates."""
    point = as_vector(x, "x")
    delta = as_vector(dx, "dx")
    jac = jacobian_at(model, point, source=source).matrix  # type: ignore[arg-type]
    primed_jac = transform_jacobian(jac, coordinates)
    dx_prime = coordinates.T @ delta
    left = jvp(primed_jac, dx_prime)
    right = coordinates.S @ jvp(jac, delta)
    map_residual = _residual_norm(left, right)
    transformed = transform_model(model, coordinates)
    x_prime = apply_input_map(point, coordinates)
    value_residual = _residual_norm(
        transformed.evaluate(x_prime),
        coordinates.S @ model.evaluate(point),
    )
    jac_at_prime = jacobian_at(transformed, x_prime, source=source).matrix  # type: ignore[arg-type]
    jac_residual = _residual_norm(jac_at_prime, primed_jac)
    residual = max(map_residual, value_residual, jac_residual)
    passed = (
        map_residual <= atol + rtol * max(float(np.linalg.norm(right)), 1e-16)
        and value_residual <= atol + rtol * max(float(np.linalg.norm(coordinates.S @ model.evaluate(point))), 1e-16)
        and jac_residual <= atol + rtol * max(float(np.linalg.norm(primed_jac)), 1e-16)
    )
    return CheckResult(
        name=f"coordinates:{model.name}:{coordinates.name}",
        passed=passed,
        residual=residual,
        details=(
            f"J'dx' vs S J dx residual={map_residual:.3e}; "
            f"value residual={value_residual:.3e}; "
            f"J' residual={jac_residual:.3e}"
        ),
        extra={
            "map_residual": map_residual,
            "value_residual": value_residual,
            "jacobian_residual": jac_residual,
        },
    )


def check_covariance_affine(
    model: DifferentiableModel,
    mean: ArrayLike,
    sigma_x: ArrayLike,
    *,
    atol: float = 5e-3,
    rtol: float = 5e-2,
    samples: int = 6000,
    seed: int = 0,
) -> CheckResult:
    """First-order covariance versus Monte Carlo on a declared model."""
    experiment = run_covariance_experiment(
        model,
        mean,
        sigma_x,
        samples=samples,
        rng=np.random.default_rng(seed),
    )
    scale = max(float(np.linalg.norm(experiment.monte_carlo, ord="fro")), 1e-16)
    passed = experiment.frobenius_gap <= atol + rtol * scale
    return CheckResult(
        name=f"covariance:{model.name}",
        passed=passed,
        residual=experiment.frobenius_gap,
        details=(
            f"Frobenius gap={experiment.frobenius_gap:.3e}, "
            f"relative={experiment.relative_gap:.3e}, n={experiment.samples}"
        ),
        extra={"relative_gap": experiment.relative_gap},
    )


def check_metric_consistency(
    model: DifferentiableModel,
    x: ArrayLike,
    coordinates: AffineCoordinates,
    metric: DeclaredMetric,
    *,
    atol: float = 1e-8,
    rtol: float = 1e-7,
    source: str = "auto",
) -> CheckResult:
    """Compare scaled operator gains after pushing the metric with the chart."""
    point = as_vector(x, "x")
    jac = jacobian_at(model, point, source=source).matrix  # type: ignore[arg-type]
    primed_jac = transform_jacobian(jac, coordinates)
    pushed = metric.push(coordinates)
    gain = metric.operator_gain(jac)
    primed_gain = pushed.operator_gain(primed_jac)
    scaled = metric.scale_jacobian(jac)
    primed_scaled = pushed.scale_jacobian(primed_jac)
    left_svals = np.sort(np.linalg.svd(scaled, compute_uv=False))
    right_svals = np.sort(np.linalg.svd(primed_scaled, compute_uv=False))
    residual = float(np.linalg.norm(left_svals - right_svals))
    passed = residual <= atol + rtol * max(float(np.linalg.norm(left_svals)), 1e-16)
    return CheckResult(
        name=f"metric:{model.name}:{coordinates.name}:{metric.name}",
        passed=passed,
        residual=residual,
        details=(
            f"unscaled ||J||_2={float(np.linalg.norm(jac, ord=2)):.3e}, "
            f"||J'||_2={float(np.linalg.norm(primed_jac, ord=2)):.3e}; "
            f"scaled gains {gain:.6g} vs {primed_gain:.6g}"
        ),
        extra={
            "gain": gain,
            "primed_gain": primed_gain,
            "unscaled_ratio": float(
                np.linalg.norm(primed_jac, ord=2) / max(np.linalg.norm(jac, ord=2), 1e-16)
            ),
        },
    )


def predicted_output_covariance(
    model: DifferentiableModel,
    mean: ArrayLike,
    sigma_x: ArrayLike,
    *,
    source: str = "auto",
) -> Array:
    jac = jacobian_at(model, mean, source=source).matrix  # type: ignore[arg-type]
    return first_order_covariance(jac, sigma_x)
