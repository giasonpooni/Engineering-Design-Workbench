# Laboratory teaching-sample workflow

How to add a **HOST teaching sample** that emits one retained render JSON and
is projected by stacked providers (Godot tab + optional Bevy). Science stays on
the host; engines only present.

```text
  fixtures / docs language
           │
           ▼
  examples/<name>/emit_render.py
           │  write_render(...)
           ▼
  examples/<name>/results/*_render.json   (gitignored)
           │
     ┌─────┴─────┐
     ▼           ▼
  Godot tab   Bevy projector
  PresentationKit   tools/bevy-render-view
```

## Steps (summary)

1. **Pick language, do not mint a kind** — attach to an existing operation id /
   docs vocabulary (`ciw.*.v1`, FDIR-OIT, RCI/FSRT/JSPT, …).
2. **Emit** — `emit_render.py` (or `run_or_emit.py`) builds cards / series /
   caption / forbidden_claims and calls `examples/_render_json.write_render`.
3. **Gitignore results** — `results/.gitignore` with `*` and `!.gitignore`.
4. **Godot tab** — `*_view.gd` preloads `PresentationKit`; missing JSON → **STALE**;
   wire into `godot/scripts/main.gd`.
5. **Bevy** — same JSON path; pin `giasonpooni/bevy@0f38358…`; no engine patch.
6. **Docs** — README non-claims; brief row in `docs/VISUALIZATION_PROVIDERS.md`
   Teaching samples.

Detail: [01_emit_render_json.md](01_emit_render_json.md) ·
[02_godot_presentation_tab.md](02_godot_presentation_tab.md) ·
[03_bevy_projector.md](03_bevy_projector.md) ·
[04_real_world_usecase.md](04_real_world_usecase.md) ·
[05_sp1_verifiable_experiment.md](05_sp1_verifiable_experiment.md) ·
[checklist.md](checklist.md) ·
[checklist_sp1.md](checklist_sp1.md).

SP1 teaching emits (no fake proofs): `python3 examples/workflows/emit_sp1_teaching_bundle.py`.

Optional stub: `python examples/workflows/scaffold_sample.py my-sample-name`.

## Status vocabulary

`LIVE` · `STALE` · `UNAVAILABLE` · `REFUSED` · `HELD` · `RECONCILED` ·
`SATISFIED` · `VIOLATED` · `REQUEST_EVIDENCE` · `HISTORICAL`

- Missing render file → **STALE**
- `HISTORICAL` display → `retained_runtime_report_requires_fresh_verification`
- Paint **VERIFIED** only when `fresh_verifier_occurrence: true`

## Claim rules

| Field | Rule |
| --- | --- |
| `may_authorize` | Always `false` (`write_render` forces it) |
| `claim_scope` | Prefer `computational-integrity-only` |
| `fresh_verifier_occurrence` | Default `false`; never invent a fresh occurrence |
| `presentation_only` | `true` |
| Caption | Explicit non-claims (no physical calibration / surveyed frame / BIM / …) |
| Forbidden | No fluid-volume / building / proof-byte viewport content |

## SP1 verifiable experiment (first-class)

Operator path for registered guest → pin ELF → SP1 proof → separate verifier
report → render JSON → Godot/Bevy → optional ESM candidate retention
(**UNADMITTED**). Operation **`ciw.proved-heat.v1` only** (no v2). Cite pins
only from [`docs/PROVED_HEAT.md`](../../docs/PROVED_HEAT.md).

- Workflow: [05_sp1_verifiable_experiment.md](05_sp1_verifiable_experiment.md)
- Checklist: [checklist_sp1.md](checklist_sp1.md)
- Teaching emit orchestrator (existing emitters only, no fake proofs):
  `python3 examples/workflows/emit_sp1_teaching_bundle.py`
- Owned samples: `examples/proved-heat/`, `examples/usecase-thermal-proof-gate/`

Missing proof / ELF / corrupt → **REFUSED** (never green). Retained reports →
**HISTORICAL** / `retained_runtime_report_requires_fresh_verification`.
**VERIFIED** only if `fresh_verifier_occurrence: true`. Godot must not reverify;
no proof bytes on screen; `may_authorize` stays false.

## Batch 1 / Batch 2 samples

| Tab | Folder |
| --- | --- |
| Circle geometry | `examples/gte-circle-eligibility/` |
| Residual strip | `examples/residual-cusum-teach/` |
| Stability verdict | `examples/plsr-stability-verdict/` |
| Energy accuracy | `examples/energy-accuracy-teach/` |
| Free energy | `examples/vfe-sensor-bias-teach/` |
| Measurement chain | `examples/measurement-chain-teach/` |
| Tank farm | `examples/usecase-tank-farm-balance/` |
| Bridge span | `examples/usecase-bridge-span-path/` |
| Takeoff gate | `examples/usecase-ifc-takeoff-gate/` |
| Thermal proof | `examples/usecase-thermal-proof-gate/` |
| Drift watch | `examples/usecase-drift-watch/` |
