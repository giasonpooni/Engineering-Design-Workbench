//! The four identities, the outcome vocabulary, and the occurrence.
//!
//! # Why there are four identities and not one
//!
//! Phase 126 found that the three zkVM substrates disagree about what an
//! execution even is: RISC Zero centres a claim digest, SP1 centres a
//! `(verifying key, public values)` pair, Nexus centres a reconstructible
//! `View`. Collapsing those into a single "execution id" would force one
//! backend's model onto the others.
//!
//! Four separate identities, each committing to exactly one thing, is
//! what all three can attach to:
//!
//! ```text
//! ProgramIdentity   what was to be run
//! InputIdentity     what it was to be run on
//! OutputIdentity    what came out
//! ProofIdentity     the artifact asserting the run happened
//! ```
//!
//! And one thing that is deliberately NOT an identity in that sense:
//!
//! ```text
//! ExecutionOccurrence   that a run happened, this time
//! ```
//!
//! # Backend-native commitments are not canonical identities
//!
//! A `ProgramIdentity` is *our* commitment to the program bytes. It is
//! NOT a RISC Zero ImageID, NOT an SP1 verifying-key hash, and NOT a
//! Nexus ELF. Phase 126 §5 is the reason:
//!
//! | substrate | program commitment | pure function of the ELF? |
//! |---|---|---|
//! | RISC Zero | 32-byte ImageID | yes |
//! | SP1 | verifying-key hash | derivable, but only via an expensive, circuit-version-bound `setup()` |
//! | Nexus | *none at all* -- the verifier is handed the whole ELF | n/a |
//!
//! One backend has no program digest whatsoever. A canonical identity
//! defined as "the backend's program commitment" would therefore be
//! undefined for Nexus and version-dependent for SP1. A backend's native
//! commitment belongs BESIDE our identity, as an opaque backend-tagged
//! value, never as the identity itself.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

use alloc::string::String;
use alloc::vec::Vec;
use execution_commitment::{commit, Commitment};
use execution_serialization::canonical_u32;

/// Domain tag for [`ProgramIdentity`].
pub const PROGRAM_TAG: &str = "scout.execution.program.v1";
/// Domain tag for [`InputIdentity`].
pub const INPUT_TAG: &str = "scout.execution.input.v1";
/// Domain tag for [`OutputIdentity`].
pub const OUTPUT_TAG: &str = "scout.execution.output.v1";
/// Domain tag for [`ProofIdentity`].
pub const PROOF_TAG: &str = "scout.execution.proof.v1";
/// Domain tag for the content-addressed computation digest.
pub const COMPUTATION_TAG: &str = "scout.execution.computation.v1";
/// Domain tag for a specification digest: (program bytes, configuration
/// bytes, input bytes) -- the request to execute, before any run.
///
/// The Phase 128 review REJECTED a specification identity for lack of a
/// consumer. The consumer then arrived (recorded here so the reversal is
/// explicit, not silent): the cross-process execution boundary. When
/// Python asks the execution engine, in another process, to run a
/// specification, the result must name which request it answers -- the
/// same detachable-warrant hazard probe 1 found in verification results,
/// one seam over. The digest exists for that echo; a specification TYPE
/// still has no consumer and still does not exist.
pub const SPECIFICATION_TAG: &str = "scout.execution.specification.v1";

macro_rules! identity {
    ($name:ident, $tag:ident, $doc:expr) => {
        #[doc = $doc]
        #[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
        pub struct $name(Commitment);

        impl $name {
            /// Commit to `bytes` under this identity's domain tag.
            pub fn of(bytes: &[u8]) -> Self {
                Self(commit($tag, &[bytes]))
            }

            /// The underlying commitment.
            pub const fn commitment(&self) -> &Commitment {
                &self.0
            }

            /// Lowercase hex, the form this repository stores identities in.
            pub fn to_hex(&self) -> String {
                self.0.to_hex()
            }
        }
    };
}

