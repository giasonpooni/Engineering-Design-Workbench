# 05 — SP1 verifiable experiment (`ciw.proved-heat.v1`)

End-to-end **operator** workflow for a verifiable integer-heat experiment using
the registered SCR guest and SP1 CPU backend. Science and proof stay on the
host; Godot/Bevy only present retained JSON. **No `ciw.proved-heat.v2`.**

Standing rules (see [`docs/PROVED_HEAT.md`](../../docs/PROVED_HEAT.md),
[`docs/JULIA_SP1.md`](../../docs/JULIA_SP1.md)):

| Rule | Operator consequence |
| --- | --- |
| proof-before-result | Failed / missing proof → refusal; no successful result |
| Godot must not reverify | Presentation never invokes the verifier |
| HISTORICAL | Retained reports carry `retained_runtime_report_requires_fresh_verification` |
| Missing proof / ELF / corrupt | **REFUSED**, never green |
| VERIFIED | Only when JSON has `fresh_verifier_occurrence: true` |
| `may_authorize` | Always `false` |
| No proof bytes on screen | Bundle retains bytes; viewports do not draw them |
| Distinct identities | Separate execution / result / verification IDs |
| Cite real pins only | From `docs/PROVED_HEAT.md` — do not invent |

```text
  register guest (recipe + ELF pin)
           |
           v
  pin host SCR/SP1 + execution-cli + sp1-host
           |
           v
  produce SP1 proof (ciw.proved-heat.v1)
           |
           v
  separate verifier report (python -m ciw proof verify)
           |
           v
  emit render JSON (proved-heat / thermal-proof-gate)
           |
     +-----+-----+
     v           v
  Godot Proof /  Bevy projector
  Thermal proof  (same JSON)
           |
           v
  optional ESM candidate retention -> UNADMITTED
  (binding refuse stays REFUSED / UNAVAILABLE — never admission)
```

## Pins (from `docs/PROVED_HEAT.md` exactly)

| Component | Required identity |
| --- | --- |
| SCR source | `a59aba283b0304faeeb3e5d305087e7709e171ca` |
| SP1 source | `b38b61209e45e969289e70d5cf79dc763460bc41` |
| Backend report | `sp1-cpu v6.1.0` |
| Guest recipe | SCR `zk/recipes/sp1-heat.recipe`, identity `6e5d1687bcc55243d712553a2b7768b6c587a76418bb48a7a2c44224470d423d` |
| Guest ELF SHA-256 | `a14e3750da7e221d31842bd6cf983fcc8c0f530b2811537e2a9a9fe803dacf82` |
| Guest compiler | `succinct-1.94.0-64bit` (Linux x86-64; exact archive SHA-256 in the workflow) |
| Operation | `ciw.proved-heat.v1` only |
| Source schema | `ciw.proved-heat-source.v1` |
| Session schema | `ciw.proved-heat-session.v1` |
| Gate schema | `ciw.proved-heat-gate.v1` |

Teaching statement (bounded registered guest only): `[0,100,200,100,0]` and
four steps → `[0,65,92,65,0]`. Unit `1`. Not physical heat, not Gaussian
update, not observations, not building-safe, not state admission.

## 1. Register guest → pin ELF

On Linux, provision the exact Succinct compiler, check the committed recipe,
and rebuild the guest **outside** the immutable SCR checkout. The Linux
workflow [`.github/workflows/proved-heat.yml`](../../.github/workflows/proved-heat.yml)
is the reference:

```sh
# Clean SCR checkout at a59aba283b0304faeeb3e5d305087e7709e171ca
# CI installs the recipe toolchain then runs verify_build
python -c "
from execution.build import load_recipe, verify_build
from pathlib import Path
import shutil
scr = Path('/path/to/scr')
recipe = load_recipe(scr / 'zk/recipes/sp1-heat.recipe')
assert recipe.identity() == '6e5d1687bcc55243d712553a2b7768b6c587a76418bb48a7a2c44224470d423d'
artifact = verify_build(
    recipe,
    'a14e3750da7e221d31842bd6cf983fcc8c0f530b2811537e2a9a9fe803dacf82',
    repo_root=scr,
)
out = Path('/path/to/artifacts')
out.mkdir(parents=True, exist_ok=True)
shutil.copyfile(artifact.elf_path, out / 'sp1-heat.elf')
print(artifact.elf_path)
"
```

**Refuse paths**

| Condition | Status |
| --- | --- |
| Recipe identity mismatch | **REFUSED** — do not rewrite the guest registry |
| Built ELF SHA-256 mismatch | **REFUSED** |
| Recipe / compiler unavailable | **UNAVAILABLE** (unavailable ≠ passed) |
| Non-Linux host without compatible backend | **UNAVAILABLE** for proof; Windows may inspect saved records only |

## 2. Pin host binaries and start the shared operation

Keep build outputs outside the immutable SCR/SP1 checkouts. Use Python 3.12
and explicit trusted paths:

