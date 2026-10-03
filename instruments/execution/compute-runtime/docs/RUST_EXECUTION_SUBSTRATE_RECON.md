# Phase 126 -- Rust Execution Substrate Reconnaissance

Reconnaissance only. **No production code was written or changed in this
phase.** The deliverable is a map of three zkVM substrates, read from
their source, and a determination of what a shared Rust execution layer
can and cannot abstract over them.

Read at these exact revisions:

| substrate | local path | HEAD | declared version |
|---|---|---|---|
| RISC Zero | `notationsystems/risc0-zero` | `3bbcd44` | `risc0-zkvm` 5.0.0 |
| SP1 | `notationsystems/SP1-zero-knowledge-virtual-machine` | `b38b612` | circuit `v6.1.0` |
| Nexus | `notationsystems/nexus-zkvm` | `f2ad126` | workspace 0.3.6 |

Nexus was not among the forks named at the start of the phase; it was
cloned during reconnaissance because the target architecture names it as
a backend. All three were read as source. Only RISC Zero was built
(`cargo build -p risc0-zkvm --release`, exit 0, 1m30s) to confirm the
toolchain works; **no proof was generated, and nothing below rests on a
proof this repository has produced.**

---

## 1-2. Architecture of the two (three) forks

### RISC Zero -- `risc0/`
```
risc0/binfmt      ELF decoding, MemoryImage, ImageID, ExitCode
risc0/zkvm/src/guest    the RISC-V side: env::read / env::commit
risc0/zkvm/src/host     the native side: ExecutorEnv, executor, prover, Receipt
risc0/zkvm/src/claim    ReceiptClaim, SystemState, Output, MaybePruned
risc0/zkvm/src/receipt  Receipt, Journal, InnerReceipt {composite,succinct,groth16}
risc0/zkvm/src/serde    word-oriented (u32) serializer/deserializer
risc0/zkp, risc0/circuit  the proof system itself
```
The organising type is `ReceiptClaim` -- a structured statement about a
whole execution (`pre`, `post`, `exit_code`, `input`, `output`), hashed
by a domain-tagged tree hash. Everything else exists to produce or check
that claim's digest.

### SP1 -- `crates/`
```
crates/zkvm/entrypoint  guest runtime + syscalls
crates/zkvm/lib         guest API: sp1_zkvm::io::read / commit
crates/core             executor, machine, SP1Stdin
crates/primitives       SP1PublicValues, Buffer
crates/hypercube        MachineVerifyingKey, SP1VerifyingKey, HashableKey
crates/prover           proving pipeline (core -> compressed -> groth16/plonk)
crates/sdk              ProverClient, SP1ProofWithPublicValues, verify
crates/verifier         standalone Groth16/Plonk/compressed verifiers
```
The organising type is a *pair*: `(SP1VerifyingKey, SP1PublicValues)`.
There is no single struct describing an execution; the program is named
by the verifying key and the result by the public-values buffer.

### Nexus -- workspace root
```
runtime/       guest runtime: nexus_rt::{read_public_input, read_private_input, write_public_output}
vm/, core/     the NVM emulator, ElfFile, View, LinearMemoryLayout
prover/, prover2/   the Stwo-based prover
sdk/           Prover / Verifiable / Viewable / CheckedView traits, Stwo impl
```
The organising type is `View` (`nexus_core::nvm::View`) -- a
reconstructible picture of the whole execution: program memory, public
input memory, exit code, public output, associated data.

**The three substrates do not share an organising abstraction.** RISC
Zero centres a *claim digest*, SP1 centres a *key/values pair*, Nexus
centres a *reconstructible execution view*. This is the root fact that
constrains everything in §9-10.

---

## 3. Guest / host boundary

| | guest reads input | guest publishes output |
|---|---|---|
| RISC Zero | `env::read::<T>()` -- `risc0/zkvm/src/guest/env/mod.rs:209` | `env::commit(&T)` -> journal -- `:331` |
| SP1 | `sp1_zkvm::io::read::<T>()` -- `crates/zkvm/lib/src/io.rs:88` | `sp1_zkvm::io::commit(&T)` -> fd `FD_PUBLIC_VALUES` -- `:126` |
| Nexus | `nexus_rt::read_public_input::<T>()` / `read_private_input::<T>()` -- `runtime/src/io.rs:58,41` | `nexus_rt::write_public_output(&T)` -- `:78` |

All three are the same *shape*: a stream in, a committed stream out,
crossed by syscall. Nexus is the only one that distinguishes public
from private input at the runtime API level; on RISC Zero and SP1 all
host-supplied input is private unless the guest chooses to commit it.

