# usecase-thermal-proof-gate (integer heat / thermal guest proof gate)

ORIGINAL teaching use-case: **integer heat / thermal guest proof gate** before
releasing a retained result.

Reuses owned proved-heat strengthen rules
(`HISTORICAL` / `REFUSED` / missing proof / binaries absent) from
`examples/proved-heat/` — **does not mint `ciw.proved-heat.v2`**.

## Scenario

Before releasing a retained integer-heat guest result, the gate inspects
whether a fresh proof occurrence is present. Missing proof, missing guest pin,
or resealed-corrupt proof → **REFUSED**. Binaries absent → **UNAVAILABLE**.
Retained historical reports stay under
`retained_runtime_report_requires_fresh_verification`.

## Non-claims

- **Inspect does not reverify**
- **No proof bytes on screen**
- Not physical heat; not Gaussian update; not state admission
- Unavailable ≠ passed
- `may_authorize` stays false; presentation only

## Owned configs cited

- `examples/proved-heat/` (`emit_proof_render.py`, `source.json`)
- `docs/PROVED_HEAT.md` pins

Source label: **HOST_FROM_OWNED_CONFIG**. Operation: `ciw.proved-heat.v1`.

## Emit

```sh
python3 examples/usecase-thermal-proof-gate/emit_render.py
# → examples/usecase-thermal-proof-gate/results/thermal_proof_render.json
```

## Godot

Tab **Thermal proof** loads the render JSON above. Missing file → **STALE**.

## Evidence seam

Reuse the SP1 verifiable-experiment operator path; this folder frames the same
owned proved-heat strengthen rules as a thermal guest proof gate:

- [`examples/workflows/05_sp1_verifiable_experiment.md`](../workflows/05_sp1_verifiable_experiment.md)
- Acceptance: [`examples/workflows/checklist_sp1.md`](../workflows/checklist_sp1.md)
- Owned upstream: `examples/proved-heat/` + `docs/PROVED_HEAT.md` pins

Inspect does not reverify; no proof bytes on screen; missing proof / guest pin /
resealed-corrupt → **REFUSED**; binaries absent → **UNAVAILABLE**; retained
reports stay **HISTORICAL** /
`retained_runtime_report_requires_fresh_verification`.