```sh
python -m ciw serve \
  --computation-repo /path/to/scr \
  --computation-engine /path/to/native-target/release/execution-cli \
  --sp1-prover /path/to/proof-target/release/sp1-host \
  --sp1-heat-guest /path/to/artifacts/sp1-heat.elf \
  --output-dir results/proved-heat-session

# Second terminal — --replay produces another real proof
python examples/proved-heat/run.py --replay
```

Source fixture: [`examples/proved-heat/source.json`](../proved-heat/source.json)
(`ciw.proved-heat-source.v1`). Existing `source.add`, `operation.execute`,
`bundle.get`, `bundle.replay`, `experiment.inspect`, and `instrument.inspect`
carry this operation. Instrument role is `scr`; `fusion_context` is null.

**Refuse paths**

| Condition | Status |
| --- | --- |
| Missing guest / engine / prover binding | Pre-dispatch refuse; no execution claimed |
| Guest SHA mismatch at bind | **REFUSED** |
| Proof failure after dispatch | Failed outer workflow retained; null result; never silent downgrade to unproved |

## 3. Produce SP1 proof → separate verifier report

Proof production and verification are **distinct occurrences**. Opening a
workspace checks content/linkage without executing a verifier. Saved outcomes
are historical: `retained_runtime_report_requires_fresh_verification`.

Export the native bundle from `bundle.get`, then reverify **without** producing
a new proof:

```sh
python -m ciw proof verify results/original.json \
  --computation-repo /path/to/scr \
  --computation-engine /path/to/native-target/release/execution-cli \
  --sp1-prover /path/to/proof-target/release/sp1-host \
  --sp1-heat-guest /path/to/artifacts/sp1-heat.elf \
  --output results/fresh-verification.json
```