identity!(
    ProgramIdentity,
    PROGRAM_TAG,
    "Our commitment to the program bytes.\n\nDistinct from every backend's own program commitment; see the module documentation for why that distinction is load-bearing rather than pedantic."
);
identity!(
    InputIdentity,
    INPUT_TAG,
    "Our commitment to the canonical input bytes.\n\n**This is not a backend-native input commitment, and the difference is the single most important finding of Phase 126.** SP1 never hashes its `SP1Stdin` at all; RISC Zero's `ReceiptClaim.input` can only hold a HOST-DECLARED `input_digest` (its `Input` type is uninhabited), and the standard `Receipt::verify` path requires that digest to be zero. Only Nexus binds the input, by reconstructing the whole execution `View`.\n\nSo an `InputIdentity` matching a value the host asserts proves nothing about what the program actually read. See [`crate::INPUT_COMMITMENT_INVARIANT`]."
);
identity!(
    OutputIdentity,
    OUTPUT_TAG,
    "Our commitment to the canonical output bytes.\n\nAll three substrates surveyed in Phase 126 do bind the output -- RISC Zero via the journal digest inside `ReceiptClaim`, SP1 via the committed-value digest checked against `public_values.hash()`, Nexus via the reconstructed `View`. Output is the one field on which they agree."
);

/// The rule a future backend must satisfy before it may report
/// `input_checked = true`.
///
/// Stated now, deliberately not implemented now. The guest mechanism it
/// describes is Phase 128 work or later.
///
/// ```text
/// A backend may set input_checked = true if and only if the PROVED
/// EXECUTION ITSELF cryptographically binds the canonical InputIdentity.
///
/// A host-side assertion is insufficient.
/// An externally supplied digest is insufficient.
/// A digest the host passed to the prover is insufficient.
/// ```
///
/// The last line is not hypothetical. RISC Zero's
/// `ExecutorEnvBuilder::input_digest(digest)` is exactly such a digest:
/// the host declares it, nothing computes it from `env.input`, and the
/// executor stores `self.env.input_digest.unwrap_or_default()`. It is a
/// declaration in precisely the sense Phase 119 found `extraction_method`
/// to be a declaration -- and Phase 119 proved a declaration is not a
/// witness.
///
/// The only construction that works identically on all three substrates
/// is a guest-side convention: the guest reads its input, hashes it, and
/// commits that hash as part of its own committed output. Then the
/// binding is inside the proved execution, where it has to be. That
/// convention must live in the guest program, which is why it cannot
/// live in Python.
pub const INPUT_COMMITMENT_INVARIANT: &str =
    "input_checked = true requires the proved execution to bind the canonical InputIdentity; \
     a host-side assertion or externally supplied digest is insufficient";

/// Which substrate ran an execution.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum BackendKind {
    /// Ran natively, with no proof system involved.
    ///
    /// A legitimate backend: it establishes that a program was run on an
    /// input and what came out, on the authority of this process. It
    /// establishes nothing cryptographic, and
    /// [`ExecutionOccurrence::attach_proof`] refuses to let it pretend
    /// otherwise.
    Native,
    /// Ran under a proving backend, named and versioned.
    Proving(BackendId),
}

/// A proving backend's name and version.
///
/// Version is not decoration. Phase 126 §8: SP1's verifier hard-fails on
/// version mismatch, RISC Zero binds `verifier_parameters` into the
/// receipt, Nexus embeds the memory layout in the proof. A proof is not
/// verifiable forever -- it is verifiable by a compatible verifier -- so
/// a record that omits the version records something unverifiable.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct BackendId {
    /// Backend name, e.g. `"sp1"`.
    pub name: String,
    /// Backend version, as the backend reports it.
    pub version: String,
}

impl BackendId {
    /// Construct a backend identifier.
    pub fn new(name: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: version.into(),
        }
    }
}

/// How an execution ended.
///
/// Reduced from the three substrates' own vocabularies (RISC Zero's
/// `ExitCode::{Halted, Paused, SystemSplit, SessionLimit}`, SP1's
/// `exit_code` / `StatusCode`, Nexus's `exit_code: u32`) to the three
/// distinctions all of them can express.
///
/// [`ExecutionOutcome::Indeterminate`] exists because RISC Zero says so
/// in its own source: of a system split, "no conclusions can be drawn
/// about whether the program will eventually halt." An unknown outcome
/// stays unknown; it is never reported as a zero exit code to make a
/// caller's life easier.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum ExecutionOutcome {
    /// Started, not yet resolved.
    Pending,
    /// Ended with a committed output.
    Completed {
        /// What the execution committed.
        output: OutputIdentity,
        /// The exit code it ended with. Non-zero is still `Completed`;
        /// the code carries the failure, and discarding it would lose
        /// information the backends all supply.
        exit_code: u32,
    },
    /// Ended without a committed output.
    Halted {
        /// The exit code it ended with.
        exit_code: u32,
    },
    /// Ended in a state from which no conclusion follows.
    Indeterminate,
}

