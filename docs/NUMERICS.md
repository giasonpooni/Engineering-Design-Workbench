# Numerical scope

The supplied affine clock model is

\[
\delta=a(t-t_0)+b,\qquad t_\mathrm{ref}=T_0+\delta.
\]

The anchors `t0` and `T0` are treated as fixed constants. `a` is positive and dimensionless; `t`, `t0`, `T0`, and `b` are in seconds. The inclusive source interval bounds model applicability. A timestamp outside it is rejected; no extrapolation occurs.

For covariance ordered as `x = [t, a, b]`, the local Jacobian is

\[
J=[a,\ t-t_0,\ 1], \qquad u^2=JCJ^\mathsf{T}.
\]

Equivalently,

\[
u^2=a^2C_{tt}+(t-t_0)^2C_{aa}+C_{bb}
+2a(t-t_0)C_{ta}+2aC_{tb}+2(t-t_0)C_{ab}.
\]

The operation includes correlations between raw timestamp, skew, and offset. If a timestamp helped estimate its clock model, treating these quantities as independent may be unjustified; the caller supplies their joint covariance. This implementation does not estimate it.

## Precision and checks

1. Inputs are binary64 finite real numbers. Complex values, nonfinite values, nonpositive skew, and unsupported units are rejected.
2. Covariance must be 3×3, finite, and exactly symmetric. The supplied covariance is copied without averaging, repair, or replacement. Boolean entries and strings representing numbers are rejected.
3. Negative diagonal entries are rejected. Zero variance requires exactly zero associated covariances. Positive-variance coordinates are normalized into a correlation matrix before a PSD test. Each entry is divided by the larger standard deviation first to avoid intermediate overflow. This prevents a very large variance from hiding a negative direction in a much smaller variance coordinate.
4. The normalized covariance must obey pairwise covariance bounds and have minimum eigenvalue at least `-64*eps*n`, where `n` is the number of positive-variance coordinates. This tolerance admits rounding-level PSD violations; no ridge, pseudoinverse, or regularization is added.
5. The propagated covariance terms are accumulated using `math.fsum`. Any negative variance is rejected. Nonfinite intermediate or final arithmetic is rejected. No rounding-level negative value is clipped to zero.

Anchoring reduces epoch-related cancellation but cannot recover precision lost in the supplied source timestamp. Keep the returned `(reference_origin, event_time_delta)` pair for fine resolution. Converting to `event_time` may lose a small delta when the reference epoch is large. Cross-platform floating-point and BLAS results are not promised to be bitwise identical.

## Interpretation

`first-order.v1` reports the model evaluated at supplied nominal inputs and a local covariance approximation. The product of uncertain skew and uncertain time is bilinear. Its exact expectation can include a timestamp/skew covariance correction, and its exact variance can include higher moments. Neither is claimed here. A zero first-order variance under perfect correlation need not imply zero exact nonlinear variance.

The validity interval checks the nominal timestamp; it does not prove that an uncertainty distribution stays inside that interval. This operation also provides no leap-second conversion, clock-drift validation, synchronization certification, or validation of the source evidence itself.

Tests cover an analytical correlated case, endpoint applicability, exact deterministic input, singular covariance, mixed-scale indefinite covariance, retained metadata, immutable snapshots, invalid identities, and nonfinite arithmetic.
