# Numerical contract

The package requires NumPy and exposes `StatePrior`, `Observation`, `LinearDynamics`, `LinearObservation`, `Estimate`, `predict`, `update`, `replay_estimate`, `EuclideanGeometry` and `SO2Geometry`.

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
- Source IDs are nonblank references, not authenticated evidence. Prediction and update derive distinct content-bound transition `state_id` values. A prediction records `predecessor_state_id` and `operation_ref`; an estimate records `prior_state_id`. `Estimate.as_prior()` uses its derived state ID, while `as_prior(state_id)` retains a caller-assigned alias distinct from its predecessor. Neither is an execution occurrence ID.

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

Input dimensions, finite values, ordered metadata and covariance validity are checked before estimation. Numerical axes are bounded to 64 components. Declared booleans, strings, complex values and nonfinite values are refused rather than converted to real measurements; integers (including NumPy integer scalars) must be exactly representable in float64, and conversion of a nonzero real value to float64 zero is refused. Types or integer precision already erased by a caller's prior array conversion cannot be recovered. Singular state/noise covariances can be valid; the combined innovation covariance must be positive definite. Unsupported or singular updates are refused, without implicit jitter or pseudoinverse substitution. Floating-point roundoff and conditioning remain numerical limits; reproducibility means the same declared numerical operation, not guaranteed bitwise equality across BLAS implementations.

Covariance checks reject negative diagonal entries and require exact zero rows/columns for zero-variance axes. Supplied covariance must be exactly symmetric; even small declared asymmetry is refused without repair. The positive-semidefinite check uses correlation coordinates, with dimensionless tolerance `64 * float64_epsilon * dimension`, scaled by correlation spectral radius. This is a floating-point eligibility check, not exact proof of PSD. These tolerances differ from the shared SET checker's declared tolerances, so exchange conformance alone does not guarantee estimator acceptance.

Prediction, innovation and Joseph posterior covariance use guarded sums of congruences. The ordinary float64 path explicitly averages only its *computed* roundoff asymmetry. A variance small relative to `64 * eps * dimension * diag(sum(abs(A) abs(P) abs(A).T))`, any zero matrix entry with a structurally possible nonzero product path, or a nonfinite intermediate triggers exact rational evaluation of the stored binary64 inputs. Boolean support multiplication detects possible covariance paths even when floating-point magnitudes underflow. A positive exact variance is preserved when representable; nonzero covariance entries that would round to zero are refused on this fallback. Exact nullspaces and exact off-diagonal cancellation remain zero. This finite, dimension-bounded reference fallback repairs arithmetic cancellation, not the declared input covariance. It is not a general forward-error guarantee for all entries or ill-conditioned gain solves. NIS zero with a nonzero innovation is refused as underflow rather than presented as perfect agreement.

## Local replay and numerical identity

`Estimate.replay_snapshot` returns detached JSON containing the prior mean/covariance, observation, model matrices, geometry, noise assumption and retained predecessor transitions. `replay_estimate(snapshot)` executes only the supported local operations, checks predecessor agreement, and refuses unknown geometry/operation declarations. It imports no artifact-named code. Snapshots are capped at 1 MiB and replay at 64 predecessor transitions. For long histories, a caller can explicitly establish a new prior checkpoint; its identity and provenance must then be managed outside this bounded engine.

`Estimate.numerical_result_id` hashes elapsed physical time, mean, covariance, coordinate metadata, innovation, innovation covariance, residual and NIS. It excludes evidence IDs, model IDs, state IDs, execution occurrence and creation time. It is a numerical-content equality key, not evidence identity or an independent certificate. State-transition identity separately binds the complete declared configuration and numerical state. Full replay repeats this implementation; it does not establish source authenticity, independence or physical correctness.

Tests compare Gaussian updates against an independently assembled least-squares reference, replay scalar results against exact rational arithmetic, exercise angle wrapping and reject invalid input metadata/covariance. These tests establish computational behavior on the tested cases. They do not establish physical sensor accuracy, observability, calibration traceability or field performance.