/// A commitment to a proof artifact.
///
/// The proof's bytes are opaque here and stay opaque. Phase 126 §7 found
/// no shared proof shape whatsoever -- RISC Zero's `Receipt`, SP1's
/// `SP1ProofWithPublicValues` and Nexus's `stwo::Proof` have nothing
/// structural in common, and two of the three carry the output inside
/// the proof while the third does not. Opaque bytes plus a backend tag
/// plus a backend version is the most that is true of all of them.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct ProofArtifact {
    backend: BackendId,
    bytes: Vec<u8>,
}

impl ProofArtifact {
    /// Wrap raw proof bytes produced by `backend`.
    pub fn new(backend: BackendId, bytes: Vec<u8>) -> Self {
        Self { backend, bytes }
    }

    /// Which backend produced this, and at what version.
    pub const fn backend(&self) -> &BackendId {
        &self.backend
    }

    /// The opaque proof bytes.
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// This artifact's identity.
    ///
    /// Commits to the backend name and version as well as the bytes, so
    /// the same bytes under two backend versions are two proofs. That is
    /// the version-binding of Phase 126 §8 made structural rather than
    /// remembered.
    pub fn identity(&self) -> ProofIdentity {
        ProofIdentity(commit(
            PROOF_TAG,
            &[
                self.backend.name.as_bytes(),
                self.backend.version.as_bytes(),
                &self.bytes,
            ],
        ))
    }
}

/// A commitment to a proof artifact, its backend, and its backend version.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct ProofIdentity(Commitment);

impl ProofIdentity {
    /// The underlying commitment.
    pub const fn commitment(&self) -> &Commitment {
        &self.0
    }

    /// Lowercase hex.
    pub fn to_hex(&self) -> String {
        self.0.to_hex()
    }
}

/// The content-addressed identity of WHAT WAS COMPUTED: program, input,
/// output and exit code, committed under [`COMPUTATION_TAG`].
///
/// Two occurrences of the same computation share this value while
/// remaining two distinct occurrences -- Phase 122's two-ledger rule
/// made structural. It is a newtype over [`Commitment`] (added in Phase
/// 129, at the Phase 128 review's direction) so a computation digest
/// cannot be passed where a proof or evidence digest is expected: the
/// domain tag already separates the DIGESTS, and the newtype separates
/// the TYPES.
///
/// What it does NOT establish: that the computation models anything,
/// that its input was measured, or that it happened more than zero
/// times -- occurrence counting is the trace's job, never this value's.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct ComputationIdentity(Commitment);

impl ComputationIdentity {
    /// The underlying commitment.
    pub const fn commitment(&self) -> &Commitment {
        &self.0
    }

    /// Lowercase hex.
    pub fn to_hex(&self) -> String {
        self.0.to_hex()
    }
}

/// Refusal reasons for [`ExecutionOccurrence::attach_proof`].
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum AttachProofError {
    /// A native execution produced no proof and cannot borrow one.
    NativeExecutionHasNoProof,
    /// The proof came from a different backend than the one that ran.
    BackendMismatch {
        /// The backend that ran the execution.
        executed_by: BackendId,
        /// The backend named on the proof.
        proof_from: BackendId,
    },
    /// A proof is already attached; an occurrence's record is written once.
    AlreadyAttached,
}

