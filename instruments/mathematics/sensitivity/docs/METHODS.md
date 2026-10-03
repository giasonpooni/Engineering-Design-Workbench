# Methods

## Local map

For a differentiable model `y = F(x)`,

```text
\u03b4y \u2248 J_F(x) \u03b4x,     J_F(x) = \u2202F/\u2202x.
```

The Jacobian is the local linear map. Sensitivity propagation is the
use of that map across a declared system.

## Composition

If `F = f_n \u2218 \u22ef \u2218 f_1`, the chain rule is

```text
J_F(x) = J_{f_n}(x_{n-1}) \u22ef J_{f_2}(x_1) J_{f_1}(x).
```

The testbed compares this product with a Jacobian formed from the
composed function. Agreement is a structural check, not a performance
claim about automatic differentiation.

## Coordinate changes

For invertible linear maps `x' = T x` and `y' = S y`,

```text
J' = S J T^{-1}.
```

Consequently

```text
J' \u03b4x' = S J T^{-1} T \u03b4x = S (J \u03b4x).
```

The two representations predict the same physical increment after the
perturbation and the output have been translated. Raw matrix norms and
singular values can change with units. Any scalar “sensitivity score”
must therefore declare a metric or scaling.

## Local remainder

The linear prediction is compared with the true increment

```text
r(\u03b4x) = F(x + \u03b4x) \u2212 F(x) \u2212 J_F(x) \u03b4x.
```

For an affine map, `r = 0`. For a quadratic scalar, `r = ½ \u03b4xᵀ H \u03b4x`.
A sweep over `\u2016\u03b4x\u2016` reports where a declared tolerance is first
exceeded. That radius is directional and empirical.

## Covariance

```text
\u03a3_y \u2248 J_F(\u03bc_x) \u03a3_x J_F(\u03bc_x)ᵀ
```

is exact when `F` is affine and `\u03a3_x` is the stated covariance. For a
nonlinear `F` the formula inherits the first-order remainder. NIST
propagation guidance identifies this Taylor limitation; the testbed
measures it against a declared Monte Carlo experiment instead of
leaving it as a footnote.

## What is not claimed

Finite-difference Jacobians have truncation and round-off error.
Complex-step differentiation requires a holomorphic real-on-real
restriction of `f`. Optional AD backends are adapters around existing
tools; this repository is not another differentiation framework.
