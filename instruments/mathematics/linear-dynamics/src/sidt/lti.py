"""SVD least squares with explicit sample alignment and identifiability checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Real
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

OPERATION = "sidt.discrete-lti-lstsq.v1"
FloatArray = NDArray[np.float64]


def _array(value: ArrayLike, name: str) -> FloatArray:
    if not isinstance(value, np.ndarray):
        items = np.asarray(value, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in items.flat):
            raise ValueError(f"{name} must contain real numeric values, not booleans")
    raw = np.asarray(value)
    if raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain real numeric values")
    result = np.array(raw, dtype=np.float64, copy=True)
    if result.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional sample-row matrix")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _freeze(value: FloatArray) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    if not np.all(np.isfinite(result)):
        raise ValueError("numerical computation produced nonfinite values")
    # An immutable bytes owner prevents re-enabling the write flag.
    return np.frombuffer(result.tobytes(), dtype=np.float64).reshape(result.shape)


def _labels(values: Sequence[str], width: int, name: str, *, unique: bool) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError(f"{name} must be a sequence of strings")
    result = tuple(values)
    if len(result) != width or any(not isinstance(x, str) or not x.strip() for x in result):
        raise ValueError(f"{name} must have {width} nonempty string entries")
    if unique and len(set(result)) != width:
        raise ValueError(f"{name} must be unique")
    return result


def _aligned(states: ArrayLike, inputs: ArrayLike) -> tuple[FloatArray, FloatArray]:
    x, u = _array(states, "states"), _array(inputs, "inputs")
    if x.shape[0] < 2 or x.shape[1] < 1:
        raise ValueError("states must have at least two samples and one state")
    if u.shape[0] != x.shape[0] - 1:
        raise ValueError("inputs must have one row per state transition (len(states)-1)")
    return x, u


@dataclass(frozen=True)
class ModelMetadata:
    sample_interval: float
    state_names: tuple[str, ...]
    state_units: tuple[str, ...]
    input_names: tuple[str, ...]
    input_units: tuple[str, ...]
    output_names: tuple[str, ...]
    output_units: tuple[str, ...]
    conditioning_reference: str | None
    operation: str = OPERATION


@dataclass(frozen=True)
class FitDiagnostics:
    sample_count: int
    regressor_count: int
    rank: int
    singular_values: FloatArray
    relative_rank_cutoff: float
    degrees_of_freedom: int
    state_residuals: FloatArray | None
    state_residual_sum_squares: FloatArray | None
    output_residuals: FloatArray | None
    output_residual_sum_squares: FloatArray | None


class NonIdentifiableError(ValueError):
    """No usable candidate was produced because the design matrix lacks rank."""

    def __init__(self, diagnostics: FitDiagnostics):
        self.diagnostics = diagnostics
        super().__init__(
            f"regression is nonidentifiable: rank {diagnostics.rank} < "
            f"{diagnostics.regressor_count} regressors"
        )


@dataclass(frozen=True)
class DynamicsCandidate:
    A: FloatArray
    B: FloatArray
    C: FloatArray | None
    D: FloatArray | None
    metadata: ModelMetadata
    diagnostics: FitDiagnostics
    candidate_digest: str

    def predict_next(self, states: ArrayLike, inputs: ArrayLike) -> FloatArray:
        """Predict sample rows; no recursive simulation or observer correction."""
        x, u = self._predict_inputs(states, inputs)
        return _freeze(x @ self.A.T + u @ self.B.T)

    def predict_output(self, states: ArrayLike, inputs: ArrayLike) -> FloatArray:
        if self.C is None or self.D is None:
            raise ValueError("candidate has no output model")
        x, u = self._predict_inputs(states, inputs)
        return _freeze(x @ self.C.T + u @ self.D.T)

    def _predict_inputs(self, states: ArrayLike, inputs: ArrayLike) -> tuple[FloatArray, FloatArray]:
        x, u = _array(states, "states"), _array(inputs, "inputs")
        if x.shape[0] != u.shape[0] or x.shape[1] != self.A.shape[1] or u.shape[1] != self.B.shape[1]:
            raise ValueError("prediction rows and state/input widths must match the candidate")
        return x, u


@dataclass(frozen=True)
class OneStepEvaluation:
    candidate_digest: str
    sample_count: int
    state_residuals: FloatArray
    state_rmse: FloatArray
    output_residuals: FloatArray | None
    output_rmse: FloatArray | None


def fit_lti(
    states: ArrayLike,
    inputs: ArrayLike,
    *,
    sample_interval: float,
    state_names: Sequence[str],
    state_units: Sequence[str],
    input_names: Sequence[str],
    input_units: Sequence[str],
    outputs: ArrayLike | None = None,
    output_names: Sequence[str] = (),
    output_units: Sequence[str] = (),
    conditioning_reference: str | None = None,
    rcond: float | None = None,
) -> DynamicsCandidate:
    """Fit x[k+1] = A x[k] + B u[k], optionally y[k] = C x[k] + D u[k].

    State sample rows have shape (N+1, n), input rows (N, m), and optional
    output rows (N, p). Sample interval is in seconds. All state components
    must be observed. Rank deficiency raises NonIdentifiableError.
    """
    x, u = _aligned(states, inputs)
    if not isinstance(sample_interval, Real) or isinstance(sample_interval, (bool, np.bool_)):
        raise ValueError("sample_interval must be a finite positive number in seconds")
    dt = float(sample_interval)
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("sample_interval must be a finite positive number in seconds")
    if conditioning_reference is not None and (
        not isinstance(conditioning_reference, str) or not conditioning_reference.strip()
    ):
        raise ValueError("conditioning_reference must be a nonempty reference string or None")
    n, m, count = x.shape[1], u.shape[1], u.shape[0]
    y = None if outputs is None else _array(outputs, "outputs")
    if y is not None and (y.shape[0] != count or y.shape[1] < 1):
        raise ValueError("outputs must have shape (number of transitions, positive output width)")
    p = 0 if y is None else y.shape[1]
    metadata = ModelMetadata(
        dt,
        _labels(state_names, n, "state_names", unique=True),
        _labels(state_units, n, "state_units", unique=False),
        _labels(input_names, m, "input_names", unique=True),
        _labels(input_units, m, "input_units", unique=False),
        _labels(output_names, p, "output_names", unique=True),
        _labels(output_units, p, "output_units", unique=False),
        conditioning_reference,
    )
    z = np.concatenate((x[:-1], u), axis=1)
    if rcond is not None and (not isinstance(rcond, Real) or isinstance(rcond, (bool, np.bool_))):
        raise ValueError("rcond must be a finite relative cutoff strictly between zero and one")
    cutoff = np.finfo(np.float64).eps * max(z.shape) if rcond is None else float(rcond)
    if not math.isfinite(cutoff) or not 0 < cutoff < 1:
        raise ValueError("rcond must be a finite relative cutoff strictly between zero and one")
    target = x[1:] if y is None else np.concatenate((x[1:], y), axis=1)
    coefficients, _, rank, singular_values = np.linalg.lstsq(z, target, rcond=cutoff)
    singular_values = _freeze(singular_values)
    rank = int(rank)
    if rank < z.shape[1]:
        raise NonIdentifiableError(FitDiagnostics(
            count, z.shape[1], rank, singular_values, cutoff, count - rank,
            None, None, None, None,
        ))
    residual = target - z @ coefficients
    state_residual = _freeze(residual[:, :n])
    output_residual = None if y is None else _freeze(residual[:, n:])
    diagnostics = FitDiagnostics(
        count, z.shape[1], rank, singular_values, cutoff, count - rank,
        state_residual, _freeze(np.sum(state_residual ** 2, axis=0)),
        output_residual,
        None if output_residual is None else _freeze(np.sum(output_residual ** 2, axis=0)),
    )
    a, b = _freeze(coefficients[:n, :n].T), _freeze(coefficients[n:, :n].T)
    c = None if y is None else _freeze(coefficients[:n, n:].T)
    d = None if y is None else _freeze(coefficients[n:, n:].T)
    payload = {
        "schema": "sidt.dynamics-candidate.v1",
        "A": a.tolist(), "B": b.tolist(),
        "C": None if c is None else c.tolist(), "D": None if d is None else d.tolist(),
        "metadata": asdict(metadata), "relative_rank_cutoff": cutoff,
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return DynamicsCandidate(a, b, c, d, metadata, diagnostics, digest)


def evaluate_one_step(
    candidate: DynamicsCandidate,
    states: ArrayLike,
    inputs: ArrayLike,
    *,
    outputs: ArrayLike | None = None,
) -> OneStepEvaluation:
    """Evaluate supplied rows; callers establish holdout independence and alignment."""
    x, u = _aligned(states, inputs)
    state_residual = _freeze(x[1:] - candidate.predict_next(x[:-1], u))
    output_residual = None
    if outputs is not None:
        y = _array(outputs, "outputs")
        predicted = candidate.predict_output(x[:-1], u)
        if y.shape != predicted.shape:
            raise ValueError("outputs must match prediction shape exactly")
        output_residual = _freeze(y - predicted)
    return OneStepEvaluation(
        candidate.candidate_digest, len(u), state_residual,
        _freeze(np.sqrt(np.mean(state_residual ** 2, axis=0))), output_residual,
        None if output_residual is None else _freeze(np.sqrt(np.mean(output_residual ** 2, axis=0))),
    )
