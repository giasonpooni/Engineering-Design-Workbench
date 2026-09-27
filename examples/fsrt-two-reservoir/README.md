# fsrt-two-reservoir (HOST replay of published quickstart)

HOST replay of Fluid-State-Reconstruction-Testbed `examples/quickstart.py` for
the Godot **Fluid balance** tab. Does **not** mint `ciw.fluid-volume.v1` or
import `set_lcm`.

## Data source

GitHub MCP read of `giasonpooni/Fluid-State-Reconstruction-Testbed`
`examples/quickstart.py` @ `3674e0d328bd63777486acd9d8b8b605a37d586f`
(+ in-tree `adapters/two-reservoir.json` for model kind only).
Marked **HOST_REPLAY_OF_PUBLISHED_QUICKSTART** (not native set_lcm import).

`git clone` returned **403**; MCP `get_file_contents` succeeded. Cite copy:
`upstream/quickstart.py`.

## Teaching inputs (exact published quickstart)

| Case | Inputs | Policy |
| --- | --- | --- |
| Small disagreement → reconcile | `[52.0, 46.0]` | reconcile when consistency_stat ≤ threshold |
| Large disagreement → hold | `[60.0, 50.0]` | hold when consistency_stat > threshold |

Constraint: `A=[[1,1]]`, `b=[100]`, `b_var=[0.25]`, `cov=I`.
`S = A P A^T + R = 2.25`. `consistency_stat = r^T S^{-1} r` with
`r = Ax - b`. Threshold ≈ χ² 0.999 df=1 ≈ `10.8275661707` (scipy if present, else hardcode).

HOST hard reconcile: when not held, `x_hat = x - A^T/S * r`; when held keep
`x` and `residual_post` null.

## Caption

**disagreement is not unique fault attribution.**

## Emit

```sh
python examples/fsrt-two-reservoir/emit_render.py
# → examples/fsrt-two-reservoir/results/fsrt_render.json  (gitignored)
```

## Godot

```sh
godot --path godot
# Fluid balance tab loads ../examples/fsrt-two-reservoir/results/fsrt_render.json
```

Presentation only. Missing file → STALE.
