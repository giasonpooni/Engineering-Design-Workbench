# Phase 127 -- The Rust Execution Semantic Boundary

> **Revised by Phases 128-129.** The Phase 128 adversarial review found
> two holes in the interface described in §5/§9 of this document -- a
> `Verified` result that did not name the statement it satisfied, and
> adapter-reported coverage passing through the entry point unvalidated.
> Both are repaired: adapters now return an `AdapterVerdict` and the
> sealed entry point assembles every `VerificationResult` with its
> `Expectation` embedded. The current interface is documented in
> `docs/RUST_EXECUTION_ARCHITECTURE.md` and
> `docs/ZKVM_ADAPTER_BOUNDARY.md`; this document remains the Phase 127
> record.

The smallest compilable Rust substrate that SP1 and Nexus can both
attach to **without either backend's semantics being forced into our
canonical model.**

Backend-neutral by construction: no SP1, Nexus or RISC Zero code is
cloned, imported, depended on or referenced by any identifier here. They
are *discussed* throughout, because Phase 126's reading of their source
is why each shape below is the shape it is
(`docs/RUST_EXECUTION_SUBSTRATE_RECON.md`).

```text
crates/
  execution-serialization    canonical encoding: deterministic, injective
        v
  execution-commitment       SHA-256 over canonical bytes -> Commitment
        v
  execution-model            ProgramIdentity / InputIdentity / OutputIdentity
                             ProofIdentity / ExecutionOccurrence
        v
  execution-trace            ExecutionTrace -- mints occurrence numbers
        v
  execution-verification     Expectation / VerificationCoverage
                             VerificationResult / ProofBackend
        v
  execution-core             facade; no logic
```

Zero external dependencies, in every crate. Two independent reasons, and
a test that enforces it
(`tests/test_phase127_rust_semantic_boundary.py::test_the_substrate_has_no_external_dependencies`):
this repository's Python side already declares `dependencies = []`, and
Phase 126 §4 found three mutually incompatible backend encodings, none of
which may become the canonical one by the back door of a shared crate.

---

## 1. What each identity means

| identity | commits to | domain tag |
|---|---|---|
| `ProgramIdentity` | the program bytes -- what was to be run | `scout.execution.program.v1` |
| `InputIdentity` | the canonical input bytes -- what it was to be run on | `scout.execution.input.v1` |
| `OutputIdentity` | the canonical output bytes -- what came out | `scout.execution.output.v1` |
| `ProofIdentity` | the proof artifact, **plus its backend name and version** | `scout.execution.proof.v1` |

Each is `SHA-256` over a canonical encoding, rendered as 64 lowercase hex
characters -- the same primitive and the same form
`evidence/identity.py::content_hash` already uses. That reuse is
deliberate and is checked: `semantics.rs` carries vectors computed by
Python's own `hashlib` and asserts the Rust implementation reproduces
them exactly. A second identity system was the thing to avoid, and this
is the test that would catch one appearing.

What is *not* reused is the canonical-JSON step. Execution identities
commit to raw program and I/O bytes; canonicalising an ELF binary as JSON
would be a category error. The shared primitive is the hash and its hex
form; the encoding beneath it is domain-specific.

**The domain tag is load-bearing, not decoration.** The same bytes
committed as a program and as an input produce different identities.
Without that separation, a program could be mistaken for the input it ran
on. This is the same construction RISC Zero uses for its own structured
hashes (`tagged_struct`, `risc0/binfmt/src/hash.rs:75`).

**`ProofIdentity` binds the version on purpose.** Phase 126 §8: SP1's
verifier hard-fails on version mismatch
(`crates/sdk/src/prover.rs:154`), RISC Zero binds `verifier_parameters`
into the receipt, Nexus embeds the memory layout in the proof. A proof is
verifiable by a *compatible* verifier, not forever. The same proof bytes
under two backend versions are therefore two proofs, and the identity
says so.

---

