# Scientific Computation Runtime Stage 10 — The Reusable Verification Artifact

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
## The measured bottleneck, decomposed

Stage 9's structural campaign ended on a number: SP1 cached-warrant
re-verification at **73.4 s/hit** (219.9 s of a 220.0 s campaign wall).
Stage 10 began by instrumenting the host (`timing <component>_ms` on
stderr) and measuring where that time actually goes:

| component | measured |
|---|---|
| `client.setup(elf)` — full **proving-key** generation | ~79.8–84.0 s |
| actual cryptographic verification (`client.verify`) | **0.13 s** |
| proof deserialization + statement checks | inside the 0.13 s |
| filesystem I/O, process startup | noise |

First surprise, discovered by building: reconstructing only the
verifying key still cost **75.2 s** — because
`ProverClient::builder().cpu().build()` itself constructs the full CPU
**prover node**. The expensive state was never the key; it was the
prover machinery a verifier does not need. The SDK ships the answer:
`LightProver` — *"only executes and verifies but does not generate
proofs"* — which builds in **~0.5 s** and verifies through the SDK's
**identical** `verify_proof` path.

## The artifact

`sp1-host export-vk <elf> <descriptor> <out>` runs setup ONCE and
persists **398 bytes**:

    ste-sp1-verification-artifact v1
    backend sp1-cpu v6.1.0
    program <ProgramIdentity of the registered descriptor>
    elf_sha256 <sha256 of the reproducible guest ELF>
    vkey_hash <SP1 bytes32 commitment of the verifying key>
    payload <length>
    <bincode SP1VerifyingKey>

`sp1-host verify-vk <artifact> ...` reconstructs a **verify-only**
backend (`Sp1KernelBackend::from_verification_artifact` → `LightProver`
+ deserialized key) and runs the same sealed `ProofBackend::verify` as
always. Loading fails closed on *any* disagreement: malformed header,
backend/SDK version mismatch, payload length or deserialization
failure, a `vkey_hash` that does not **re-derive** from the payload, or
a program binding differing from the caller's registered descriptor.
The Python layer adds an end-to-end provenance gate: the artifact's
recorded `elf_sha256` must equal the sha256 of the Stage 5 registered
ELF for the specification, or `verify_existing_proof` refuses. There is
**no fallback**: a rejected artifact is a hard error, never a silent
detour through the slow path.

Identity discipline: the artifact commits to backend name, SDK/circuit
version, program binding, source-ELF hash, and the verifying key
itself. Nothing temporal, host-local, or occurrence-shaped. It answers
a different question than `ExecutionSpecification` (what to compute),
the proof identity (which proof), or the operation ledger (what
happened) — a fifth object: *which verifier machinery*.

## The trust invariant, unchanged

The cache still holds bytes; the artifact holds machinery. The flow is

    WarrantCache → proof bytes → VerificationArtifact (LightProver + vk)
        → FRESH verification → VerifiedExecution

and there is nowhere in the 398 bytes a verdict could live. The battery
demonstrates it on real artifacts: a corrupted **proof** still fails
through the artifact path (a cached verdict would have said
"verified"); statement tampering (input/output/exit) still yields the
attributable mismatches; a real **Nexus proof** of the same statement
fails as `Malformed` through the SP1 artifact (backend-specific
machinery, computation identity backend-independent); the **heat**
guest's artifact is refused for a **pairwise** statement at load
(program binding); a corrupted artifact payload or tampered header
fails closed before any cryptography; a forged `elf_sha256` header
passes the Rust internal checks and is caught by the Python registry
cross-check. `prove` on an artifact-constructed backend refuses
structurally (`pk` is absent).

One boundary made explicit while testing: the Stage 5 registry gate is
**per-program**, not per-backend — the Nexus pairwise ELF is a
registered artifact for the pairwise program, so exporting "against"
it passes the gate and then fails in the SP1 host itself (a hard
process error: the ELF is not SP1-loadable). Fail-closed either way;
the backend-level separation lives in the statement key and the
verifying key, as it has since Stage 8.

## Measured results

| | Stage 9 (setup per hit) | Stage 10 (persisted artifact) |
|---|---|---|
| SP1 hit re-verification | **73.4–84.4 s** | **0.6–0.8 s** (load ~0.5 s + verify 0.13 s) |
| structural campaign B wall (8 hits, warm cache) | **220.0 s** | **3.5 s** (98.4% reduction) |
| artifact size | — | **398 bytes** |
| artifact construction (one-time `export-vk`) | — | ~80 s (amortized after the **second** verification) |
| peak verifier memory (child RSS) | **7113 MB** (CpuProver setup) | **50 MB** (LightProver) |
| cryptographic verification itself | 0.13 s | 0.13 s — identical, identical path |

Campaign B (warm cache + artifacts) reproduced campaign A exactly:
10/10 successes, 8 hits all re-verified, water still carrying Nexus
**and** SP1 warrants, observations/unique 10/8, occurrences 10, and
evidence **asserted** identical to the unproved baseline. Two
verifications of one warrant remain two `WarrantRecord`s with one
proof/computation identity — operations never collapse, content always
does.

## Backend survey (§16, answered by measurement)

Hit re-verification measured per backend: **Nexus 0.1 s**, **RISC Zero
0.05 s**, SP1 (pre-artifact) 73.4 s. No verification artifact is
justified for Nexus or RISC Zero — their verifier construction is
already cheap — so none was built. The `ProofBackend` interface is
untouched; the artifact is SP1-specific machinery behind the existing
backend boundary, exactly where backend-specific setup belongs.

## Claim classification

**MEASURED**: every number above; the LightProver discovery sequence
(84.0 s setup → 75.2 s naive vk-only → 0.6 s light); campaign B's
3.5 s wall and evidence invariance; each failure-battery outcome.

**STRUCTURALLY GUARANTEED**: no verdict field exists in the artifact;
every hit still executes `ProofBackend::verify`; an
artifact-constructed backend cannot prove; load-time validation
precedes any use; the Python provenance gate ties artifacts to the
Stage 5 registry.

**CALLER-DECLARED**: the descriptor↔ELF semantic binding (Stage 4
posture, unchanged — the vk binds the ELF cryptographically, the
descriptor binding is registered); which lane has an exported artifact
(the `.vkart` sibling convention).

**EXTERNALLY UNVERIFIABLE**: SP1 circuit soundness at the pinned
version; that `LightProver` and `CpuProver` verify equivalently is the
SDK's claim (both call the same `verify_proof`; read in source, not
proven here); filesystem integrity between verifications — which is
exactly why every hit re-verifies.

## Remaining bottleneck (measured, for whatever comes next)

With reuse (Stage 8), parallel manufacture (Stage 9) and reusable
verifier setup (Stage 10), the structural campaign's steady state is
~3.5 s of verification per rerun and its cost is again dominated by the
**irreducible first proof of each genuinely new statement** (SP1
~230–300 s, RISC Zero ~65 s, Nexus ~15–50 s, memory-bounded to ~2
concurrent provers on this machine class). Within verification itself
the ~0.5 s LightProver construction now dominates the 0.13 s
cryptographic check — three orders of magnitude below proving, and not
worth optimizing before proving costs move.
