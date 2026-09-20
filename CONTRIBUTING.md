# Contributing

Keep the project status `planned` until executable reference cases and their
validation exist. Document only delivered capabilities and retain explicit
limits on every claim.

- Every delivered claim must identify the mathematical object, representation, assumptions, tolerances, invariant checks and a reproducible artifact.
- Use the square torus only as a regression oracle; do not duplicate the Flat-Torus Geodesic Reference implementation.
- Jacobi propagation, SPD covariance geometry and triangle-mesh geodesics are outside this project.
- Do not describe a numerical trajectory as exact unless it is derived symbolically.

Run `python -m unittest discover -s tests -v` after changing the scaffold.
Preserve concurrent work and do not force-push shared history.
