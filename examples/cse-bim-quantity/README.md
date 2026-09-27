# cse-bim-quantity (presentation sample)

HOST / synthetic Construction-State-Estimator presentation for the Godot
**BIM quantity** tab. Reuses existing `ciw.bim-quantity.v1` — **does not mint
a new CIW kind**.

## Data sources

| Source | Role |
| --- | --- |
| In-tree [`examples/bim-quantity/README.md`](../bim-quantity/README.md) | Teaching numbers (prior / obs / posterior / volume) and held/refused cases |
| [Construction-State-Estimator-for-BIM](https://github.com/giasonpooni/Construction-State-Estimator-for-BIM) @ `4b74abda40bba3277de69bf61e9e09283ae2d5b3` | CSE disposition language; MCP-readable (local `git clone` returned **403**; no checkout here) |

Marked **HOST / synthetic**. Not a native `GatSession` receipt.

## Teaching numbers (from bim-quantity README)

| Quantity | Value |
| --- | --- |
| Prior ClearHeight | 3 m, σ = 0.01 m |
| Observation | 2.99 m, variance 0.000025 m², independent |
| Posterior ClearHeight | 2.992 m, variance 0.00002 m² |
| Derived room volume | 59.84 m³ |
| Geometry authority | `QUANTITY_ONLY` |

## Cases in the render JSON

1. **Conditioned** — `ciw_status: accepted` / disposition `SATISFIED` → ACCEPT recommendation.
2. **Held** — unknown cross-covariance (and documented frame/unit/binding holds) → `held` / `REQUEST_EVIDENCE`; prior unchanged.
3. **Refused** — negative height invariant rejection → `refused` / `VIOLATED`; replayable rejected event.

## Caption (always)

**ACCEPT is a recommendation, not construction approval.** Demo IFC is not
field evidence; surveyed geometry remains separate.

## What it does not claim

- No building / Revit / IFC solid mesh.
- No construction approval or as-built clearance.
- No surveyed-frame geometry authority.
- No state admission / GSIE fusion.

## Emit render JSON

```sh
python examples/cse-bim-quantity/emit_render.py
# → examples/cse-bim-quantity/results/cse_bim_render.json  (gitignored under results/)
```

## Godot

```sh
godot --path godot
# BIM quantity tab loads ../examples/cse-bim-quantity/results/cse_bim_render.json
# or pass an explicit cse_bim_render.json path after --
```

Presentation only: schematic bars + cards from host JSON; missing file → STALE.