SP1 additionally notes, in the guest itself, that the input stream is
untrusted: "bincode bytes are also prover-controlled -- a corrupt
encoding is an..." (`crates/zkvm/lib/src/io.rs:100`). The guest cannot
assume its own input is well-formed.

---

## 4. Serialization formats

| | host->guest and guest->host encoding |
|---|---|
| RISC Zero | its own **word-oriented** serde over `u32` words -- `risc0/zkvm/src/serde/{serializer,deserializer}.rs`, `WordRead`/`WordWrite` |
| SP1 | **bincode** (`bincode::serialize_into` on commit, `bincode::deserialize` on read) -- `crates/zkvm/lib/src/io.rs:102,128`; `SP1Stdin::read` also bincode -- `crates/core/machine/src/io.rs:33` |
| Nexus | **postcard + COBS**, then zero-padded to a 4-byte boundary -- `sdk/src/traits.rs:276-287`, `runtime/src/io.rs:43,74,80` |

These are three mutually incompatible byte encodings of the same values.
`to_vec(&42u32)` produces different bytes in each. **There is no shared
wire format and there is no prospect of one.**

---

## 5. Program commitment

| | what names the program | pure function of the ELF? |
|---|---|---|
| RISC Zero | **ImageID**, a 32-byte `Digest`: `tagged_struct("risc0.SystemState", [merkle_root], [pc=0])` over the initial memory image -- `risc0/binfmt/src/elf.rs:435-438`, `risc0/binfmt/src/sys_state.rs:73` | **yes** -- `compute_image_id(blob)` -- `risc0/binfmt/src/lib.rs:50` |
| SP1 | **verifying key hash**: `SP1VerifyingKey` -> `hash_koalabear` / `hash_bn254` / `bytes32()` -- `crates/hypercube/src/verifier/hashable_key.rs:14-71` | **derivable from the ELF, but not cheaply and not context-free**: requires `prover.setup(elf)` -- `crates/cli/src/commands/vkey.rs:44-56` -- and is bound to the circuit version |
| Nexus | **nothing**. There is no program digest. The verifier is handed `expected_elf: &nexus_core::nvm::ElfFile` and rebuilds program memory from it -- `sdk/src/traits.rs:459,484-491` | n/a -- the ELF *is* the commitment |

**Consequence.** A shared `ProgramIdentity` cannot be "the backend's
program commitment", because one backend has no such value, one produces
it by pure hash, and one produces it through an expensive
version-dependent setup.

---

## 6. Input and output commitment -- the decisive finding

### Output
All three bind the output.

- RISC Zero: the journal digest is inside `Output`, inside `ReceiptClaim`,
  and `Receipt::verify` reconstructs the expected claim from the caller's
  `image_id` and the receipt's own `journal.digest()` -- `risc0/zkvm/src/receipt.rs:180-190`.
- SP1: `verify_proof` checks the proof's committed value digest against
  `bundle.public_values.hash()` (or `blake3_hash()`) -- `crates/sdk/src/prover.rs:176-190`.
- Nexus: the expected public output is written into the reconstructed
  `View` and checked by `verify` -- `sdk/src/traits.rs:473-493`.

### Input
**They do not agree, and two of the three do not bind the input at all.**

**SP1: no input commitment exists.** `SP1Stdin` is
`{ buffer: Vec<Vec<u8>>, ptr, proofs }` -- `crates/core/machine/src/io.rs:8-17`.
It is never hashed, and `verify_proof` (`crates/sdk/src/prover.rs:143-215`)
never receives it. What is checked is: version, exit code, and
public-values digest. Nothing else.

**RISC Zero: the input field exists but is structurally inert.**
`ReceiptClaim.input: MaybePruned<Option<Input>>` --
`risc0/zkvm/src/claim/receipt.rs:67`. And:

> "NOTE: This type is currently uninhabited (i.e. it cannot be
> constructed), and only its digest is accessible. It may become
> inhabited in a future release."
> -- `risc0/zkvm/src/claim/receipt.rs:406-417`

The only way a value ever reaches that field is
`ExecutorEnvBuilder::input_digest(digest)` -- a value the **host
declares**, with no computed relationship to `env.input` --
`risc0/zkvm/src/host/client/env.rs:108,428-432`, consumed at
`risc0/zkvm/src/host/server/exec/executor.rs:442` as
`self.env.input_digest.unwrap_or_default()`.

Worse for our purposes: the standard verification path *requires that
declared digest to be zero*. `Receipt::verify_with_context` builds
`ReceiptClaim::ok(image_id, journal_digest)`, which sets `input:
None.into()` (`:87`), and a `MaybePruned<Option<T>>` is `None` exactly
when its digest is `Digest::ZERO`
(`risc0/zkvm/src/claim/maybe_pruned.rs:117-124`). So a receipt carrying
a *real* input digest fails `Receipt::verify` outright; checking it
requires dropping to `verify_integrity` and inspecting the claim by hand.

