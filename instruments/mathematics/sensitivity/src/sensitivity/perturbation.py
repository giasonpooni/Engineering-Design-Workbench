"""Compare the linear map ``J dx`` with the true increment ``f(x+dx)-f(x)``."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .jacobian import jacobian_at, jvp
from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]


@dataclass(frozen=True)
class PerturbationPoint:
    scale: float
    predicted: Array
    actual: Array
    absolute_error: float
    relative_error: float


@dataclass(frozen=True)
class PerturbationSweep:
    model: str
    point: Array
    direction: Array
    source: str
    samples: tuple[PerturbationPoint, ...]

    def as_table(self) -> list[dict[str, float]]:
        rows = []
        for sample in self.samples:
            rows.append(
                {
                    "scale": sample.scale,
                    "absolute_error": sample.absolute_error,
                    "relative_error": sample.relative_error,
                }
            )
        return rows


@dataclass(frozen=True)
class LocalValidity:
    """Largest probed scale at which the linear remainder stays under a bound."""

    model: str
    direction: Array
    absolute_tolerance: float
    relative_tolerance: float
    valid_scale: float | None
    first_invalid_scale: float | None
    notes: str


def perturbation_error(
    model: DifferentiableModel,
    x: ArrayLike,
    dx: ArrayLike,
    *,
    source: str = "auto",
) -> PerturbationPoint:
    point = as_vector(x, "x")
    delta = as_vector(dx, "dx")
    if point.size != model.input_dim or delta.size != model.input_dim:
        raise ValueError("x and dx must match the model input dimension")
    estimate = jacobian_at(model, point, source=source)  # type: ignore[arg-type]
    predicted = jvp(estimate.matrix, delta)
    actual = model.evaluate(point + delta) - model.evaluate(point)
    residual = actual - predicted
    abs_err = float(np.linalg.norm(residual))
    denom = max(float(np.linalg.norm(actual)), 1e-16)
    rel_err = abs_err / denom
    return PerturbationPoint(
        scale=float(np.linalg.norm(delta)),
        predicted=predicted,
        actual=actual,
        absolute_error=abs_err,
        relative_error=rel_err,
    )


def sweep_perturbation_scale(
    model: DifferentiableModel,
    x: ArrayLike,
    direction: ArrayLike,
    scales: ArrayLike,
    *,
    source: str = "auto",
) -> PerturbationSweep:
    point = as_vector(x, "x")
    raw_dir = as_vector(direction, "direction")
    norm = float(np.linalg.norm(raw_dir))
    if norm == 0.0:
        raise ValueError("direction must be nonzero")
    unit = raw_dir / norm
    samples = []
    for scale in np.asarray(scales, dtype=float).ravel():
        samples.append(perturbation_error(model, point, scale * unit, source=source))
    estimate = jacobian_at(model, point, source=source)  # type: ignore[arg-type]
    return PerturbationSweep(
        model=model.name,
        point=point,
        direction=unit,
        source=estimate.source,
        samples=tuple(samples),
    )


def local_validity(
    sweep: PerturbationSweep,
    *,
    absolute_tolerance: float = 1e-3,
    relative_tolerance: float = 5e-2,
) -> LocalValidity:
    """Report the largest scale whose remainder meets both tolerances.

    This is an empirical radius along one declared direction, not a
    global Lipschitz certificate.
    """
    valid = None
    first_invalid = None
    for sample in sweep.samples:
        ok = (
            sample.absolute_error <= absolute_tolerance
            or sample.relative_error <= relative_tolerance
        )
        if ok:
            valid = sample.scale
        else:
            first_invalid = sample.scale
            break
    notes = (
        "Linear remainder compared along one direction. "
        "Tolerances are declared, not universal."
    )
    return LocalValidity(
        model=sweep.model,
        direction=sweep.direction,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        valid_scale=valid,
        first_invalid_scale=first_invalid,
        notes=notes,
    )
