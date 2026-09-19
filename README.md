# Translation-Surface Dynamics Explorer

Research scaffold for reproducible trajectory experiments on compact translation
surfaces assembled from polygon edge identifications.

**Status: planned.** This repository defines the experiment and evidence boundary;
it does not yet claim a dynamics implementation.

## Research question

How do straight-line trajectories, singularities, and closed-orbit structure change
when locally Euclidean polygons are glued into globally nontrivial surfaces?

## First release

The first implementation milestone will:

1. represent labelled polygon edges and validate orientation-reversing pairings;
2. construct the square torus as a regression oracle and an L-shaped genus-two surface;
3. unfold and re-enter directional trajectories while recording every edge transition;
4. distinguish regular closure from termination at a cone singularity;
5. emit a deterministic JSON experiment record with input, invariants, events,
   tolerances, software version, and artifact digest.

The release is accepted only when the checks in
[docs/FIRST-RELEASE.md](docs/FIRST-RELEASE.md) pass.

## Portfolio role

This project owns polygon gluing, cone singularities, and translation-surface
trajectory dynamics. The Flat-Torus Geodesic Reference remains the exact genus-one
oracle. Curved-Surface Geodesic Sensitivity owns Jacobi propagation. Intrinsic
Surface Geodesics owns triangle-mesh distance and path algorithms.

Potential later applications include periodic tool-path studies and coverage on
developable or piecewise-developed domains. Those are hypotheses until tested
against physical measurements.

## Scaffold validation

```bash
python -m unittest discover -s tests -v
```

See [docs/SCOPE.md](docs/SCOPE.md) for exclusions and the staged roadmap.

## License

MIT.