**Nexus: the input is genuinely bound.**
`Verifiable::verify_expected(expected_public_input, expected_exit_code,
expected_public_output, expected_elf, expected_ad)` --
`sdk/src/traits.rs:451-494` -- encodes the expected input, writes it
into the reconstructed input memory
(`CheckedView::new_from_expected`, `:59-66`), and verifies the proof
against that whole view. Nexus also carries an arbitrary
`associated_data` blob bound into the proof
(`sdk/src/traits.rs:250`, `sdk/src/stwo/seq.rs:94-97`).

### What this means
> A zkVM proof, by default, on two of these three backends, says:
> *"some program with this program-commitment produced this output."*
> It does **not** say *"...from this input."*

Binding the input is therefore **not a property of the substrate**. It
is a property of a *guest program convention*: the guest reads its
input, hashes it, and commits that hash as part of its own output. That
convention works identically on all three backends and is the only
construction that does.

This is Phase 119's declared-vs-witnessed distinction reappearing one
layer down, in cryptography rather than in a string field. RISC Zero's
`input_digest` is a *declaration* by the host in exactly the sense
`extraction_method` was a declaration by the dispatcher.

---

## 7. Proof objects

| | type | contents | serialization |
|---|---|---|---|
| RISC Zero | `Receipt` -- `risc0/zkvm/src/receipt.rs:116-130` | `inner: InnerReceipt` (Composite / Succinct / Groth16 / Fake), `journal: Journal`, `metadata: ReceiptMetadata` | serde + borsh |
| SP1 | `SP1ProofWithPublicValues` -- `crates/sdk/src/proof.rs:52-64` | `proof: SP1Proof` (Core / Compressed / Plonk / Groth16), `public_values`, `sp1_version: String`, `tee_proof: Option<Vec<u8>>` | bincode (`save`/`load`, `:87-100`) |
| Nexus | `stwo::Proof` -- `sdk/src/stwo/seq.rs:59-64` | `proof: nexus_core::stwo::Proof`, `memory_layout: LinearMemoryLayout` | serde |

