//! The execution ledger: where occurrence numbers come from.
//!
//! One trace mints a monotonic sequence. That sequence is the ONLY
//! source of an [`ExecutionOccurrence`]'s number, which is why
//! `ExecutionOccurrence::new` is never the right thing for application
//! code to call directly.
//!
//! This mirrors `operations/trace.py` (Phase 124) exactly, in a second
//! language, because the rule it encodes is not language-specific:
//!
//! > Identical arguments always produce a NEW occurrence.
//!
//! Not a UUID, not a timestamp, not a content hash. A UUID would be a
//! second identity system; a timestamp is not an identity at all (two
//! executions can share a clock reading); a content hash would collapse
//! the two runs this ledger exists to keep apart.
//!
//! **Scope limit.** Occurrence numbers are meaningful only within one
//! `ExecutionTrace`. Two traces both start at 0. Cross-process occurrence
//! identity is not solved here and is not attempted here.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

use alloc::vec::Vec;
use execution_model::{
    AttachProofError, BackendKind, ExecutionOccurrence, ExecutionOutcome, InputIdentity,
    ProgramIdentity, ProofArtifact,
};

/// Why a trace refused an operation.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum TraceError {
    /// No such occurrence in this trace.
    ///
    /// Very often this means an occurrence number from a DIFFERENT trace
    /// was used here, which the scope limit above makes meaningless.
    UnknownOccurrence(u64),
    /// The occurrence has already been resolved; a record is written once.
    AlreadyResolved(u64),
    /// The proof could not be attached.
    Proof(AttachProofError),
}

/// An append-only ledger of executions observed by this process.
#[derive(Clone, Debug, Default)]
pub struct ExecutionTrace {
    occurrences: Vec<ExecutionOccurrence>,
}

impl ExecutionTrace {
    /// A new, empty trace.
    pub const fn new() -> Self {
        Self {
            occurrences: Vec::new(),
        }
    }

    /// Record that an execution has begun. Returns its occurrence number.
    ///
    /// Calling this twice with identical arguments yields two different
    /// numbers, and that is the whole contract.
    pub fn begin(
        &mut self,
        program: ProgramIdentity,
        input: InputIdentity,
        backend: BackendKind,
    ) -> u64 {
        let occurrence = self.occurrences.len() as u64;
        self.occurrences.push(ExecutionOccurrence::new(
            occurrence, program, input, backend,
        ));
        occurrence
    }

    /// Record how an execution ended.
    pub fn resolve(
        &mut self,
        occurrence: u64,
        outcome: ExecutionOutcome,
    ) -> Result<(), TraceError> {
        let slot = self
            .occurrences
            .get_mut(occurrence as usize)
            .ok_or(TraceError::UnknownOccurrence(occurrence))?;
        if !matches!(slot.outcome(), ExecutionOutcome::Pending) {
            return Err(TraceError::AlreadyResolved(occurrence));
        }
        slot.resolve(outcome);
        Ok(())
    }

    /// Attach a proof to an execution.
    ///
    /// Refused for [`BackendKind::Native`]; see
    /// [`ExecutionOccurrence::attach_proof`].
    pub fn attach_proof(
        &mut self,
        occurrence: u64,
        artifact: &ProofArtifact,
    ) -> Result<(), TraceError> {
        let slot = self
            .occurrences
            .get_mut(occurrence as usize)
            .ok_or(TraceError::UnknownOccurrence(occurrence))?;
        slot.attach_proof(artifact).map_err(TraceError::Proof)
    }

    /// Every occurrence, in the order they began.
    pub fn occurrences(&self) -> &[ExecutionOccurrence] {
        &self.occurrences
    }

    /// One occurrence, by its number in THIS trace.
    pub fn get(&self, occurrence: u64) -> Option<&ExecutionOccurrence> {
        self.occurrences.get(occurrence as usize)
    }
}
