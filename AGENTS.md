# Development workflow

- Work on `main`; fetch before publishing and never force-push.
- Keep the status `planned` until an executable reference case and its tests exist.
- Every delivered claim must identify the mathematical object, representation,
  assumptions, tolerances, invariant checks, and a reproducible artifact.
- Use the square torus only as a regression oracle; do not duplicate the full
  Flat-Torus Geodesic Reference implementation.
- Do not add Jacobi fields, SPD covariance geometry, or triangle-mesh geodesics here.
- Never describe a numerical trajectory as exact unless it is derived symbolically.