Two of the three carry the output *inside* the proof object (RISC Zero's
journal, SP1's public values). Nexus does not -- its output lives in the
`View`, which the verifier reconstructs.

RISC Zero's `ReceiptMetadata` carries an explicit warning worth
recording verbatim, because it is precisely the kind of field a naive
adapter would trust:

> "It is not cryptographically bound to the receipt, and should not be
> used for security-relevant decisions, such as choosing whether or not
> to accept a receipt based on its stated version."
> -- `risc0/zkvm/src/receipt.rs:125-129`

---

## 8. Verifier APIs

```rust
// RISC Zero -- risc0/zkvm/src/receipt.rs:152,163
receipt.verify(image_id: impl Into<Digest>) -> Result<(), VerificationError>
receipt.verify_with_context(ctx: &VerifierContext, image_id) -> Result<(), VerificationError>

// SP1 -- crates/sdk/src/prover.rs:72
prover.verify(&SP1ProofWithPublicValues, &SP1VerifyingKey, Option<StatusCode>)
    -> Result<(), SP1VerificationError>
// standalone -- crates/verifier/src/groth16/mod.rs:47
Groth16Verifier::verify(proof: &[u8], sp1_public_inputs: &[u8],
                        sp1_vkey_hash: &str, groth16_vk: &[u8]) -> Result<(), Groth16Error>

// Nexus -- sdk/src/traits.rs:448,451
proof.verify(expected_view: &View) -> Result<(), Error>
proof.verify_expected(expected_public_input, expected_exit_code,
                      expected_public_output, expected_elf, expected_ad) -> Result<(), Error>
```

The three signatures **differ in kind, not in naming**. Nexus's verifier
demands the expected input and the whole program; the other two accept
no input argument at all and would have nowhere to put one.

Version binding is not uniform either:
- SP1 **hard-fails** on version mismatch -- `crates/sdk/src/prover.rs:154-156`.
- RISC Zero binds `verifier_parameters` inside `InnerReceipt` and checks
  internal consistency -- `risc0/zkvm/src/receipt.rs:169-173`.
- Nexus embeds the `memory_layout` in the proof -- `sdk/src/stwo/seq.rs:62`.

**A proof is not verifiable forever.** It is verifiable by a verifier of
a compatible version. Any long-lived record of a proof must therefore
record the version it was produced under, and must not present an
unverifiable historical proof as a verified one.

---

## 9. What CAN be shared

Everything on this list is shareable **because we compute it ourselves**,
over bytes we canonicalise, rather than reading it out of a backend.

1. **`ProgramIdentity`** -- our digest over the program artifact bytes.
   The backend's own commitment (ImageID / vkey hash / nothing) is
   recorded *beside* it as an opaque, backend-tagged value, never as the
   identity.
2. **`InputIdentity`** -- our digest over our canonical encoding of the
   input. Never a backend's input digest, because two backends have none.
3. **`ExecutionOccurrence`** -- that a specific run happened. Already
   settled by Phase 122-124: an occurrence is *not* content-addressed,
   because two identical runs must remain two. Same rule in Rust.
4. **`ProofIdentity`** -- our digest over the serialized proof bytes.
5. **A canonical byte encoding of our own**, used to produce 1, 2 and 4.
   Each backend then carries those bytes opaquely through *its own*
   incompatible encoding.
6. **An execution-outcome vocabulary.** All three expose a reducible
   notion: RISC Zero `ExitCode::{Halted(u32), Paused(u32), SystemSplit,
   SessionLimit}` (`risc0/binfmt/src/exit_code.rs:33-61`); SP1's
   `exit_code` / `StatusCode`; Nexus's `exit_code: u32`.
7. **The lifecycle state machine** already proven in `operations/trace.py`
   -- invoked / started / succeeded / failed / rejected. Nothing about it
   is Python-specific or zkVM-specific.
8. **Native (unproven) execution as a first-class backend.** All three
   substrates run the same guest program shape; running it natively with
   no proof at all is a legitimate backend that yields identities 1-3
   and no `ProofIdentity`. This is what stops the architecture from
   being "Rust -> SP1".

---

## 10. What CANNOT be abstracted

1. **Serialization** (§4). Three incompatible encodings. A shared
   `execution-serialization` crate may define *our* canonical encoding;
   it must not pretend to define *theirs*.
2. **Program commitment** (§5). One pure hash, one expensive
   version-bound setup, one absent. `ProgramIdentity` must be ours.
3. **Input commitment** (§6). Absent in SP1, inert-and-host-declared in
   RISC Zero, real in Nexus. Cannot be lifted into a shared trait as
   though it were uniform.
4. **Proof object shape** (§7). No common structure; opaque bytes plus a
   backend tag plus a backend version is the most that is true.
5. **Verifier argument lists** (§8). Nexus needs the expected input and
   the ELF; the others cannot accept them.
6. **Perpetual verifiability** (§8). Version-bound in all three.

### The one design consequence that matters

A shared trait of the obvious shape --

```rust
fn verify(&self, proof: &Proof, expectation: &Expectation) -> Result<(), Error>
```

-- would be **an abstraction that fabricates a warrant.** Given the same
`Expectation` carrying program, input and output, an SP1 backend would
return `Ok(())` having checked program and output only; a Nexus backend
would return the identical `Ok(())` having also checked the input. The
caller cannot tell the two apart, and would be entitled to believe the
stronger claim in both cases. That is exactly the Phase 111 failure mode
-- an unwarranted claim entering through a gate that looks like it
checked -- reintroduced by the abstraction itself.

**Therefore the shared verification trait must return what was actually
checked, not a boolean.** Something of the form:

```rust
struct VerificationCoverage {
    program_checked: bool,   // ImageID / vkey hash / expected_elf
    input_checked:   bool,   // false on SP1 and RISC Zero unless the
                             // guest committed its own input digest
    output_checked:  bool,
    exit_code_checked: bool,
}
```

with the substrate refusing to collapse it to pass/fail. A caller that
wants "the input was bound" must then either read `input_checked` or
adopt the guest convention of §6 -- and either way it can never be
silently misled.

**Corollary, and the reason this belongs in a Rust layer at all:** if
the guest convention of §6 is adopted (guest hashes its own input and
commits the hash), then `input_checked` becomes true on *all three*
backends, uniformly, without the substrate lying about anything. The
convention has to live in the guest program -- which is Rust -- and it
cannot live in Python.

---

## What this phase did not establish

- **No proof was generated.** No `VerifiedExecution` in this repository
  is backed by a real receipt, and none may be presented as such. A
  dev-mode or mock receipt is not a proof: RISC Zero ships
  `InnerReceipt::Fake` and SP1 ships a mock prover, and both exist to
  make tests fast, not to attest to anything.
- **No claim that a proof witnesses a physical measurement.** Phase 111b
  stands unchanged: World A (a load frame produced 123.4) and World B (a
  script produced 123.4) remain identical objects. A proof witnesses that
  a *computation* ran as specified. A fabricated value can be computed
  faithfully.
- **No production change.** `materials/`, `experiment/`, `evidence/`,
  `retrieval/`, `core/` and `operations/` are untouched by this phase.