## 2. Why execution identity differs from content identity

Phase 122 established that this system holds **two ledgers with
contradictory identity rules**:

```text
EVIDENCE ledger      two identical occasions must COLLAPSE to one object
OPERATION ledger     two identical occasions must REMAIN TWO
```

No single object satisfies both. Content addressing implements the first
and is exactly wrong for the second: running the same program on the same
input twice is *two runs*, and a ledger that merges them has destroyed
the fact that it happened twice.

So the substrate splits the question:

```text
same program + same input + same output + same exit code
    = same COMPUTATION            ExecutionOccurrence::computation_identity()
                                  (content-addressed; two runs share it)

execution #1 != execution #2      the occurrence itself
                                  (a process-local monotonic sequence
                                   minted by one ExecutionTrace)
```

That is the same discipline `operations/trace.py` established for the
Python operation ledger in Phase 124, in a second language, because the
rule is not language-specific. Not a UUID (a second identity system), not
a timestamp (two executions can share a clock reading, so it is not an
identity at all), not a content hash (it would collapse the two runs).

`computation_identity()` returns `Option`, and returns `None` whenever
the outcome is `Pending`, `Halted` or `Indeterminate` -- because in each
of those the output is not known. **An unknown output is not the empty
output and is not a zero.** Manufacturing a placeholder to make the
return type simpler is the exact substitution this architecture forbids.

### Scope limit, stated rather than hidden

An occurrence number is meaningful **only within one `ExecutionTrace`**.
Two traces both start at 0. Cross-process occurrence identity is
deliberately unsolved in this phase, and nothing here should be read as
solving it.

---

## 3. Why backend-native commitments are not canonical identities

Phase 126 §5 found the three substrates do not agree on what names a
program:

| substrate | program commitment | pure function of the ELF? |
|---|---|---|
| RISC Zero | 32-byte **ImageID** -- `tagged_struct("risc0.SystemState", [merkle_root], [pc=0])` (`risc0/binfmt/src/elf.rs:435`) | yes -- `compute_image_id(blob)` |
| SP1 | **verifying-key hash** -- `SP1VerifyingKey::bytes32()` (`crates/hypercube/src/verifier/hashable_key.rs:61`) | derivable, but only via an expensive, circuit-version-bound `setup()` |
| Nexus | **none** -- the verifier is handed the whole `expected_elf` and rebuilds program memory (`sdk/src/traits.rs:459`) | n/a; the ELF *is* the commitment |

One backend has no program digest at all. A canonical identity defined as
"the backend's program commitment" would therefore be *undefined* for
Nexus and *version-dependent* for SP1 -- and every historical identity
would change when SP1's circuit version changed.

So `ProgramIdentity` is ours. A backend's native commitment belongs
**beside** it, as an opaque backend-tagged value, never as the identity.
The same holds for proofs: `ProofArtifact` carries `Vec<u8>` and a
`BackendId`, and nothing in this substrate interprets those bytes. Phase
126 §7 found no shared proof structure whatsoever -- RISC Zero's
`Receipt`, SP1's `SP1ProofWithPublicValues` and Nexus's `stwo::Proof`
have nothing in common, and two of the three carry the output inside the
proof while the third does not. Opaque bytes plus a backend tag plus a
version is the most that is true of all three.

---

## 4. What `VerificationCoverage` actually means

```rust
pub struct VerificationCoverage {
    pub program_checked:   bool,
    pub input_checked:     bool,
    pub output_checked:    bool,
    pub exit_code_checked: bool,
}
```

Four independent facts about **what a verifier actually examined** --
deliberately not reducible to one. `VerificationCoverage::NONE` is the
`Default`, because a default that assumed anything had been checked would
be a fabricated warrant with a derive macro in front of it.

The type has **no** `is_complete() -> bool` and **no**
`From<VerificationCoverage> for bool`. Both are guarded structurally.
Either would restore precisely the collapse the type exists to prevent.

