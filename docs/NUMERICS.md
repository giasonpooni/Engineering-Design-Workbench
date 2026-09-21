# Numerical contract

## Finite-horizon LTI observability

For `x[k+1] = A x[k]`, `y[k] = C x[k]`, form

`O_H = [C; CA; ...; CA^(H-1)]`.

`H` counts observation blocks and must be a positive integer (booleans are
rejected). `A` must be square, `C` must have the same number of state columns,
and both must be nonempty, finite and real. The implementation multiplies the
current block by `A` and checks each result for overflow/nonfinite values.

Ordered state names are mandatory. With a positive diagonal scale matrix `D`,
the analyzed matrix is `O_H D`: its right directions live in `z` coordinates,
where `x = D z`. To map a direction back to original state coordinates, multiply
it by `D`. Without supplied scales, raw coordinates and units are reported.
Observation rows are not noise-whitened in this operation; output-unit and sensor
noise choices therefore affect conditioning. Horizon and model validity remain
caller responsibilities.

## Singular values, rank and directions

The matrix is divided by its maximum absolute entry before SVD. Rank comparison
occurs in normalized units using the mathematically equivalent rule

`retain s_i iff s_i > max(rank_atol, rank_rtol * s_max)`.

Default `rank_rtol` is `max(rows, columns) * float64_epsilon`; default
`rank_atol` is zero. Relative tolerances must be finite and in `[0, 1]`; absolute
tolerance must be finite and nonnegative. There is no absolute scale floor that
turns every sufficiently small matrix into a zero matrix. An explicitly nonzero
absolute tolerance intentionally changes rank under uniform rescaling.

`singular_values` contains `min(rows, columns)` values, in descending order.
`numerical_nullspace` is a matrix whose columns are the right singular vectors
discarded by the rank threshold, plus structural null directions of a wide
matrix. It is a **numerical** nullspace and can include small nonzero modes.
`weak_directions` contains retained right vectors satisfying
`s_i <= weak_rtol * s_max` (default `weak_rtol = 1e-6`). Numerical-null directions
are not duplicated as weak directions. For zero matrices, all input directions
are null and there are no weak retained directions.

`condition_number` is `s_max / s_min` only when full column rank is retained;
otherwise it is positive infinity. `retained_condition_number` describes just
the retained subspace, or is infinity for rank zero. This distinction prevents
a wide matrix from appearing identifiable merely because its returned singular
values are all nonzero.

Reported singular values and thresholds are in the analyzed matrix's units.
An extremely small reported threshold can round to zero; the normalized rank
comparison remains authoritative. Direction signs are arbitrary, and degenerate
singular spaces can rotate across LAPACK implementations. Compare subspaces or
projectors when verifying equivalent numerical results, rather than exact vectors.

## Local information and covariance

For a supplied local sensitivity `J = d mean(y) / d theta`, and fixed SPD
measurement covariance `R`, the mean-sensitivity Fisher matrix is

`F = J.T solve(R, J)`.

With declared parameter scales `D`, replace `J` by `J D`, so `F` is in `z`
coordinates. `sensitivity_matrix` preserves the raw supplied `J`, while
`whitened_sensitivity` and `fisher_information` use declared analysis coordinates.

Covariance must be exactly symmetric as supplied and every variance must be
strictly positive. The matrix is normalized into correlation coordinates using
individual standard deviations, dividing each entry by the larger root first.
This preserves eligibility across mixed variance scales without hiding small
negative diagonal entries. A Cholesky factorization must then succeed. Zero,
indefinite, singular and asymmetric covariances are rejected, including tiny
negative variances. There is no symmetrization, jitter, clipping or silently
substituted pseudoinverse.

Cholesky triangular-factor solving produces a whitened Jacobian, from which
information is formed as `J_white.T @ J_white`. No matrix inverse is formed.
Rank diagnostics use `J_white` rather than its Gram matrix, avoiding the
squared conditioning of `F`. Consequently `rank_atol` is in **whitened
sensitivity singular-value units**, not Fisher eigenvalue units.

Full rank establishes local first-order distinguishability under these inputs;
it does not prove global uniqueness or estimator performance. Rank deficiency
can also arise at a special evaluation point in a model identifiable elsewhere.
If covariance depends on parameters, this operation omits the extra covariance
derivative contribution to Gaussian Fisher information. Non-Gaussian likelihoods
can require another information definition.

## Arithmetic and ownership

All arithmetic uses float64. Nonfinite inputs and overflow in matrix products,
reported singular values, whitening or information are rejected with
`ValueError`. Extremely small products may underflow to zero under float64;
declared rescaling is required when this affects the model. Severe covariance
conditioning can make a mathematically SPD covariance numerically inadmissible.
No arbitrary precision claim is made.

Inputs are copied, never mutated. Returned arrays are copied and read-only;
dataclasses are frozen. These guards prevent accidental mutation, not hostile
tampering or cryptographic authentication. A failed NumPy SVD can raise
`numpy.linalg.LinAlgError`.