Success exits zero and writes a separately identified report linked to the
original bundle (`verifier_runtimes` / `verifier_runtime_digest` distinct from
the producer's runtime). No supplied verification-key artifact is accepted.
Existing output files are refused.

**Refuse paths** (command exits two)

| Condition | Status |
| --- | --- |
| Malformed source / changed pins | **REFUSED** |
| Missing artifacts | **REFUSED** / **UNAVAILABLE** |
| Mismatched commitments | **REFUSED** |
| Failed verification / resealed-corrupt proof | **REFUSED** (never green) |
| Output path already exists | **REFUSED** |

Paint **VERIFIED** in presentation JSON only when
`fresh_verifier_occurrence: true`. Teaching emits default that field to
`false` — do not invent a fresh occurrence.

## 4. Emit render JSON → Godot / Bevy

Presentation emitters reuse owned pins and strengthen rules. They do **not**
mint proofs or a v2 operation.

```sh
python3 examples/proved-heat/emit_proof_render.py
# → examples/proved-heat/results/proved_heat_render.json

python3 examples/usecase-thermal-proof-gate/emit_render.py
# → examples/usecase-thermal-proof-gate/results/thermal_proof_render.json

# Optional orchestrator (existing emitters only — no fake proofs)
python3 examples/workflows/emit_sp1_teaching_bundle.py
```

```sh
godot --path godot
# Proof tab → proved_heat_render.json
# Thermal proof tab → thermal_proof_render.json
# Missing JSON → STALE

cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- --summary \
  examples/proved-heat/results/proved_heat_render.json
```

Godot **must not reverify**. `HISTORICAL` displays as
`retained_runtime_report_requires_fresh_verification`. No proof bytes in the
viewport. `may_authorize` stays `false`; `claim_scope` is
`computational-integrity-only`.

## 5. ESM candidate retention (UNADMITTED)

After a host-verified bundle exists, an operator may attempt explicit ESM
candidate capture. ESM retains **`UNADMITTED`** envelopes and refuses
canonical admission, state mutation, release activation, and source-truth
claims ([`docs/STATE_DIAGNOSTICS_EVIDENCE.md`](../../docs/STATE_DIAGNOSTICS_EVIDENCE.md)).

Current shared ESM bindings accept calibrated / scalar telemetry bundles
through exact provider/policy pins; identified-design (and other unbound)
schemas still refuse. A proved-heat session is **not** automatically an
admitted ESM schema — treat capture as:

1. Fresh inspect (`esm.inspect-candidate.v1`) — no evidence-store write.
2. Explicit capture (`esm.capture-candidate.v1`) only when the binding and
   policy name this bundle — retained status **`UNADMITTED`**.
3. Binding / policy refuse → **REFUSED** or **UNAVAILABLE**; never paint
   green; never claim qualified admission from a proof alone.

Workbench candidate retention never establishes canonical-state admission
([`docs/WORKBENCH_ASSEMBLY.md`](../../docs/WORKBENCH_ASSEMBLY.md)). Presentation
`may_authorize` remains `false`.

## Installed-wheel gate (acceptance)

When SCR/SP1 binaries and the pinned guest are present:

```sh
python scripts/check_proved_heat.py \
  --scr-repo /path/to/scr \
  --sp1-repo /path/to/notationsystems/SP1-zero-knowledge-virtual-machine \
  --engine /path/to/native-target/release/execution-cli \
  --prover /path/to/proof-target/release/sp1-host \
  --guest /path/to/artifacts/sp1-heat.elf \
  --output-dir results/proved-heat-gate
```

Gate report schema: `ciw.proved-heat-gate.v1`. Required native tests
(no skips / failures / errors):

- `test_native_proved_heat_shared_session`
- `test_native_tampered_proof_fails_fresh_verification`
- `test_native_retained_proof_can_be_reverified_without_reexecution`

Pass line: `PASS: installed workbench, real SP1 proof, fresh replay, verification and tamper rejection`.
Missing providers and skipped tests **fail** this gate. Ordinary local
structural fixtures with synthetic proof bytes are **not** cryptographic
evidence.

Acceptance checklist: [`checklist_sp1.md`](checklist_sp1.md).

## Explicit refuse / unavailable matrix

| Trigger | Presentation / gate |
| --- | --- |
| Binaries absent | **UNAVAILABLE** / **STALE**; pins listed; unavailable ≠ passed |
| Missing proof | **REFUSED**; no successful result |
| Missing / mismatched guest ELF pin | **REFUSED** |
| Resealed-corrupt proof | **REFUSED** (gate rejects) |
| Retained report only | **HISTORICAL** + `retained_runtime_report_requires_fresh_verification` |
| Fresh verify not run | Do not set `fresh_verifier_occurrence: true` |
| ESM binding rejects schema | **REFUSED** / **UNAVAILABLE**; still **UNADMITTED** if retained |
| Godot missing JSON | **STALE** |

## Coverage layers (do not collapse)

Track these **separately**. Teaching emit / catalog presence is not scientific
execution.

| Layer | SP1 / proved-heat meaning | How to record |
| --- | --- | --- |
| Catalog / docs | Workflow 05 + checklist exist; pins cited from `PROVED_HEAT.md` | Present / missing |
| Export | `emit_proof_render` / thermal-proof emit / orchestrator write render JSON | Pass / fail emit |
| Scientific execution | Real `ciw.proved-heat.v1` with pinned guest + SP1 proof | Run / `not_run` / `blocked` / `unavailable` |
| Numerical / teaching check | Bounded lattice statement `[0,100,200,100,0]` → `[0,65,92,65,0]` (unit 1) when execution ran | Pass / fail / `not_run` |
| Fresh verification | Separate `ciw proof verify` occurrence | Pass / refuse / `not_run` |
| Replay | Retained bundle reverify without re-proof; gate fresh replay | Pass / fail / `not_run` |
| Tamper rejection | Resealed-corrupt proof fails fresh verify | Pass / fail / `not_run` |
| Presentation | Godot/Bevy load JSON; never reverify; no proof bytes | Pass / `STALE` |
| ESM retention | Optional candidate capture → **UNADMITTED** only | Retained / binding refuse / **cite-only** (no capture) |

`unavailable` ≠ passed. Synthetic teaching emits do **not** claim a live
cryptographic proof. Installed-wheel gate
(`scripts/check_proved_heat.py`) is the acceptance path for execution +
verification + tamper layers when binaries are present.

### Computational profile (one distinct experiment)

For proved-heat, the distinct executable profile is approximately:

`operation=ciw.proved-heat.v1` × `guest recipe+ELF pins` × `SCR/SP1 pins` ×
`source schema ciw.proved-heat-source.v1` × `expected lattice outcome` ×
`proof-before-result` × `fresh verifier required for VERIFIED`.

Renaming the same profile for different industries does **not** create new
experiments. Application labels (thermal-proof-gate use-case wording) are
discovery metadata on top of that profile.

### ESM: citation vs data binding

Two directions — do not conflate:

1. **Instrument result → ESM** — optional UNADMITTED candidate retention after
   host verification (destination seam).
2. **ESM → instrument inputs** — requires exact artifact digest, selected
   records/fields, and transform. A repo URL or tip SHA is **reference only**,
   not a data integration.

Proved-heat teaching fixtures are **synthetic / computational-integrity-only**.
Label them as such; they are not Caravan or field observations.

## Related paths

| Path | Role |
| --- | --- |
| [`docs/PROVED_HEAT.md`](../../docs/PROVED_HEAT.md) | Claim, pins, verify contract |
| [`docs/JULIA_SP1.md`](../../docs/JULIA_SP1.md) | Development contract (increment 1) |
| [`examples/proved-heat/`](../proved-heat/) | Live session + Proof emit |
| [`examples/usecase-thermal-proof-gate/`](../usecase-thermal-proof-gate/) | Use-case proof gate emit |
| [`checklist_sp1.md`](checklist_sp1.md) | Acceptance checklist |
| [`emit_sp1_teaching_bundle.py`](emit_sp1_teaching_bundle.py) | Orchestrate teaching emits only |
