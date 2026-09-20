# Phase 129 -- The Computational Execution Substrate

Phase report. Built on the model that survived the Phase 128 adversarial
review, whose findings are recorded first because they determined every
shape below.

## The Phase 128 review, compressed

Five probes ran against the Phase 127 substrate (scratchpad only; never
committed). Verdict: the identity model survived; the verification
result shape did not.

| probe | finding | disposition |
|---|---|---|
| 1 | **The detachable warrant.** `Verified{coverage, proof, backend}` did not name its statement: verifying one artifact against program A and program B produced IDENTICAL result objects. | REPAIRED: every result embeds its `Expectation`; the sealed entry point embeds it, not the adapter. |
| 2 | **Coverage inflation.** The entry point screened capabilities before dispatch but forwarded the adapter's claimed coverage unexamined -- `input_checked: true` escaped a backend declaring `input_checked: false`. | REPAIRED: adapters return `AdapterVerdict`; the entry point assembles results and refuses out-of-capability or under-requirement coverage as `AdapterContractViolation`. |
| 3 | **"Canonical input" is a caller-kept promise.** Two byte orderings of one logical mapping get two identities. | DOCUMENTED, not "fixed": the substrate hashes bytes; canonicalization is upstream, and the reference workload ships `encode_positions` as its one canonical encoding. |
| 4 | **Nondeterminism.** Same program+input, two outputs -> two computations. | SURVIVES: this is the case that kills `program+input` as computation identity -- it would have fabricated an equality between different results. |
| 5 | **Exit code is part of the computation.** | SURVIVES as built. |

Further review verdicts: `ExecutionSpecification` rejected for absence
of a consumer (Phase 123's no-purpose-independent-equivalence result);
`ComputationIdentity` promoted to a newtype so type-level confusion of
digests is impossible; three verification outcomes sufficient
(verifier-unavailable is a construction-time error); capability honesty
classified as a TRUSTED ADAPTER BOUNDARY, auditable via the entry-point
clamp plus future tamper-vector conformance tests; six-crate structure
retained -- serialization vs commitment is a proven-vs-assumed trust
boundary (injectivity proven by construction; collision resistance
assumed of SHA-256), and both stay `no_std` because a future guest must
compute the same commitment function the host does.

## What Phase 129 built

| | |
|---|---|
| files | `crates/execution-native/` (new crate: `lib.rs`, `reference.rs`), `execution-verification/src/lib.rs` (rewritten), `execution-model/src/lib.rs` (+`ComputationIdentity`), `execution-core` (facade + `tests/adversarial.rs`), guard updates in `tests/test_phase127_rust_semantic_boundary.py`, three docs |
| crates | 6 -> 7: `execution-native` added (std; the five identity/verification crates stay `no_std`) |
| types added | `ComputationIdentity`, `AdapterVerdict`, `VerificationFailure::AdapterContractViolation`, `DeterministicProgram`, `NativeCompletion`, `NativeFault`, `NativeExecution`, `PairwiseEnergyKernel` |
| identities added | `ComputationIdentity` (newtype over the existing commitment -- no new hash) |
| identities deliberately NOT added | specification/task identity (no consumer), cross-process occurrence identity (unsolved, stated), UUIDs, timestamps, an `ExecutionRecord`, any provenance abstraction |
| tests | 54 Rust (30 prior semantic + 6 kernel + 18 adversarial incl. cases A-L, both probe inversions, the end-to-end walk) + 12 Python guards; full Python suite 1914 |
| dependencies added | none |
| dependencies deliberately avoided | `sha2`/`ring` (version-binding identity), `serde`/`bincode`/`postcard`/`borsh` (Phase 126 §4), `uuid`/`chrono` (second identity system; clocks are not identity), `rand` (determinism is the product) |

## The six questions

**What can the Rust layer establish?** By construction: identity
determinism and domain separation; that two runs of one computation are
two occurrences with one `ComputationIdentity`; that history is written
once; that a native execution can never carry a proof; that an
unsupported requirement can never become a success; that a warrant
cannot detach from its statement; that coverage cannot inflate past
declared capabilities.

**What can it only record?** Outcomes, exit codes, computation
identities, which backend ran what -- honestly, without judging any of
it.

**What remains caller-declared?** That a native program's canonical
bytes describe its function (`native_program_identity_binds_bytes_not_
behavior` demonstrates the gap); that input bytes are the canonical
encoding of the logical input; an adapter's `capabilities()`; the
`BackendId` on a `ProofArtifact`.

**What remains unverifiable?** That any input was ever measured; that
any computation models the world. `computation_is_not_measurement` holds
Phase 111b as an executable assertion.

**What would a zkVM prove that NativeBackend cannot?** Exactly the
declared coupling: that the program named by the commitment is the
program that RAN, over inputs the execution actually read (given the
guest convention), producing the committed output -- checkable by a
party who trusts neither this process nor its operator.

**What remains impossible for a zkVM to prove?** That the input
corresponds to a physical event. A fabricated value can be computed --
and proved -- faithfully.
