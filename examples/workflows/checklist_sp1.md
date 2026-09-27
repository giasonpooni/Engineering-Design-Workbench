# SP1 verifiable-experiment acceptance checklist

Companion to [05_sp1_verifiable_experiment.md](05_sp1_verifiable_experiment.md).
Cite pins only from [`docs/PROVED_HEAT.md`](../../docs/PROVED_HEAT.md).
Operation: **`ciw.proved-heat.v1` only** (no v2). No push required for local
laboratory acceptance.

## Pins present

- [ ] SCR source `a59aba283b0304faeeb3e5d305087e7709e171ca`
- [ ] SP1 source `b38b61209e45e969289e70d5cf79dc763460bc41`
- [ ] Guest recipe identity `6e5d1687bcc55243d712553a2b7768b6c587a76418bb48a7a2c44224470d423d`
- [ ] Guest ELF SHA-256 `a14e3750da7e221d31842bd6cf983fcc8c0f530b2811537e2a9a9fe803dacf82`
- [ ] Backend report `sp1-cpu v6.1.0`
- [ ] Docs / emits cite these exact strings — no invented pins

## Register guest → pin ELF

- [ ] Recipe loaded from SCR `zk/recipes/sp1-heat.recipe`
- [ ] `execution.build.verify_build` against committed ELF SHA-256
- [ ] Artifacts written **outside** immutable SCR/SP1 checkouts
- [ ] Recipe / ELF mismatch → **REFUSED** (do not rewrite registry)
- [ ] Missing toolchain → **UNAVAILABLE** (unavailable ≠ passed)

## Produce proof (when binaries present)

```sh
python -m ciw serve \
  --computation-repo /path/to/scr \
  --computation-engine /path/to/native-target/release/execution-cli \
  --sp1-prover /path/to/proof-target/release/sp1-host \
  --sp1-heat-guest /path/to/artifacts/sp1-heat.elf \
  --output-dir results/proved-heat-session

python examples/proved-heat/run.py --replay
```

- [ ] Source is `ciw.proved-heat-source.v1` (`examples/proved-heat/source.json`)
- [ ] Session is `ciw.proved-heat-session.v1`
- [ ] Distinct **execution** / **result** / **verification** identities
- [ ] proof-before-result: failed proof → no successful result
- [ ] Missing host bindings → pre-dispatch refuse (no execution claimed)

## Separate verifier report

```sh
python -m ciw proof verify results/original.json \
  --computation-repo /path/to/scr \
  --computation-engine /path/to/native-target/release/execution-cli \
  --sp1-prover /path/to/proof-target/release/sp1-host \
  --sp1-heat-guest /path/to/artifacts/sp1-heat.elf \
  --output results/fresh-verification.json
```

- [ ] Exit 0 on success; exit 2 on malformed / pin change / missing / mismatch / failed verify
- [ ] Verifier report separately identified (`verifier_runtimes` ≠ producer runtime)
- [ ] No supplied verification-key artifact accepted
- [ ] Existing output path refused
- [ ] Retained-only open → **HISTORICAL** =
      `retained_runtime_report_requires_fresh_verification`
- [ ] **VERIFIED** painted only if `fresh_verifier_occurrence: true`

## Installed-wheel gate (`scripts/check_proved_heat.py`)

```sh
python scripts/check_proved_heat.py \
  --scr-repo /path/to/scr \
  --sp1-repo /path/to/notationsystems/SP1-zero-knowledge-virtual-machine \
  --engine /path/to/native-target/release/execution-cli \
  --prover /path/to/proof-target/release/sp1-host \
  --guest /path/to/artifacts/sp1-heat.elf \
  --output-dir results/proved-heat-gate
```

| Name | Role |
| --- | --- |
| Gate schema | `ciw.proved-heat-gate.v1` |
| Pass execution | `real_sp1_proof_fresh_replay_and_verification` |
| Pass stdout | `PASS: installed workbench, real SP1 proof, fresh replay, verification and tamper rejection` |
| Skip policy | Any `skipped` / `failure` / `error` in junit → **gate fails** |
| Required native tests | `test_native_proved_heat_shared_session`, `test_native_tampered_proof_fails_fresh_verification`, `test_native_retained_proof_can_be_reverified_without_reexecution` |
| Test modules | `test_proved_heat.py`, `test_proved_heat_session.py` |

