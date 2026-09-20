# Scope

The first release answers one question:

> If inputs or parameters change slightly, how does that change travel
> through a declared differentiable model, and when does the local
> linear map stop describing the actual increment?

It does **not** claim to be a general sensitivity-analysis platform.

## In scope

- Explicit maps `y = f(x)` with declared dimensions.
- Analytical Jacobians, central/forward finite differences, and
  complex-step checks on holomorphic maps.
- Composition through the chain rule.
- Invertible linear coordinate changes `x' = T x`, `y' = S y` with
  `J' = S J T^{-1}`.
- First-order covariance `\u03a3_y \u2248 J \u03a3_x Jᵀ` compared with Monte Carlo.
- Empirical local-validity sweeps along declared directions.

## Unsupported capabilities

- Global sensitivity indices.
- Discontinuous mode changes and hybrid switching.
- Trajectory / tangent-linear sensitivities of ODE or PDE integrators.
- Automatic discovery of models from source code.

Covariance reuse is intentional: the same Jacobian that maps `\u03b4x` to
`\u03b4y` maps `\u03a3_x` to `\u03a3_y`. The testbed does not introduce a second
meaning of covariance.

Consuming projects (fluid reconstruction, construction estimators,
observers) may import `sensitivity` without adopting the experiment
suite or changing their domain types.
