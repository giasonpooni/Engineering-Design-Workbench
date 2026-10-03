# The Rust Execution Architecture (Phase 129)

Computation as a first-class, deterministic, inspectable, event-traceable
object -- **without contaminating the evidence ledger.** This document
describes the substrate as built; `docs/ZKVM_ADAPTER_BOUNDARY.md`
describes the seam future proving backends attach to;
`docs/PHASE_129_EXECUTION_SUBSTRATE.md` is the phase report, including
the Phase 128 review that determined this shape.

```text
crates/
  execution-serialization   canonical(tag, fields): deterministic, injective   [no_std]
  execution-commitment      SHA-256 over canonical bytes -> Commitment         [no_std]
  execution-model           ProgramIdentity / InputIdentity / OutputIdentity
                            ProofIdentity / ComputationIdentity
                            ExecutionOccurrence / ExecutionOutcome             [no_std]
  execution-trace           ExecutionTrace: mints occurrence numbers           [no_std]
  execution-native          DeterministicProgram / execute() / the
                            reference workload                                 [std]
  execution-verification    Expectation / AdapterVerdict / VerificationCoverage
                            VerificationResult / ProofBackend                  [no_std]
  execution-core            facade; no logic
```

Zero external dependencies in every crate. Dependencies avoided by name:
`sha2`/`ring` (a hash dependency would version-bind every identity),
`serde`/`bincode`/`postcard`/`borsh` (Phase 126 §4: three backends,
three incompatible encodings, none may become canonical through a shared
crate), `uuid`/`chrono` (a second identity system; a clock is not an
identity), `rand` (determinism is the product).

## The three ledgers and their identity rules

| ledger | identity rule | carrier |
|---|---|---|
| EVIDENCE | two identical occasions **collapse** | `evidence.identity.content_hash` (Python, untouched) |
| OPERATION | two identical occasions **remain two** | `operations/trace.py` (Python) / `ExecutionTrace` (Rust) |
| COMPUTATION | what was computed, content-addressed | `ComputationIdentity` (Rust) |

```text
same program + same input + same output + same exit code
    = same ComputationIdentity            (two runs share it)
execution #1 != execution #2              (the trace keeps them apart)
```

`ComputationIdentity` is a newtype over `Commitment` (Phase 128's
direction): the domain tag already separates the digests; the newtype
separates the types, so a computation digest cannot be handed where a
proof or evidence digest is expected.

`computation_identity()` is `None` for `Pending`, `Halted` and
`Indeterminate` outcomes. An unknown output is not the empty output and
is not a zero; the reference kernel enforces the same rule one level
down by *faulting* on a coincident-particle pair rather than
contributing a zero term.

**Not built, deliberately:** `ExecutionSpecification`. The Phase 128
review found it would be a content-addressed *task* identity
(program+input) with no consumer, resting on exactly the
purpose-independent operation equivalence Phase 123 proved does not
exist. The occurrence already carries `(program, input, backend)`; any
future consumer wanting "same task" can derive it, and must argue for it
then. Likewise not built: `ExecutionRecord` (nothing requires it), any
generic provenance abstraction, UUIDs, timestamps-as-identity,
persistence, Python bindings.

## Native execution: the honest backend

`execution-native` runs a `DeterministicProgram` and records the run:

```text
program bytes -> ProgramIdentity
input bytes   -> InputIdentity
run           -> ExecutionOccurrence   (BackendKind::Native)
completion    -> OutputIdentity + exit code -> ComputationIdentity
fault         -> Halted { exit_code }       -> no computation identity
```

It produces no proof and cannot borrow one: `attach_proof` refuses every
native occurrence by construction. There is no fake proof generation and
no mock receipt anywhere in the workspace.

**The declared coupling.** A native `ProgramIdentity` commits to the
program's *canonical bytes*; its *behavior* lives in a Rust function,
and nothing verifies the coupling. `adversarial.rs::
native_program_identity_binds_bytes_not_behavior` demonstrates the
consequence rather than hiding it: two programs declaring identical
bytes but computing different functions share one `ProgramIdentity`, and
the lie surfaces only as divergent computations under it. **Closing that
gap is what a zkVM backend is for** -- there, the program commitment is
computed from the artifact the machine actually executed.

The same test file demonstrates the configuration analogue (case C):
configuration folded into the canonical bytes is two programs;
configuration hidden from them is one program identity with divergent
computations -- visible as a contradiction, preventable by nothing.

## The reference workload

`reference::PairwiseEnergyKernel` -- an integer pairwise inverse-power
energy kernel, Lennard-Jones-*shaped* (repulsive short-range minus
attractive long-range term). Positions in as `i32` LE triples, energy
out as `i128` LE. Entirely integer arithmetic: floating point would make
"deterministic" contingent on FMA contraction and libm versions;
integers make it a property the tests exercise.

It is **not** a materials primitive, is not physically parameterised,
and asserts nothing about any material. `materials/` remains the only
home of scientific mathematics; this kernel exists so the substrate has
one honest scientific-computation-shaped workload to demonstrate
identity semantics against. Its canonical descriptor spells out its
exact semantics, so a future zkVM guest implementing the same semantics
can carry the same descriptor -- and therefore the same
`ProgramIdentity`.

## Verification (as repaired by Phase 128)

Three outcomes, every one naming the statement it answered:

```rust
Verified    { expectation, coverage, proof, backend }
Failed      { expectation, coverage, failure, backend }
Unsupported { expectation, capabilities, missing, backend }
```

Adapters return an `AdapterVerdict` (`Accept { coverage }` /
`Reject { coverage, failure }`) and never construct the result. The
sealed `ProofBackend::verify`:

1. screens the expectation against declared `capabilities()` --
   an uncheckable requirement becomes `Unsupported`, never a success;
2. embeds the expectation verbatim and identifies the proof from the
   artifact actually examined -- the warrant cannot detach from its
   claim (Phase 128, probe 1);
3. refuses claimed coverage outside capabilities, or an acceptance
   covering less than the expectation requires, as
   `AdapterContractViolation` -- coverage cannot inflate (probe 2).

`VerificationCoverage` remains four independent booleans, defaults to
`NONE`, and has no `is_complete()` and no conversion to `bool`.

## COMPUTATION ≠ MEASUREMENT

A completed execution -- native today, proved under a zkVM later --
establishes:

> "this program transformed input X into output Y"

It does **not** establish:

> "input X was physically measured."

World A: `123.4` was read off a load frame. World B: `123.4` was typed
into a script. The bytes are identical, so every identity in this
substrate is identical, so the computations are identical. No execution
substrate can tell the worlds apart, and a proof does not change that: a
fabricated value can be computed faithfully. This is Phase 111b, and it
is held as an executable assertion
(`adversarial.rs::computation_is_not_measurement`): any future change
that makes that test fail is claiming to witness physical history from
content, and is wrong.

Nothing in this workspace is evidence. No type here may be admitted to
`EvidencePool`, and none knows the pool exists -- a Python guard test
keeps the workspace free of any reference to it.

## What the layer establishes / records / leaves unverifiable

| | |
|---|---|
| **establishes** (by construction) | identity determinism, domain separation, occurrence distinctness, once-written history, native-cannot-prove, unsupported-cannot-succeed, warrant-carries-statement, coverage-cannot-inflate |
| **records** (without judging) | outcomes, exit codes, computation identities, which backend ran what |
| **caller-declared** (trusted, stated as such) | that canonical bytes describe the function (native), that input bytes are the canonical encoding of the logical input, adapter capability honesty, `BackendId` on a `ProofArtifact` |
| **unverifiable from here, forever** | that any input was measured; that any computation models the world |
