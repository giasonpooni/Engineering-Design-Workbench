# vfe-sensor-bias-teach (presentation sample)

HOST teaching of variational-free-energy sensor-bias / model-mismatch contrasts
for the Godot **Free energy** tab. Reuses existing
`ciw.variational-free-energy.v1` language — **does not mint a new CIW kind**.

## Evidence seam

| Source | Role |
| --- | --- |
| [`examples/variational-free-energy/sensor-bias.json`](../variational-free-energy/sensor-bias.json) | Generator bias absent from assumed likelihood |
| [`examples/variational-free-energy/ignored-correlation.json`](../variational-free-energy/ignored-correlation.json) | Correlated noise vs simplified assumed covariance |
| [`examples/variational-free-energy/wrong-curvature.json`](../variational-free-energy/wrong-curvature.json) | Generator curvature ≠ fitted geometry curvature |
| [`docs/VARIATIONAL_FREE_ENERGY.md`](../../docs/VARIATIONAL_FREE_ENERGY.md) | Vocabulary: free energy, held-out, computational calibration |

Marked **HOST_FROM_PUBLISHED_FIXTURES**. Cards summarize declared
generator-vs-assumed mismatches — **not a live free-energy solve**.

## Cases

1. **Sensor bias** — unmodelled generator bias → `REQUEST_EVIDENCE`.
2. **Ignored correlation** — omitted noise correlation → `HELD`.
3. **Wrong curvature** — generator ≠ geometry curvature → `REFUSED`.

## Caption (always)

Free-energy numerics are computational, not physical calibration. Sensor
calibration, surveyed geometry, physical state admission and physical
stability remain unestablished.

## Non-claims

- No physical / sensor calibration claim.
- No surveyed geometry or physical state admission.
- Lowering free energy does not make an assumed model physically correct.
- No second free-energy solver in the viewport.

## Emit render JSON

```sh
python examples/vfe-sensor-bias-teach/emit_render.py
# → examples/vfe-sensor-bias-teach/results/vfe_sensor_bias_render.json  (gitignored)
```

## Godot

```sh
godot --path godot
# Free energy tab loads ../examples/vfe-sensor-bias-teach/results/vfe_sensor_bias_render.json
```

Missing file → **STALE**. `may_authorize` stays false.
