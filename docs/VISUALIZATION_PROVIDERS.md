# Visualization providers (stacked projectors)

Host science emits **one** retained render JSON record per sample
(`*_render.json` under `examples/*/results/`, gitignored). Presentation engines
project that record. They do **not** compute science, mint CIW viewport kinds,
or call each other.

```text
                    ┌─────────────────────────────┐
  host emit ──────► │  retained *_render.json     │
  (_render_json.py) │  cards / series / status    │
                    │  claim_scope                │
                    │  may_authorize: false       │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
   Godot 4.5 GL Compatibility              Bevy 0.20.0-dev
   godot/scripts/*_view.gd                 tools/bevy-render-view
   PresentationKit status vocab            same status vocab
```

## Providers

| Provider | Path | Pin / version | Role |
| --- | --- | --- | --- |
| Godot | `godot/` | Godot **4.5.2**, GL Compatibility | Interactive tabs: Analog, Fluid balance, Geodesic path, BIM quantity, Proof, Circle geometry, Residual strip, Stability verdict, Energy accuracy, Free energy, Measurement chain, Tank farm, Bridge span, Takeoff gate, Thermal proof, Drift watch, Use-case catalog |
| Bevy | `tools/bevy-render-view` | `giasonpooni/bevy` @ `0f38358f573a7dc6ea961076f6151be662142010` (`0.20.0-dev`) | Second projector over the **same** JSON |

Do **not** patch the Bevy engine tree. Do **not** make Godot call Bevy or Bevy call Godot.

## Shared status vocabulary

Used by `godot/scripts/presentation_kit.gd` and `tools/bevy-render-view`:

`LIVE`, `STALE`, `UNAVAILABLE`, `REFUSED`, `HELD`, `RECONCILED`, `SATISFIED`, `VIOLATED`, `REQUEST_EVIDENCE`, `HISTORICAL`

- Missing render file → **STALE**
- `HISTORICAL` display text → `retained_runtime_report_requires_fresh_verification`
- Paint **VERIFIED** only when JSON has `fresh_verifier_occurrence: true`
- Caption constant: `presentation of retained values; meshes do not compute`

## Emit helpers

```sh
python examples/_render_json.py   # library: write_render(path, dict)
python examples/pyramid-method-gap/run_analog.py --write-render examples/pyramid-method-gap/results/analog_render.json
python examples/fsrt-two-reservoir/emit_render.py
python examples/csg-path-sensitivity/emit_render.py
python examples/cse-bim-quantity/emit_render.py
python examples/proved-heat/emit_proof_render.py
python examples/gte-circle-eligibility/run_or_emit.py
python examples/residual-cusum-teach/emit_render.py
python examples/plsr-stability-verdict/emit_render.py
python examples/energy-accuracy-teach/emit_render.py
python examples/vfe-sensor-bias-teach/emit_render.py
python examples/measurement-chain-teach/emit_render.py
python examples/usecase-tank-farm-balance/emit_render.py
python examples/usecase-bridge-span-path/emit_render.py
python examples/usecase-ifc-takeoff-gate/emit_render.py
python examples/usecase-thermal-proof-gate/emit_render.py
python examples/usecase-drift-watch/emit_render.py
```

`write_render` forces `may_authorize: false` and fills `claim_scope`, `status`, `source`, `cards`, `fresh_verifier_occurrence: false` when absent.

## Non-claims

- No fluid-volume field, building/Revit mesh, or proof-byte drawing in the viewport
- No second BIM / curved-path / proved-heat CIW operation for presentation
- Unavailable ≠ passed; Godot/Bevy must not reverify proofs

## Teaching samples

Host-only presentation samples (no private clones; emit without stack-root):

| Tab | Example folder | Render JSON |
| --- | --- | --- |
| Circle geometry | `examples/gte-circle-eligibility/` | `results/gte_circle_render.json` |
| Residual strip | `examples/residual-cusum-teach/` | `results/residual_cusum_render.json` |
| Stability verdict | `examples/plsr-stability-verdict/` | `results/plsr_stability_render.json` |
| Energy accuracy | `examples/energy-accuracy-teach/` | `results/energy_accuracy_render.json` |
| Free energy | `examples/vfe-sensor-bias-teach/` | `results/vfe_sensor_bias_render.json` |
| Measurement chain | `examples/measurement-chain-teach/` | `results/measurement_chain_render.json` |
| Tank farm | `examples/usecase-tank-farm-balance/` | `results/tank_farm_render.json` |
| Bridge span | `examples/usecase-bridge-span-path/` | `results/bridge_span_render.json` |
| Takeoff gate | `examples/usecase-ifc-takeoff-gate/` | `results/takeoff_gate_render.json` |
| Thermal proof | `examples/usecase-thermal-proof-gate/` | `results/thermal_proof_render.json` |
| Drift watch | `examples/usecase-drift-watch/` | `results/drift_watch_render.json` |
| Use-case catalog | `examples/usecase-catalog.md` + every `examples/usecase-*/` folder | 9,074 discovered `results/*_render.json` records (9,024 exhaustive product rows plus 50 preserved hand-authored extras) |

Reuses existing kinds / ops language only (`ciw.geometric-circle.v1`, residual-monitor / FDIR-OIT, `ciw.identified-stability.v1`, `ciw.energy-accuracy.v1`, `ciw.variational-free-energy.v1`, RCI/FSRT/JSPT measurement-chain, FSRT two-reservoir, `ciw.curved-path-transfer.v1`, `ciw.bim-quantity.v1`, `ciw.proved-heat.v1`). Captions keep non-claims explicit; missing JSON → **STALE**.

Real-world use-case samples wrap **owned** adapters/fixtures (`HOST_FROM_OWNED_CONFIG`) as operations scenarios — no new CIW kinds. See [`examples/workflows/04_real_world_usecase.md`](../examples/workflows/04_real_world_usecase.md).

The Godot **Use-case catalog** tab (`godot/scripts/usecase_catalog_view.gd`) loads the generated index for all 9,074 use-case folders and projects each retained JSON as a PresentationKit card with status and verification label. Run `python3 examples/workflows/emit_all_usecases.py` to regenerate the local records. Generate/merge the exhaustive matrix with `python3 examples/workflows/generate_usecase_corpus.py` (industry/domain × mapped verb; preserved folders are skipped). The full slug/source/non-claim index is [`examples/usecase-catalog.md`](../examples/usecase-catalog.md). The original specialty scenarios remain wired to their specialty tabs; the exhaustive product rows intentionally share the catalog rather than adding thousands of tabs.

Laboratory workflow for adding teaching samples: [`examples/workflows/`](../examples/workflows/).

