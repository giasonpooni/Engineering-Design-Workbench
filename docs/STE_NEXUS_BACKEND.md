# Scientific Computation Runtime Stage 3 -- Nexus, the Second Implementer

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
The critical architectural test: is `VerifiedExecution` a verified
computational fact, or an SP1 fact wearing a neutral name? Method:
implement `NexusPairwiseBackend` behind the unchanged `ProofBackend`
trait, prove the SAME pairwise-energy statement over the SAME argon-pair
geometry, and compare.

**Fork revision:** `nexus-zkvm` `f2ad126` (workspace 0.3.6), stwo prover
(`stwo` pinned at starkware-libs rev `0790eba`), guest target
`riscv32im-unknown-none-elf`, toolchain `nightly-2025-05-09` (the fork's
own pin). All APIs below were read from this revision's source, not from
documentation.

## Verdict of the architectural test

**The contract held -- with two substrate-specific dimensions found and
named, both absorbed by small earned extensions to the shared
vocabulary rather than by bending either backend.**

### Dimension 1: extract-style vs confirm-style verification

SP1's verifier EXTRACTS the committed statement from the proof's public
values and compares per field. Nexus's verifier
(`Verifiable::verify_expected`, `sdk/src/traits.rs:451`) can only
CONFIRM: it reconstructs the entire expected execution view -- public
input bytes, exit code, public output bytes, **the full ELF**,
associated data -- and checks the proof against it in one aggregate act.
A Nexus proof does not carry a readable statement at all
(`Proof { proof, memory_layout }`, `sdk/src/stwo/seq.rs:61`).

Consequences, expressed through the contract:

- **A partial expectation is unanswerable on Nexus.** New
  `AdapterVerdict::Decline { missing }`, mapped by the sealed entry
  point to `Unsupported` -- an unanswerable question stays visibly
  unanswered. (Capability screening covers asking MORE than a backend
  can check; Decline covers asking LESS than a confirm-style backend
  needs.)
- **A failed confirmation is unattributable.** New
  `VerificationFailure::StatementMismatch`: the proof does not prove the
  claimed statement, and this substrate cannot say whether input, output
  or exit was the wrong part. The tamper tests assert this honestly --
  the same altered input that SP1 rejects as `InputMismatch`, Nexus
  rejects as `StatementMismatch`. Reporting `InputMismatch` there would
  be manufactured precision.

### Dimension 2: the program commitment (already known, now exercised)

Nexus has no program digest -- the ELF is the commitment, and the
verifier requires it wholesale (Phase 126 §5, confirmed in use). The
adapter holds the ELF and registers the descriptor binding, exactly as
the SP1 adapter registers its verifying key. Because the canonical
`ProgramIdentity` was fixed at the DESCRIPTOR level in Phase 127 --
never a backend's native commitment -- both backends answer expectations
naming the SAME program identity. That decision is what makes the
two-proof/one-statement diagram possible at all.

## What is identical across the two backends (tested with real proofs)

One `ExecutionSpecification` (same identity), one `ProgramIdentity`
(descriptor-level), one `InputIdentity`, byte-identical outputs, one
`OutputIdentity`, one `ComputationIdentity` -- because native backend,
SP1 guest (riscv64) and Nexus guest (riscv32) all compile the ONE
`execution-kernel` crate and the ONE `execution-commitment` crate. The
statement is substrate-independent; only the warrants differ: two proof
systems, two artifacts, two `ProofIdentity`s, two `BackendId`s.

The guest input arrives on Nexus's PRIVATE tape deliberately: Nexus can
bind public input natively, but the cross-backend statement must not
depend on a facility only one backend has. The input binding both share
is the in-circuit commitment -- the same mechanism, the same `no_std`
crate, on both.

## Investigations (from source, this revision)

- **Execution identity:** none native. A Nexus execution is transient;
  the `View` is reconstructible state, not an identity. Our
  occurrence/computation identities apply unchanged.
- **Guest/program identity:** the ELF itself; no digest anywhere.
- **I/O commitment facilities:** public input/output segments,
  postcard+COBS encoded, word-aligned; private tape via ecall. `View`
  offers `public_input_digest`/`public_output_digest` helpers (host-side
  conveniences, not in-proof commitments).
- **Proof artifact identity:** none native; `Proof` is (stwo proof,
  memory layout). Our `ProofIdentity` (backend+version+bytes) applies.
- **Verifier identity/version:** no version string in the artifact
  (unlike SP1's `sp1_version`); compatibility is structural (memory
  layout embedded in proof, circuit shape). We carry `0.3.6@f2ad126` in
  `BackendId` -- a declaration, honestly labeled.
- **Recursion/continuations:** the stwo path proves in `k`-sized chunks
  (`k_trace(elf, ad, public, private, 1)` -- the SDK passes k=1); the
  legacy Nova/HyperNova folding stack (`sdk/src/legacy/`) is the
  continuation-native lineage but is feature-gated legacy code. Large
  scientific workloads on the current path would lean on chunked
  proving; untested here and out of stage scope.
- **CPU proving feasibility:** measured -- see the stage report numbers.
- **Floating point:** both zkVMs execute RISC-V integer ISAs (RV32IM /
  RV64IM); floating-point arithmetic is software-emulated at massive
  cycle cost, and cross-platform FP determinism pitfalls would return at
  the semantic level. A fundamental practical limitation for
  FP-heavy scientific code, and the reason the kernel's integer
  discipline is not incidental: **integer/fixed-point formulations are
  what make scientific kernels provable.**
- **Is the pairwise kernel representative?** As arithmetic: yes for the
  class of pairwise-interaction accumulations (the shape of
  short-range MD energy loops). As scale: no -- it is a minimal proof
  substrate, and chunked/recursive proving plus precompiles would be
  the path to anything GROMACS-shaped. The honest statement stands: a
  zkVM will not run GROMACS; it can run distilled integer kernels that
  a scientific pipeline commits to as specifications.

## Environment notes

The fork pins `nightly-2025-05-09` (rustc 1.88-nightly) but ships no
lockfile; `educe 0.5.11 -> enum-ordinalize 4.4.x` now declares MSRV
1.89, so a fresh resolution refuses the fork's own pinned toolchain --
upstream reproducibility rot, worked around with
`--ignore-rust-version` (the declared MSRV is a metadata bump; the code
compiles). Recorded because it is exactly the version-drift failure
mode Phase 126 §8 predicted for proof stacks.