/// That a specific execution happened, this time.
///
/// # Why this is not content-addressed
///
/// Phase 122 established that this system holds two ledgers with
/// contradictory identity rules. In the EVIDENCE ledger, two identical
/// occasions must COLLAPSE to one object -- that is what content
/// addressing is for. In the OPERATION ledger, two identical occasions
/// must REMAIN TWO -- running the same program on the same input twice is
/// two runs, and a ledger that merges them has lost the fact that it
/// happened twice. No single object satisfies both rules.
///
/// So:
///
/// ```text
/// same program + same input + same output = same COMPUTATION
///                                           (computation_identity())
///
/// execution #1                            != execution #2
///                                           (the occurrence itself)
/// ```
///
/// [`ExecutionOccurrence::computation_identity`] gives the first. The
/// occurrence's own `occurrence` number gives the second, and it is a
/// process-local monotonic sequence minted by one `ExecutionTrace` --
/// exactly the discipline `operations/trace.py` already established for
/// the Python operation ledger in Phase 124.
///
/// # Scope limit, stated rather than hidden
///
/// **An occurrence number is meaningful only within one trace.** Two
/// traces both mint an occurrence 0, and comparing occurrences across
/// traces is not defined by this type. Cross-process occurrence identity
/// is deliberately unsolved here. Inventing a UUID or a timestamp to
/// paper over it would create a second identity system and a
/// clock-dependent one at that; both are excluded.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct ExecutionOccurrence {
    occurrence: u64,
    program: ProgramIdentity,
    input: InputIdentity,
    outcome: ExecutionOutcome,
    backend: BackendKind,
    proof: Option<ProofIdentity>,
}

impl ExecutionOccurrence {
    /// Construct an occurrence. Called by `ExecutionTrace`, which owns
    /// the sequence; there is no other legitimate source of `occurrence`.
    pub fn new(
        occurrence: u64,
        program: ProgramIdentity,
        input: InputIdentity,
        backend: BackendKind,
    ) -> Self {
        Self {
            occurrence,
            program,
            input,
            outcome: ExecutionOutcome::Pending,
            backend,
            proof: None,
        }
    }

    /// This occurrence's process-local sequence number.
    pub const fn occurrence(&self) -> u64 {
        self.occurrence
    }

    /// The program that ran.
    pub const fn program(&self) -> &ProgramIdentity {
        &self.program
    }

    /// The input it ran on.
    pub const fn input(&self) -> &InputIdentity {
        &self.input
    }

    /// How it ended.
    pub const fn outcome(&self) -> &ExecutionOutcome {
        &self.outcome
    }

    /// Which substrate ran it.
    pub const fn backend(&self) -> &BackendKind {
        &self.backend
    }

    /// The attached proof, if any.
    ///
    /// `None` for every native execution, always.
    pub const fn proof(&self) -> Option<&ProofIdentity> {
        self.proof.as_ref()
    }

    /// Record how the execution ended.
    pub fn resolve(&mut self, outcome: ExecutionOutcome) {
        self.outcome = outcome;
    }

    /// Attach a proof produced for this execution.
    ///
    /// Refuses for [`BackendKind::Native`]. Native execution is a real
    /// backend and produces a real occurrence, but it produces no
    /// cryptographic artifact, and the type system is where that stays
    /// true rather than in a comment someone later disregards.
    pub fn attach_proof(&mut self, artifact: &ProofArtifact) -> Result<(), AttachProofError> {
        match &self.backend {
            BackendKind::Native => Err(AttachProofError::NativeExecutionHasNoProof),
            BackendKind::Proving(executed_by) => {
                if executed_by != artifact.backend() {
                    return Err(AttachProofError::BackendMismatch {
                        executed_by: executed_by.clone(),
                        proof_from: artifact.backend().clone(),
                    });
                }
                if self.proof.is_some() {
                    return Err(AttachProofError::AlreadyAttached);
                }
                self.proof = Some(artifact.identity());
                Ok(())
            }
        }
    }

    /// The content-addressed digest of *what was computed*: program,
    /// input, output and exit code.
    ///
    /// Two occurrences of the same computation share this value while
    /// remaining two distinct occurrences. That is the whole point.
    ///
    /// `None` while the outcome is [`ExecutionOutcome::Pending`] or
    /// [`ExecutionOutcome::Indeterminate`], and for
    /// [`ExecutionOutcome::Halted`], because in each of those cases the
    /// output is not known. An unknown output is not the empty output,
    /// and it is not a zero. Returning `Some` of some placeholder here
    /// would be the exact substitution this architecture forbids.
    pub fn computation_identity(&self) -> Option<ComputationIdentity> {
        match &self.outcome {
            ExecutionOutcome::Completed { output, exit_code } => Some(ComputationIdentity(commit(
                COMPUTATION_TAG,
                &[
                    self.program.commitment().as_bytes(),
                    self.input.commitment().as_bytes(),
                    output.commitment().as_bytes(),
                    &canonical_u32(*exit_code),
                ],
            ))),
            _ => None,
        }
    }
}
