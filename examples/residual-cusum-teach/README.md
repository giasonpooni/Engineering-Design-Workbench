# residual-cusum-teach (presentation sample)

HOST teaching of residual-monitor / FDIR-OIT CUSUM concepts for the Godot
**Residual strip** tab. Attaches to existing residual-monitor language from
[`docs/EXPERIMENT_VIEW.md`](../../docs/EXPERIMENT_VIEW.md) — **does not invent
`ciw.fluid-volume` or a new residual CIW kind**. No stack-root providers required.

## Evidence seam

| Source | Role |
| --- | --- |
| `docs/EXPERIMENT_VIEW.md` (FDIR/OIT residual sequence) | Vocabulary: normalized residuals, CUSUM, OIT-held, diagnostic candidates |
| [`examples/residual-monitor/`](../residual-monitor/) | Live path requires `--stack-root`; this sample is HOST-only |

Marked **HOST / synthetic ordered windows**.

## Windows

1. **Quiet** — CUSUM stays below threshold → `LIVE`.
2. **Diagnostic candidate** — CUSUM crosses threshold → `REQUEST_EVIDENCE`.
3. **OIT-held** — window held; CUSUM does not advance → `HELD`.

## Caption (always)

Physical drift and alarm probability unestablished; no joint covariance /
cross-window confidence bars. OIT-held windows do not advance the CUSUM state.

## Non-claims

- No physical drift or alarm probability.
- No joint / cross-window confidence bars.
- No new residual CIW kind; no fluid-volume field.

## Emit render JSON

```sh
python examples/residual-cusum-teach/emit_render.py
# → examples/residual-cusum-teach/results/residual_cusum_render.json  (gitignored)
```

## Godot

```sh
godot --path godot
# Residual strip tab loads ../examples/residual-cusum-teach/results/residual_cusum_render.json
```

Missing file → **STALE**.
