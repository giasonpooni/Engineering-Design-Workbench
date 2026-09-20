# Numerical contract

The package requires NumPy and exposes `StatePrior`, `Observation`, `LinearDynamics`, `LinearObservation`, `Estimate`, `predict`, `update`, `EuclideanGeometry` and `SO2Geometry`.

## Models and covariance

For each explicitly supplied interval:

\[
\hat x^- = F\hat x,\qquad P^- = FPF^T + Q.
\]

The caller discretizes `F` and `Q` for that interval. The engine does not infer a sample rate, multiply `Q` by elapsed time, integrate a continuous model or estimate process noise.

At the same state and observation timestamp:

\[
\nu = y-H\hat x^-,\quad S=HP^-H^T+R,\quad K=P^-H^TS^{-1},
\]
\[
\hat x^+=\hat x^-+K\nu,\quad
P^+=(I-KH)P^-(I-KH)^T+KRK^T.
\]

The implementation solves linear systems instead of explicitly forming the inverse. The second equation is the Joseph covariance update. `innovation` is the pre-update difference; `residual` is the post-update measurement difference. `nis` is the normalized innovation squared, `nu.T @ solve(S, nu)`. It is a diagnostic value without an automatic acceptance threshold.

This model assumes zero-mean independent process and measurement noise and measurement noise independent of the prior error. Reusing observations, correlated sensor noise across updates, unknown cross-covariance, model mismatch or bias invalidates the ordinary covariance interpretation. Full covariance within each supplied vector is retained, including off-diagonal entries. Unknown uncertainty must not be replaced by zero.

## Time, frame and unit semantics

- Core time is a finite scalar in caller-declared elapsed seconds. Prediction must strictly advance time. Update requires exact equality of observation and predicted-state time; out-of-order observations must be handled outside this API.
- Each state has a frame ID and an ordered unit tuple. Measurements must match the observation model's declared measurement frame and unit tuple. Defaults use the state's metadata; dimension-changing `H` requires explicit measurement units.
- Matrices encode the caller's declared coordinate map and dimensional scaling. Label checks do not derive units from matrix coefficients, perform frame transforms or authenticate frame IDs.
- Covariance axes follow their associated vector order; entry `(i,j)` has the product of units `i` and `j`.
- Source IDs are nonblank references, not authenticated evidence. `Estimate.as_prior(state_id)` requires an explicit next-state reference for sequential replay.

## Scalar SO(2)

For one angle in radians, use `SO2Geometry()` for both state geometry and measurement geometry. Identity `F` and `H` are required by this version. Differences and corrected angles are wrapped to `[-pi, pi)`. The covariance is local angular variance in `rad²`; it is not covariance of embedded Cartesian circle coordinates. Tangent transport in this one-dimensional angular chart is the identity.

The example in `examples/replay.py` fuses `179°` with `-179°`. The innovation is `+2°`, and the estimate lies on the `±180°` boundary. A broad or multimodal circular distribution cannot be represented faithfully by this local Gaussian approximation; the caller must establish that the local model is appropriate.

## API example

```python
from geometric_state_inference import StatePrior, Observation, LinearObservation, update

prior = StatePrior(0, [0], [[1]], "frame:local", ("m",), "example:prior")
observation = Observation(0, [2], [[1]], "frame:local", ("m",),
                          "example:observation", ("example:synthetic-source",))
estimate = update(prior, observation, LinearObservation([[1]], "example:direct.v1"))
# mean = [1]; covariance = [[0.5]]; innovation = [2]; NIS = 2
```

## Validation limits

Input dimensions, finite values, ordered metadata and covariance validity are checked before estimation. Singular state/noise covariances can be valid; the combined innovation covariance must be positive definite. Unsupported or singular updates are refused, without implicit jitter or pseudoinverse substitution. Floating-point roundoff and conditioning remain numerical limits; reproducibility means the same declared numerical operation, not guaranteed bitwise equality across BLAS implementations.

Covariance checks reject negative diagonal entries and require exact zero rows/columns for zero-variance axes. Symmetry and positive-semidefinite checks use correlation coordinates, with a dimensionless tolerance of `64 * float64_epsilon * dimension` (scaled by correlation spectral radius for the eigenvalue check). Tolerated asymmetry is averaged numerically; the exchange source snapshot remains unchanged. These tolerances differ from the shared SET checker's declared tolerances, so exchange conformance alone does not guarantee estimator acceptance.

Tests compare Gaussian updates against an independently assembled least-squares reference, replay scalar results against exact rational arithmetic, exercise angle wrapping and reject invalid input metadata/covariance. These tests establish computational behavior on the tested cases. They do not establish physical sensor accuracy, observability, calibration traceability or field performance.
