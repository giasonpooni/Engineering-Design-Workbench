# The zkVM Adapter Boundary

The seam a future SP1 / Nexus / RISC Zero adapter attaches to. Nothing in
this document is implemented against a real backend yet; it is the
contract the substrate holds open, shaped by the Phase 126 source
reconnaissance and repaired by the Phase 128 review.

## What an adapter implements

```rust
impl ProofBackend for Sp1Backend {
    fn backend(&self) -> &BackendId;                 // name + the version its verifier accepts
    fn capabilities(&self) -> VerificationCoverage;  // honestly -- see table below
    fn verify_supported(
        &self,
        artifact: &ProofArtifact,                    // opaque bytes + declared BackendId
        expectation: &Expectation,                   // the statement to check
    ) -> AdapterVerdict;                             // Accept{coverage} / Reject{coverage, failure}
}
```

An adapter never constructs a `VerificationResult`. The sealed
`ProofBackend::verify` screens the expectation against declared
capabilities (`Unsupported`, never success-by-omission), embeds the
expectation in the result (the warrant cannot detach), identifies the
proof from the artifact it examined, and refuses coverage outside
capabilities or below requirements (`AdapterContractViolation`).

## The commitments an adapter mediates

| ours (canonical) | backend-native (opaque, beside ours) |
|---|---|
| `ProgramIdentity` -- SHA-256 of program bytes | RISC Zero ImageID / SP1 vkey hash / Nexus: none, the ELF itself |
| `InputIdentity` -- SHA-256 of canonical input bytes | SP1: nothing; RISC Zero: host-declared `input_digest` (must be zero on the standard verify path); Nexus: the reconstructed input memory |
| `OutputIdentity` -- SHA-256 of canonical output bytes | journal digest / public-values digest / reconstructed output memory |
| `ProofIdentity` -- SHA-256 of (backend, version, proof bytes) | the artifact itself |
| execution statement | the `Expectation` embedded in every `VerificationResult` |

Two obligations follow that the substrate cannot discharge for an
adapter:

**The binding table.** Our `Expectation` names programs by
`ProgramIdentity` (a hash of the bytes). SP1's verifier consumes a
verifying key; Nexus's consumes the whole ELF. An adapter therefore
owns a mapping `ProgramIdentity -> (backend-native commitment | program
bytes)`, established by the adapter itself from the same bytes at setup
time. A Nexus adapter that cannot resolve a `ProgramIdentity` back to
its ELF cannot verify at all -- resolution failure is `Unsupported` or
an explicit failure, never a silent narrowing.

**Version fidelity.** `BackendId.version` must be the version the
adapter's verifier actually accepts; a proof from another version is
`VerificationFailure::VersionMismatch`, never a silent pass (SP1's own
verifier hard-fails on this; RISC Zero binds verifier parameters; Nexus
embeds the memory layout).

## Capability honesty (the trusted boundary, stated as one)

```text
SP1        input_checked: false    SP1Stdin is never hashed, never reaches verify_proof
RISC Zero  input_checked: false    Input is uninhabited; input_digest is host-declared
                                   and must be zero on the standard path
Nexus      input_checked: true     verify_expected reconstructs the full View
```

Stage 3 realized the Nexus row -- with a nuance the recon could not
see: the guest takes input on the PRIVATE tape (the cross-backend
statement must not depend on a facility only one backend has), so
Nexus's `input_checked: true` in OUR adapter comes from the same guest
convention SP1 uses, not from its native public-input binding. And the
confirm-style shape of its verifier added two vocabulary extensions
(`AdapterVerdict::Decline`, `VerificationFailure::StatementMismatch`) --
see `docs/STE_NEXUS_BACKEND.md`.

`capabilities()` is trusted, not verified. It is auditable two ways: the
entry point confines any over-claim to one declared place and refuses
results that exceed it; and a conformance suite can falsify a claimed
capability empirically -- give the adapter a proof for input X and an
expectation for input X', and a backend claiming `input_checked` that
returns anything but a failure has been caught.

## The input-commitment chain (future guest convention)

`input_checked = true` requires every link, and the links are not
equivalent:

```text
1. host observed input X                       -- establishes nothing about the guest
2. host hashed X                               -- still host-side
3. host supplied hash(X) to the guest          -- the guest ECHOING this proves nothing:
                                                  a digest that passes through the guest
                                                  untouched binds nothing
4. guest READ bytes B                          -- what actually entered the execution
5. guest computed H(B) INSIDE the proved
   execution and committed it in its output    -- the only link that binds
6. proof verifies; adapter extracts the
   committed digest and compares it to the
   canonical InputIdentity, under the same
   domain tag and canonical encoding
```

Link 5 is why `execution-serialization` and `execution-commitment` are
`no_std`: the guest must compute the *same* commitment function the host
does, from the same crates, or host and guest are comparing different
functions. Link 3 is RISC Zero's `ExecutorEnv::input_digest` -- a
declaration in exactly Phase 119's sense. The convention's journal
layout must also domain-separate the committed input digest from
ordinary output, or a hostile guest program could emit output that
merely *looks* like an input commitment.

Phase 129 represented links 1-2 and 6's comparison target
(`InputIdentity`, `INPUT_COMMITMENT_INVARIANT`). **STE stage 2 closed
links 4-5**: `zk/guest-pairwise` reads its input, computes the canonical
commitment in-circuit with the same `no_std` `execution-commitment`
crate the host uses, and commits it in its public values under the
`ste.sp1.pairwise-io.v1` layout tag; the SP1 adapter performs link 6's
comparison inside the sealed entry point. `docs/
STE_VERIFICATION_SUBSTRATE.md` records exactly what that does and does
not establish.

## What stays out of the common layer

Backend serialization (bincode / word-serde / postcard+COBS), proving,
program-commitment accessors, proof internals. Phase 126 §10 found none
of these can be shared; none of them appears in the trait.
