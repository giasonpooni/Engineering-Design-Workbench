# Sensitivity kernel

The Python `sensitivity` package operates on arrays and explicitly declared
models. Domain identifiers, acquisition records, and application decisions
are outside its interface.

## Public operations

| Operation | API | Meaning |
| --- | --- | --- |
| Local derivative | `jacobian_at`, `jvp` | Evaluate the local map and its action on a perturbation. |
| First-order covariance | `first_order_covariance` | Propagate `Sigma_y = J Sigma_x J^T`. |
| Model-based mean and covariance | `propagate_belief` | Evaluate the mean as `f(mu)` and propagate covariance with the local Jacobian. |
| Coordinate changes | `AffineCoordinates`, `transform_jacobian`, `push_covariance` | Apply the declared affine chart and verify numerical fidelity. |
| Local structure | `local_structure` | Report rank, singular values, visible directions, and the null space of the instantaneous map. |
| Additive state operations | `invariant_error`, `retract`, `predict`, `update` | Apply additive errors and affine Gaussian prediction and conditioning. |

A nonlinear model mean is evaluated as `f(mu)`; `J mu` is not a substitute.
The null space of an instantaneous Jacobian does not establish trajectory
observability, identifiability, or stability.

## Numerical constraints

- Charts must be invertible with 2-norm condition number at most
  `MAX_CONDITION_NUMBER = 1e12`.
- `ROUND_TRIP_TOLERANCE = 1e-8` applies in `max(abs(mean), sigma)` units
  for means and `sigma_i * sigma_j` units for covariance entries.
- Chart transformations use linear solves to recover coordinates.
- Covariances are validated in correlation coordinates. Permitted numerical
  symmetrization does not clip eigenvalues or apply a nearest-PSD repair.
- Exact-zero variance requires zero cross-covariance. A chart round trip
  that introduces uncertainty into an exact-zero direction is refused.
- The Skeel condition estimate is diagnostic and does not alter the chart cap.
- Matrix norms and singular values depend on the declared coordinates;
  sensitivity comparisons require an explicit scaling or metric.

These constraints are exercised by the coordinate, covariance, fidelity, and
metric tests. The public operations are local and first order; see
[SCOPE.md](SCOPE.md) and [METHODS.md](METHODS.md).
