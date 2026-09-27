# csg-path-sensitivity (HOST synthetic from published boundary params)

HOST / synthetic Curved-Surface-Geodesic-Sensitivity presentation for the Godot
**Geodesic path** tab. Conceptually attached to existing
`ciw.curved-path-transfer.v1` — **does not mint a second curved-path operation**.

## Data source

GitHub MCP read of `giasonpooni/Curved-Surface-Geodesic-Sensitivity-Runtime`
`examples/replay_path_artefact.py` @ `bbc535af29c30997e56fd120320c570830676462`
(hyperbolic_paraboloid 0.6, u0=0.15, v0=-0.1, heading=0.65, length=1.5,
n_steps=600) and `examples/emit_boundary_record.py` (torus 200/60 mm);
+ in-tree `curved-path-study/baseline.json` for the HOST constant-curvature
path + Jacobi strip.

`git clone` returned **403**; MCP read succeeded; full CSG package was **not**
vendored (`gh` unauthenticated). Status:
**HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS**.

Cite copies: `upstream/replay_path_artefact.py`, `upstream/emit_boundary_record.py`.

## What it shows

- One host-sampled path polyline on declared constant curvature from
  `examples/curved-path-study/baseline.json`.
- Jacobi / sensitivity norm strip (HOST synthetic).
- Cards: path length, declared residual, sensitivity norm, native status
  `HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS`.

## What it does not claim

- Not surveyed BIM.
- Not physical geodesic truth.
- Not a native CSG `integrate_paths` receipt.

## Emit

```sh
python examples/csg-path-sensitivity/emit_render.py
# → examples/csg-path-sensitivity/results/csg_render.json  (gitignored)
```

## Godot

```sh
godot --path godot
# Geodesic path tab loads ../examples/csg-path-sensitivity/results/csg_render.json
```

Presentation only. Missing file → STALE.