A coverage of

```text
{ program_checked: true, input_checked: false, output_checked: true, exit_code_checked: true }
```

is a **real and useful** result. It is **not** complete verification. It
is consistent with the execution having run on an input nobody checked,
and it must never be presented as anything stronger.

The same struct is reused for `ProofBackend::capabilities()` -- what a
backend can check *at all, ever*. Per Phase 126 that is genuinely
different per backend, and an honest adapter says so:

```text
SP1        input_checked: false    SP1Stdin is never committed to
RISC Zero  input_checked: false    Input is uninhabited; input_digest is
                                   host-declared and must be zero
Nexus      input_checked: true     verify_expected binds the input
```

---

## 5. Why verification is not Boolean

This is the design consequence Phase 126 was run to find.

Consider the obvious interface:

```rust
fn verify(proof, expectation) -> bool
```

Given the *same* expectation carrying program, input and output, an SP1
backend returns `true` having checked program and output only; a Nexus
backend returns the *identical* `true` having also checked the input.
**The caller cannot tell them apart and is entitled to believe the
stronger claim in both cases.** That is Phase 111's failure mode -- an
unwarranted claim entering through a gate that *looks* like it checked --
reintroduced by the abstraction itself. `Result<(), Error>` fails
identically: it carries exactly the same single bit, and it is the shape
all three substrates' own verifiers use.

So verification returns three distinguishable outcomes, each carrying
coverage:

```rust
VerificationResult::Verified    { coverage, proof, backend }
VerificationResult::Failed      { coverage, failure, backend }
VerificationResult::Unsupported { capabilities, missing, backend }
```

A `Failed` still reports what was examined, because "it failed" and "it
failed the one thing we could check" are different facts.

### Unsupported expectations cannot silently become success

`Unsupported` is the variant that matters most, and it is enforced
structurally rather than by convention. `ProofBackend` splits the work:

```rust
fn verify_supported(&self, artifact, expectation) -> VerificationResult;  // adapters write this
fn verify(&self, artifact, expectation) -> VerificationResult {           // callers call this
    let capabilities = self.capabilities();
    let missing = capabilities.missing(expectation);
    if !missing.is_empty() {
        return VerificationResult::Unsupported { capabilities, missing, backend: ... };
    }
    self.verify_supported(artifact, expectation)
}
```

An adapter is **never reached** with an expectation its declared
capabilities do not cover. It therefore never has to decide what to do
about a requirement it cannot meet, and cannot answer `Verified` with
`input_checked: false` to a caller who required the input. An SP1-shaped
backend asked to confirm an input lands in `Unsupported`, not in a
qualified success.

Note what a `Verified` does and does not say. A caller who required only
the program gets a `Verified` whose `input_checked` is `false`. That is
**correct** -- the expectation was fully met -- and the coverage stays
visible so nobody reads it as more.

---

## 6. What native execution can and cannot establish

`BackendKind::Native` is a **legitimate backend**, not a placeholder.
This substrate is not "Rust -> SP1"; it is a Rust execution layer with
proving backends attached beside native execution.

**It can establish:** that a program ran on an input, what came out, what
the exit code was, and that this happened -- an `ExecutionOccurrence`
with a `computation_identity()`, on the authority of this process.

**It cannot establish anything cryptographic**, and the substrate refuses
to let it pretend otherwise:
`ExecutionOccurrence::attach_proof` returns
`AttachProofError::NativeExecutionHasNoProof` for every native
occurrence, so `occurrence.proof()` is `None` for a native execution
always, and no code path can make it otherwise.

---

## 7. The guest-input commitment invariant (documented now, not implemented)

```text
A backend may report input_checked = true IF AND ONLY IF the PROVED
EXECUTION ITSELF cryptographically binds the canonical InputIdentity.

A host-side assertion is insufficient.
An externally supplied digest is insufficient.
A digest the host passed to the prover is insufficient.
```

