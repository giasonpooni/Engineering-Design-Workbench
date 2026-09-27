# gte-circle-eligibility (presentation sample)

HOST teaching split of GTE circle eligibility for the Godot **Circle geometry**
tab. Reuses existing `ciw.geometric-circle.v1` — **does not mint a new CIW kind**.

## Evidence seam

| Source | Role |
| --- | --- |
| [`examples/adapters/circle.json`](../adapters/circle.json) | Published observed points, unit-circle constraint, policy |
| [`examples/geometric-circle/source.json`](../geometric-circle/source.json) | Eligible under declared geometric policy |
| [`examples/geometric-circle/held.json`](../geometric-circle/held.json) | Held by correction limit |
| [`examples/geometric-circle/singular.json`](../geometric-circle/singular.json) | `numeric_geometry` refusal at circle center |

Marked **HOST_FROM_PUBLISHED_FIXTURES**. Projected points and radial residuals are
HOST teaching arithmetic from the published fixtures — not a live GTE run.

## Cases

1. **Eligible** — corrections within `max_correction_m=0.05` → `LIVE` / eligible.
2. **Held** — same points, `max_correction_m=0.001` → `HELD`; original evidence retained.
3. **Refused** — observation at constraint center → `REFUSED` / `numeric_geometry`.

## Caption (always)

No surveyed frame / physical accuracy / BIM acceptance. Declared frame
`bench-plane` only.

## Non-claims

- No surveyed-frame authority or physical accuracy claim.
- No BIM acceptance or state admission.
- No second geometric-circle operation; Godot does not solve projection.

## Emit render JSON

```sh
python examples/gte-circle-eligibility/run_or_emit.py
# → examples/gte-circle-eligibility/results/gte_circle_render.json  (gitignored)
```

## Godot

```sh
godot --path godot
# Circle geometry tab loads ../examples/gte-circle-eligibility/results/gte_circle_render.json
```

Missing file → **STALE**. `may_authorize` stays false.
