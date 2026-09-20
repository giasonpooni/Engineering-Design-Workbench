# Scientific Computation Runtime Stage 5 -- Reproducible Builds: the Declaration Becomes Checkable

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
The question: can "I declare this ELF means X" become "X
deterministically produces this ELF, independently checkable"?
Answer, built and measured: **yes**, with the residue named precisely.

## What was actually built

`execution/build.py`: `GuestBuildRecipe` (content-addressed:
descriptor + full source manifest + toolchain identity + target + flags
+ profile + fork commit -- no timestamps, hostnames, PIDs or
occurrences), `BuildArtifact`, `make_recipe`, `build_from_recipe`
(manifest-verified staging at a canonical path, then a locked, pinned,
flag-controlled cargo build), `verify_build` (the independent-rebuild
root-of-trust operation), recipe persistence whose stored format IS the
canonical bytes, and `rebuild_all_and_write_registry` -> the generated
`execution/guest_registry.py` index plus `zk/recipes/*.recipe` (four
committed recipes) and `zk/artifacts/*.elf` (derived, gitignored).
The proving driver now refuses any ELF whose hash is not the registered
reproducible artifact for the specification's program -- and the
registration is re-derivable by rebuild, so a false one is CATCHABLE.

## Reproducibility: measured, not assumed

Guest builds were NOT naturally reproducible. Found empirically, in
order:

1. **Temporal determinism held** (same tree, fresh target dirs:
   identical ELFs).
2. **Relocation broke it**: absolute source paths embedded as
   panic-location strings (execution-kernel + sp1-zkvm entrypoint
   files). Control: `--remap-path-prefix <root>=/src`,
   `<cargo-home>=/cargo`.
3. **Still broken on the SP1 target at the symbol level and on the
   Nexus target in `.text` itself**: cargo's `-C metadata` fingerprint
   bakes path-dependency package ids (absolute paths) into symbol
   disambiguators; on riscv32 this reordered the code layout.
   Controls: `-C strip=symbols` (the zkVMs load segments, never symbol
   tables) and -- structurally -- **building from a canonical staging
   path** (`/tmp/ste-stage/<backend>-<recipe-id16>`), so the path cargo
   sees is a pure function of the recipe. Staging also makes the
   manifest real: only declared files are staged, so an undeclared
   stray source cannot influence the artifact.

After controls: byte-identical ELFs across relocated source trees on
both targets. Toolchains: succinct (rustc 1.94.0-dev) for
riscv64im-succinct-zkvm-elf; nightly-2025-05-09 for
riscv32im-unknown-none-elf; identities recorded per-recipe from
`rustc -vV` (release/commit-hash/host).

Scope honestly stated: verified across source relocations ON THIS
MACHINE. Cross-machine reproduction (different cargo registry state,
different fork checkout paths) is the designed-for case but was not
demonstrable with one machine; the staging convention and remap flags
exist for it.

## The chain that actually ran

```text
heat ExecutionSpecification
  -> BuildRecipe (nexus-heat: 2245aec9..., sp1-heat: 134673ac...)
  -> reproducible build (staged, locked, pinned)
  -> ELF identity (sp1: a14e3750..., nexus: 6b11f85e...)
  -> registry-gated driver
  -> real execution + SP1 core proof   347 s, vkey 0x003c11f7... derived
                                       from the reproducible ELF
  -> real execution + Nexus stwo proof  17 s
  -> independent verification, both
  -> ONE computation identity ae4198eb... , TWO proof identities
```

Identity sensitivity, all exercised with real rebuilds: modified kernel
source -> different recipe AND different ELF, old identity not
attributable (BuildMismatch); stored recipe vs tampered tree -> refused
at staging, before any build; false artifact claim -> caught by
rebuild; recipe identity separates descriptor / toolchain / flags /
fork commit / per-file source hashes.

## What is now independently verifiable vs still declared

A verifier holding the recipe, the sources, the claimed ELF identity
and a proof -- who does NOT trust our registration -- can now
establish: the sources match the recipe's manifests; the rebuild
converges on the claimed ELF identity; the verification key derived
from THEIR rebuilt ELF verifies the proof; hence the proof is about the
executable those sources deterministically produce.

Still declared, exactly: (1) that the pinned source SEMANTICALLY
implements the descriptor's mathematics -- now pinned to exact
reviewable source instead of an arbitrary binary, but reviewed, not
proven; (2) the verifier's own toolchain binaries match the recorded
toolchain identity (their provisioning problem); (3) the fork's source
integrity, referenced by git commit -- a content hash, independently
checkable against the upstream, not re-hashed file-by-file here.

## Impact

- **SP1 / Nexus**: `ProofBackend` unchanged -- no contract deficiency
  surfaced. Both consume registry-gated reproducible artifacts; the
  vkey / the wholesale ELF are now derived from checkable builds.
