# Scientific Computation Runtime Stage 2 -- The Verification Substrate

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
`Verified` as an EARNED computational property. The chain this stage
makes real:

```text
ExecutionSpecification
      |
   native execution          run_specification -- the checked engine
      |
   SP1 core proof            sp1-host prove -- real CPU prover, real
      |                      circuit; NO mock path exists in the adapter
   independent verification  sp1-host verify -- the sealed
      |                      ProofBackend::verify entry point
      |
   VerifiedExecution / ProvedRun -- exists ONLY when everything agreed
```

## What a verified proof establishes (requirement 3, precisely)

Assuming SP1 circuit soundness at the verifier's version:

1. **Execution correctness** -- the RISC-V program bound to the
   adapter's verifying key executed under SP1 semantics.
2. **Input commitment** -- that execution READ bytes whose canonical
   commitment (`scout.execution.input.v1`, computed INSIDE the proved
   execution by the same `no_std` `execution-commitment` crate the host
   uses) is the one in the public values. This is links 4-5 of the
   chain `docs/ZKVM_ADAPTER_BOUNDARY.md` specified, now closed: the
   recon's `input_checked: false` for SP1 was a fact about the
   SUBSTRATE; the guest convention is the one honest upgrade, and it is
   what the guest (`zk/guest-pairwise`) does.
3. **Output commitment** -- it produced bytes with the committed output
   commitment, or halted with the committed fault code and NO output
   (a marker byte; never a zeroed digest).
4. **Exit code** -- as committed.
5. **Specification identity** -- bound by composition: the expectation
   carries the program identity and the input identity, which together
   with configuration ARE the specification's content.

**One declared link, stated rather than hidden:** the proof binds the
GUEST ELF (via its verifying key, reported as `vkey_hash` beside our
identities). The claim that this ELF implements
`PAIRWISE_ENERGY_DESCRIPTOR`'s semantics is a **registered binding** --
made credible by both substrates compiling the *identical*
`execution-kernel` function (extracted `no_std` in this stage precisely
so there is one implementation, not two claimed-equal ones), and checked
empirically on every proved run (the guest's committed output must equal
the native run's output), but not itself proven.

## What it can never establish (requirement 4)

That the input corresponds to a physical event. A fabricated value is
computed -- and proved -- faithfully. Phase 111b survives proof
generation unchanged; the guest's own docstring, the adapter's docs, and
`computation_is_not_measurement` (still passing) all say so. Nothing in
`zk/`, `execution/proving.py`, or the substrate ever claims measurement,
and `VerifiedExecution` is a computational object that no pool accepts.

## Hard failure (requirement 8), twice over

- **Type level:** `VerifiedExecution::from_result` yields `Some` only
  for `Verified`; from `Failed` or `Unsupported` there is NOTHING --
  no object, no flag to ignore. `ProvedRun` (Python) likewise has no
  `verified` attribute to consult; failure is an exception, success is
  existence.
- **Pipeline level:** `proved_runner` raises on any disagreement --
  guest-vs-host commitment mismatch, halted guest, non-verified outcome
  -- and the exception propagates through the dispatch seam like any
  dispatch failure: the operation ledger records FAILED and nothing is
  admitted. There is no code path on which an unverified result
  proceeds to the evidence path with a flag set to false.

## The capability model (requirement 11)

`ProofBackend::capabilities()` is per-backend and per-guest, not
per-marketing-page. This SP1 adapter reports COMPLETE **for this one
registered guest**, each dimension with a mechanism: program via the
verifying key + registered binding; input via the guest convention;
output and exit via the committed public values. A future Nexus adapter
implements the same trait with its own honest set; a backend that
cannot prove a workload declines it (`Unsupported`), it does not
approximate it.

## Two-ledger separation (requirement 9) -- unchanged and retested

The proved E2E test runs the full loop with the proved runner: the
observation admits with the same evidence-identity discipline as stage
1, the operation trace mints occurrences, and the observation's
semantic content carries no proof or execution bookkeeping.

## Artifacts and reproduction

- Succinct toolchain `succinct-1.94.0-64bit`, linked into rustup as
  `succinct` (downloaded from the GitHub release; the API endpoint is
  blocked in this environment, direct release downloads are not).
- Guest: `zk/guest-pairwise`, built with
  `RUSTUP_TOOLCHAIN=succinct cargo build --release --target
  riscv64im-succinct-zkvm-elf` and the sp1-build flag set
  (image-base `0x7800_0000`, `panic=abort`, lower-atomic).
- Host: `zk/` workspace, `cargo build --release` (stable toolchain),
  path-dependent on the SP1 fork checked out at
  `../notationsystems/SP1-zero-knowledge-virtual-machine` (b38b612).
- The substrate workspace (`crates/`) remains zero-dependency; the
  dependency arrow is adapter -> substrate only, and the crates/ guards
  still hold.

## Measured facts from this environment

First real proof (argon-pair geometry, the system the GROMACS workload
evaluated, scaled onto the integer grid): SP1 core mode, CPU (4 cores,
15 GB), **2m37s wall**, proof bundle 2.78 MB, backend `sp1-cpu v6.1.0`,
vkey hash `0x00713b31...dea3f9`. The guest's in-circuit input commitment
and output commitment matched this layer's independent recomputations
exactly on the first run -- the cross-language, cross-substrate
commitment function agreement held under the zkVM, not only under test
vectors.

## What remains unproven / out of scope

GROMACS's own arithmetic (a zkVM cannot run GROMACS; the proof covers
the kernel's computation over the same argon-pair geometry the GROMACS
workload evaluated, and no test claims more); compressed/Groth16 proof
modes; the Nexus adapter; cross-machine proving determinism; proof
archival policy. And, permanently: physical measurement.