The last line is not hypothetical. RISC Zero's
`ExecutorEnvBuilder::input_digest(digest)`
(`risc0/zkvm/src/host/client/env.rs:428`) is exactly such a digest: the
host declares it, nothing computes it from `env.input`, and the executor
stores `self.env.input_digest.unwrap_or_default()`
(`exec/executor.rs:442`). It is a declaration in precisely the sense
Phase 119 found `extraction_method` to be a declaration -- and Phase 119
proved a declaration is not a witness.

The only construction that works identically on all three substrates is a
**guest-side convention**: the guest reads its input, hashes it, and
commits that hash as part of its own committed output. Then the binding
lives inside the proved execution, where it has to be, and
`input_checked` becomes honestly true on all three backends without the
substrate claiming anything it cannot support.

That convention must live in the guest program. **This is the single
clearest reason the layer belongs in Rust and cannot live in Python.**

The invariant is recorded in the substrate as
`execution_model::INPUT_COMMITMENT_INVARIANT`. The guest mechanism is
Phase 128 work or later and is **not** implemented here.

---

## 8. Exactly what this phase does not establish

- **No proof exists.** No backend is implemented. Nothing in this
  workspace has produced or checked a real proof. The `ScriptedBackend`
  in `semantics.rs` is a test fixture whose every result is stipulated;
  it attests to nothing whatsoever.
- **No claim that a proof witnesses a measurement.** Phase 111b stands
  unchanged: a world where a load frame produced 123.4 and a world where
  a script produced 123.4 are *identical objects* to a content-addressed
  system. A proof witnesses that a **computation** ran as specified. A
  fabricated value can be computed faithfully.
- **No input is bound yet.** `InputIdentity` is our commitment to bytes.
  Until the guest convention of §7 exists, no backend may report
  `input_checked = true`, and the type system here cannot enforce
  honesty about that -- only make dishonesty explicit.
- **No cross-process occurrence identity.** §2's scope limit is real.
- **No integration of any kind.** No Python bindings, no FFI, no
  `EvidencePool`, no `CanonicalState`, no SCOUT, no DAF, no GraphRAG, no
  persistence, no orchestration. The substrate does not know those exist,
  and a guard test keeps it that way.
- **Nothing here is evidence.** No type in this workspace may be admitted
  to `EvidencePool`, and none knows the pool exists.

---

## 9. The interface Phase 128's adapters must satisfy

An SP1 or Nexus adapter implements exactly this, and nothing more:

```rust
impl ProofBackend for Sp1Backend {
    fn backend(&self) -> &BackendId;                        // name + version
    fn capabilities(&self) -> VerificationCoverage;         // honestly
    fn verify_supported(
        &self,
        artifact: &ProofArtifact,                           // opaque bytes + BackendId
        expectation: &Expectation,                          // program (+ optional input/output/exit code)
    ) -> VerificationResult;                                // never bool, never Result<(), E>
}
```

Four obligations the substrate cannot check for an adapter, and which
therefore have to be stated:

1. **`capabilities()` must not over-claim.** A backend that reports a
   capability it does not have has fabricated a warrant, and no amount of
   downstream typing recovers from that. On today's reading, SP1 and RISC
   Zero must report `input_checked: false`.
2. **`input_checked` requires §7.** Not a host assertion, not
   `ExecutorEnv::input_digest`, not a value the caller supplied.
3. **The version in `BackendId` must be the one the verifier actually
   accepts**, and a proof from another version is
   `VerificationFailure::VersionMismatch`, never a silent success.
4. **The backend's native serialization stays inside the backend.**
   Canonical bytes go in and come back out unchanged; `bincode`,
   word-oriented serde and `postcard`+COBS are implementation details of
   three separate adapters and never of this substrate.

What is deliberately **absent** from the trait: serialization, proving, a
program-commitment accessor. Phase 126 §10 found none of those can be
shared, so none of them is in the shared interface.