- **Morpho HDL**: the lowering target is now sharper -- Morpho lowering
  should emit a BuildRecipe (or an input encoding against a registered
  recipe), inheriting reproducibility instead of re-solving it.
- **Evidence / operations**: untouched; build identities live beside,
  never inside, evidence and operation identities.

## Remaining trust boundary and recommended Stage 6

The semantic link source->descriptor is the last declaration in the
computational chain (physical measurement remains forever outside it).
Recommended Stage 6: put the substrate to scientific WORK -- drive a
real multi-step experiment campaign (the closed loop over one of the
stage-4 workloads with proved dispatches throughout), which will
pressure-test the one seam no stage has yet exercised at scale: many
occurrences, many proofs, one evidence ledger.

---

## Recipe drift, 2026-08-26 — and the thing it caught

The stage-5 checks had been **red for three stages** and were being
carried as known-acceptable failures. They were not acceptable, and
clearing them turned up something no one predicted.

### What had drifted

The recipes were generated at `3f40d23` and never regenerated. Two later
stages — the structural vertical (`539f1d6`) and the Transformer Engine
(`55502b9`) — added **~800 lines** across three manifested files:

| file | change |
|---|---|
| `crates/execution-kernel/src/lib.rs` | +377, purely additive after line 205 |
| `crates/execution-native/src/reference.rs` | +357 |
| `crates/execution-cli/src/main.rs` | +96/−30 |

None of it touched `pairwise_energy` or `heat_diffusion`. The additions
are new kernels (`radius_of_gyration`, `crystal_lattice`,
`hardmax_attention`) and their helpers.

### The wrong fix, and why it was available

Regenerating the recipes makes all three tests green in one command.
That would have been **re-pinning to pass**, and it would have silently
re-registered whatever the tree now builds. So the recipes were not
touched until a rebuild said what the tree actually produces.

### Measured: four identical, one different

| guest | registered | rebuilt | |
|---|---|---|---|
| `nexus-heat` | `6b11f85eae24` | `6b11f85eae24` | identical |
| `risc0-heat` | `692c15bda871` | `692c15bda871` | identical |
| `sp1-heat` | `a14e3750da7e` | `a14e3750da7e` | identical |
| `sp1-pairwise` | `3100b287c976` | `3100b287c976` | identical |
| **`nexus-pairwise`** | `f70da92f180d` | **`46d92372bde1`** | **different** |

**One guest's ELF changed.** Blanket regeneration would have registered
it without anyone noticing.

`DIFFERENT` was then separated from build noise before being believed:
`nexus-pairwise` was rebuilt **twice** and the two rebuilds agree
byte-for-byte, so the build is deterministic and the divergence is real
and source-driven.

### The finding

**An additive change elsewhere in a crate altered one guest's artifact
while leaving four byte-identical — including the same kernel under a
different backend.** `pairwise_energy` was never edited; SP1's pairwise
guest is unchanged; Nexus's is not.

The plausible mechanism is codegen: the new kernels introduce
module-level helpers over the same coordinate decoding, and inlining and
layout decisions in the same compilation unit shift under the Nexus
toolchain's settings but not SP1's. The mechanism is a hypothesis. **The
divergence is measured.**

The inference this kills: *"the kernel function didn't change, so the
artifact didn't."* False, and it would have been reasonable. Only the
rebuild distinguishes them — which is what stage 5 exists to make
possible, and the first time it has paid for itself on something nobody
suspected.

### Disposition

All five recipes regenerated, artifacts rebuilt, registry rewritten
(`python3 -m execution.build`). `zk/artifacts/` is gitignored — the ELF
is a build output and the registry is an index, so the root of trust
stays the independent rebuild rather than a committed binary. No
committed proofs or warrants pinned the old ELF, so nothing verified
under it was invalidated.

**Then re-verified end to end**: 33 tests across stage-5 build, all three
proving backends and the two-backend cross-verification, including a
real proof produced and verified against the *rebuilt* `nexus-pairwise`.

### Also cleared: two stale assertions

`test_a_wrong_program_specification_is_refused_before_proving`
(SP1 and Nexus) asserted `pytest.raises(..., match="not registered")`
against a message stage 5 itself had rewritten to *"no built guest is
registered…"*. The refusal has worked correctly throughout; only the
regex was stale. A stale `match=` is the worst of both — it fails
loudly and says nothing true, costing a green suite and buying no
coverage.

### Why this mattered beyond the five tests

A suite with known-acceptable failures **erodes**: the sixth gets added
because five were already there, and the fifth was carried because four
were. The cost here was not the noise. It was that a genuine artifact
divergence sat inside the accepted-red set for three stages, looking
exactly like the four benign ones.
