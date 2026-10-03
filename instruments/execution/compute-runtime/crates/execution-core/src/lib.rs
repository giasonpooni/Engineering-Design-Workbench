//! The execution substrate's public surface.
//!
//! A facade, and nothing else -- no logic lives here. It exists so that
//! Phase 128's backend adapters, and any later Python bridge, have ONE
//! name to depend on and cannot reach past it into an internal layer.
//!
//! ```text
//! execution-serialization   canonical encoding (deterministic, injective)
//!         v
//! execution-commitment      SHA-256 over canonical bytes -> Commitment
//!         v
//! execution-model           ProgramIdentity / InputIdentity / OutputIdentity
//!                           ProofIdentity / ExecutionOccurrence
//!         v
//! execution-trace           ExecutionTrace: mints occurrence numbers
//!         v
//! execution-native          native backend: DeterministicProgram,
//!                           execute(), the reference workload
//!         v
//! execution-verification    Expectation / VerificationCoverage
//!                           VerificationResult / ProofBackend
//! ```
//!
//! # What this substrate does not establish
//!
//! It is worth stating at the top of the facade rather than the bottom
//! of a document.
//!
//! - **No proof exists here.** No backend is implemented; nothing in this
//!   workspace has produced or checked a real proof. A `VerificationResult`
//!   constructed by a test fixture attests to nothing.
//! - **A proof would witness a COMPUTATION, never a MEASUREMENT.** Phase
//!   111b established that a world where a load frame produced 123.4 and
//!   a world where a script produced 123.4 are identical objects to a
//!   content-addressed system. A proof does not change that: a fabricated
//!   value can be computed faithfully.
//! - **Nothing here is evidence.** No type in this workspace may be
//!   admitted to `EvidencePool`, and no type here knows that
//!   `EvidencePool` exists.

#![forbid(unsafe_code)]
#![deny(missing_docs)]

pub use execution_commitment::{commit, sha256, Commitment};
pub use execution_model::{
    AttachProofError, BackendId, BackendKind, ComputationIdentity, ExecutionOccurrence,
    ExecutionOutcome, InputIdentity, OutputIdentity, ProgramIdentity, ProofArtifact, ProofIdentity,
    COMPUTATION_TAG, INPUT_COMMITMENT_INVARIANT, INPUT_TAG, OUTPUT_TAG, PROGRAM_TAG, PROOF_TAG,
    SPECIFICATION_TAG,
};
pub use execution_native::{
    execute, reference, DeterministicProgram, NativeCompletion, NativeExecution, NativeFault,
};
pub use execution_serialization::{canonical, canonical_u32};
pub use execution_trace::{ExecutionTrace, TraceError};
pub use execution_verification::{
    AdapterVerdict, Expectation, ProofBackend, RequiredCheck, VerificationCoverage,
    VerificationFailure, VerificationResult, VerifiedExecution,
};