- [ ] Output dir new or empty (stale artifacts cannot satisfy the gate)
- [ ] Guest SHA matches registry; native artifacts outside provider checkouts
- [ ] Gate writes `gate.json`; status `passed` only after real proof + replay + verify + tamper rejection
- [ ] Missing providers → fail (not skip-as-pass)
- [ ] Synthetic structural fixtures alone do **not** claim cryptographic evidence

## Emit render JSON (binaries may be absent)

```sh
python3 examples/proved-heat/emit_proof_render.py
python3 examples/usecase-thermal-proof-gate/emit_render.py
python3 examples/workflows/emit_sp1_teaching_bundle.py   # optional orchestrator
```

- [ ] Uses `examples/_render_json.write_render`
- [ ] `may_authorize: false`, `presentation_only: true`
- [ ] `fresh_verifier_occurrence: false` unless a real fresh report was bound
- [ ] `operation_id: ciw.proved-heat.v1` — **no v2**
- [ ] Cases cover UNAVAILABLE (binaries absent), REFUSED (missing proof /
      missing guest pin / resealed-corrupt), HISTORICAL (thermal gate)
- [ ] Separate cards for execution / result / verification identities
- [ ] No proof bytes in payload viewport fields
- [ ] `results/.gitignore` has `*` and `!.gitignore`
- [ ] Orchestrator only calls existing emitters — no fake proofs

## Godot / Bevy presentation

```sh
godot --path godot
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- --summary \
  examples/proved-heat/results/proved_heat_render.json
```

- [ ] Proof tab loads `examples/proved-heat/results/proved_heat_render.json`
- [ ] Thermal proof tab loads
      `examples/usecase-thermal-proof-gate/results/thermal_proof_render.json`
- [ ] Missing JSON → **STALE**
- [ ] Godot **must not reverify**
- [ ] `HISTORICAL` labeled `retained_runtime_report_requires_fresh_verification`
- [ ] Never green for missing proof / missing ELF / corrupt
- [ ] Bevy pin `giasonpooni/bevy@0f38358…`; no engine patch; same JSON

## ESM candidate retention (UNADMITTED)

- [ ] Inspect (`esm.inspect-candidate.v1`) before capture — no store write on inspect
- [ ] Capture (`esm.capture-candidate.v1`) only with explicit binding/policy
- [ ] Retained envelope status **`UNADMITTED`** — never canonical admission
- [ ] Binding refuse for unbound schema → **REFUSED** / **UNAVAILABLE** (not green)
- [ ] `may_authorize` remains `false`; proof alone does not authorize
- [ ] Receipts distinct from execution / result / verification identities


## Layer status (record separately)

Do not treat teaching emit success as gate pass. Fill one status per layer:

| Layer | Status (`pass` / `fail` / `not_run` / `blocked` / `unavailable` / `cite_only`) | Evidence (command / path / note) |
| --- | --- | --- |
| Docs / pins cited | | |
| Export (teaching render JSON) | | |
| Scientific execution (real SP1 proof) | | |
| Teaching numerical lattice check | | |
| Fresh verification occurrence | | |
| Replay without re-proof | | |
| Tamper rejection | | |
| Presentation (Godot/Bevy) | | |
| ESM (capture UNADMITTED **or** cite_only) | | |

Gate claim allowed only when execution + fresh verify + replay + tamper are
`pass` under `scripts/check_proved_heat.py` with no skips.

## Non-claims (README + caption)

- [ ] Not physical heat / Gaussian update / observations / building-safe /
      state admission
- [ ] Unavailable ≠ passed
- [ ] Inspect does not reverify; no proof bytes on screen
- [ ] No claim of “qualified / proved” without revision + command + pass/skip/gate
- [ ] Teaching emits do not claim a live cryptographic proof occurred

## Docs seam

- [ ] [`examples/workflows/README.md`](README.md) lists workflow 05 first-class
- [ ] [`examples/proved-heat/README.md`](../proved-heat/README.md) Evidence seam → workflow 05
- [ ] [`examples/usecase-thermal-proof-gate/README.md`](../usecase-thermal-proof-gate/README.md) Evidence seam → workflow 05
