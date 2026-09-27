# proved-heat (operation + Proof presentation)

Shared operation `ciw.proved-heat.v1` (no v2). See
[`docs/PROVED_HEAT.md`](../../docs/PROVED_HEAT.md) for the exact computational
claim, runtime pins, and fresh-verification contract.

## Live session (requires pinned SCR/SP1 binaries)

```sh
python -m ciw serve \
  --computation-repo /path/to/scr \
  --computation-engine /path/to/native-target/release/execution-cli \
  --sp1-prover /path/to/proof-target/release/sp1-host \
  --sp1-heat-guest /path/to/artifacts/sp1-heat.elf \
  --output-dir results/proved-heat-session

python examples/proved-heat/run.py --replay
```

Source: [`source.json`](source.json) (`ciw.proved-heat-source.v1`).

## Godot Proof tab (HOST presentation)

Emit local presentation JSON for the **Proof** tab. Godot **must not reverify**.

```sh
python examples/proved-heat/emit_proof_render.py
# → examples/proved-heat/results/proved_heat_render.json  (gitignored under results/)
```

### Pins (from docs/PROVED_HEAT.md exactly)

| Component | Identity |
| --- | --- |
| SCR source | `a59aba283b0304faeeb3e5d305087e7709e171ca` |
| SP1 source | `b38b61209e45e969289e70d5cf79dc763460bc41` |
| Guest ELF SHA-256 | `a14e3750da7e221d31842bd6cf983fcc8c0f530b2811537e2a9a9fe803dacf82` |
| Guest recipe | `6e5d1687bcc55243d712553a2b7768b6c587a76418bb48a7a2c44224470d423d` |
| Backend | `sp1-cpu v6.1.0` |

### Presentation rules

- **proof-before-result**
- Separate cards for **execution** / **result** / **verification** identities
- Label every retained report: `retained_runtime_report_requires_fresh_verification`
- Missing proof / missing guest ELF pin / resealed-corrupt → **REFUSED** card, never green
- Binaries absent → **UNAVAILABLE** / **STALE** with pins listed; unavailable ≠ passed
- Statement scope: bounded registered guest only
  (`[0,100,200,100,0]` → `[0,65,92,65,0]` teaching)
- Non-claims: not Gaussian update, not observations, not building-safe, not
  physical heat, not state admission; JSPT owns sensitivity

```sh
godot --path godot
# Proof tab loads ../examples/proved-heat/results/proved_heat_render.json
# or pass an explicit proved_heat_render.json path after --
```

Workflow: [examples/workflows/05_sp1_verifiable_experiment.md](../workflows/05_sp1_verifiable_experiment.md).
