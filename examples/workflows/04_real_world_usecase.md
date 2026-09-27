# 04 — Real-world use-case sample (owned configs → scenario)

Turn an **owned** adapter / fixture / teaching emit into a use-case presentation
sample without minting a new CIW kind.

```text
  owned config / fixture / prior teach emit
           │
           ▼
  scenario framing (operations / survey / gate / …)
           │
           ▼
  examples/usecase-<name>/emit_render.py
           │  import or replay owned math
           │  write_render(..., may_authorize false)
           ▼
  results/*_render.json   (gitignored)
           │
           ▼
  Godot Use-case catalog tab discovers all indexed JSONs
  + five specialty tabs + non-claims catalog rows
```

## Steps

1. **Scenario** — name a real-world role (shift check, surveyor path, takeoff
   gate, proof gate, drift watch). Keep it computational-integrity only.
2. **Fixtures** — cite owned paths explicitly
   (`examples/adapters/…`, `examples/*/baseline.json`, prior teach emits).
   Prefer source label **`HOST_FROM_OWNED_CONFIG`**.
3. **Emit** — `emit_render.py` reuses owned math (import prior
   `build_payload` or shared helpers). Call
   `examples/_render_json.write_render`. Force non-claims in
   `caption` and `forbidden_claims`. **No new CIW kind.**
4. **Tab** — `godot/scripts/usecase_catalog_view.gd` discovers every
   `examples/usecase-*/results/*_render.json` and uses PresentationKit cards/status.
   The five baseline scenarios also keep their specialty tabs. Missing JSON →
   **STALE**. Do not add 45 bespoke tabs.
5. **Batch** — run `python3 examples/workflows/emit_all_usecases.py` to emit all
   the full exhaustive corpus. Each sample keeps its own `results/.gitignore` with `*`.
6. **Non-claims** — README + caption must deny the easy over-claims
   (custody transfer, surveyed as-built, construction approval, proof bytes,
   physical drift, …). No fluid-volume / building / proof-byte viewport content.
7. **Docs** — row under Teaching samples in
   `docs/VISUALIZATION_PROVIDERS.md`; link this workflow.

## Reference samples

| Tab | Folder | Owned reuse |
| --- | --- | --- |
| Tank farm | `usecase-tank-farm-balance/` | FSRT / `adapters/two-reservoir.json` |
| Bridge span | `usecase-bridge-span-path/` | CSG path+Jacobi / curved-path-study |
| Takeoff gate | `usecase-ifc-takeoff-gate/` | CSE BIM prior/posterior |
| Thermal proof | `usecase-thermal-proof-gate/` | proved-heat strengthen rules |
| Drift watch | `usecase-drift-watch/` | residual-cusum-teach |

## Exhaustive catalog

The complete indexed list of slugs, owned config sources, catalog entries, and
non-claim one-liners is [`examples/usecase-catalog.md`](../usecase-catalog.md).
The catalog is presentation-only and does not mint CIW kinds.

## Checklist delta

Same as [checklist.md](checklist.md), plus:

- [ ] Source is `HOST_FROM_OWNED_CONFIG` (or equivalent) citing concrete paths
- [ ] Scenario + non-claims are explicit in README and caption
- [ ] Tab title matches the agreed use-case name
