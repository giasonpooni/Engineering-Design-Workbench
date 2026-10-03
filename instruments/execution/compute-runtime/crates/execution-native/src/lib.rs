//! Native execution: the reference backend a zkVM must reproduce.
//!
//! # What this crate represents
//!
//! [`execute`] runs a [`DeterministicProgram`] on input bytes and records
//! the run in an [`ExecutionTrace`] as a `BackendKind::Native` occurrence.
//! Its purpose is to expose, on the honest end of the spectrum, exactly
//! the semantics a future proving backend must reproduce:
//!
//! ```text
//! program bytes -> ProgramIdentity
//! input bytes   -> InputIdentity
//! run           -> ExecutionOccurrence (minted by the trace, this time)
//! completion    -> OutputIdentity + exit code -> ComputationIdentity
//! ```
//!
//! # What it deliberately cannot do
//!
//! It produces no proof, and the type system refuses to let it borrow
//! one: `ExecutionOccurrence::attach_proof` returns
//! `NativeExecutionHasNoProof` for every occurrence this crate creates.
//! There is no fake proof generation, no dev-mode receipt, no mock.
//! Phase 126 recorded that RISC Zero's `InnerReceipt::Fake` and SP1's
//! mock prover exist to make tests fast, not to attest to anything; this
//! crate does not reproduce that hazard.
//!
//! # The declared coupling -- what a zkVM would close
//!
//! Read this paragraph before trusting a native `ProgramIdentity`.
//! `DeterministicProgram` couples canonical program bytes with a Rust
//! function, and NOTHING VERIFIES THAT COUPLING: the identity commits to
//! the bytes, the behavior lives in the function, and the claim that the
//! bytes describe the function is a caller declaration -- exactly the
//! class of claim Phase 119 showed a declaration cannot witness. Two
//! programs with identical `canonical_bytes` but different behavior get
//! ONE `ProgramIdentity` and produce divergent computations under it
//! (`execution-core/tests/adversarial.rs` demonstrates this rather than
//! hiding it). Closing precisely this gap is what a zkVM backend is FOR:
//! there, the program commitment (e.g. an ImageID) is computed from the
//! artifact the virtual machine actually executed, so bytes and behavior
//! cannot part company.
//!
//! # COMPUTATION != MEASUREMENT
//!
//! A completed native execution establishes: "this process ran a
//! function declared as these program bytes over these input bytes and
//! committed these output bytes." It does NOT establish that the input
//! bytes were ever measured, observed, or true of the world. Phase 111b:
//! a world where an instrument produced `123.4` and a world where a
//! script produced `123.4` are identical byte strings, identical
//! identities, identical computations. No execution substrate -- native
//! or proving -- can tell them apart, and none of the types in this
//! workspace claims to.

#![forbid(unsafe_code)]
#![deny(missing_docs)]

pub mod reference;

use execution_model::{BackendKind, InputIdentity, OutputIdentity, ProgramIdentity};
use execution_trace::ExecutionTrace;

/// A deterministic computation this backend can run.
///
/// `canonical_bytes` names the program; `run` is the program. The
/// coupling between them is DECLARED by the implementor, not verified by
/// anything -- see the crate documentation, which states this as the
/// exact gap a zkVM backend exists to close.
///
/// Implementations must be deterministic: same input bytes, same result,
/// on every host. Integer arithmetic only is the practical rule -- the
/// reference workload avoids floating point entirely, because
/// cross-platform floating-point divergence would make "deterministic"
/// a hope rather than a property.
pub trait DeterministicProgram {
    /// The canonical bytes this program is identified by.
    fn canonical_bytes(&self) -> &[u8];

    /// Run the program over `input`.
    ///
    /// `Ok` is a completion -- an output was committed, with an exit
    /// code (nonzero completions are completions). `Err` is a fault --
    /// the program stopped WITHOUT committing an output. The distinction
    /// matters downstream: a fault yields no `OutputIdentity` and
    /// therefore no `ComputationIdentity`, because an absent output is
    /// not the empty output and is never fabricated.
    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault>;
}

/// A completed native run: committed output bytes plus exit code.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct NativeCompletion {
    /// The bytes the program committed as its output.
    pub output: Vec<u8>,
    /// The exit code it completed with. Nonzero is still a completion.
    pub exit_code: u32,
}

/// A faulted native run: the program stopped without committing output.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct NativeFault {
    /// The exit code the fault is reported under.
    pub exit_code: u32,
    /// Human-readable detail. NOT identity: two faults with different
    /// details are not thereby different kinds of fault, and nothing
    /// hashes this.
    pub detail: String,
}

/// One native execution as returned to the caller: which occurrence the
/// trace recorded it as, and what the program produced.
///
/// The output BYTES are returned here (the trace stores only their
/// identity) because a caller who just ran a computation legitimately
/// needs its result. Handing them back does not make them evidence.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct NativeExecution {
    /// The occurrence number the trace minted for this run --
    /// meaningful only within that trace.
    pub occurrence: u64,
    /// What the program produced.
    pub result: Result<NativeCompletion, NativeFault>,
}

/// Run `program` over `input`, recording the run in `trace`.
///
/// Every call mints a NEW occurrence -- running the identical program on
/// the identical input twice is two executions, one computation. A
/// completion resolves the occurrence to `Completed { output, exit_code }`;
/// a fault resolves it to `Halted { exit_code }`, which has no
/// computation identity because it has no output.
pub fn execute(
    trace: &mut ExecutionTrace,
    program: &dyn DeterministicProgram,
    input: &[u8],
) -> NativeExecution {
    let program_id = ProgramIdentity::of(program.canonical_bytes());
    let input_id = InputIdentity::of(input);
    let occurrence = trace.begin(program_id, input_id, BackendKind::Native);

    let result = program.run(input);
    let outcome = match &result {
        Ok(completion) => execution_model::ExecutionOutcome::Completed {
            output: OutputIdentity::of(&completion.output),
            exit_code: completion.exit_code,
        },
        Err(fault) => execution_model::ExecutionOutcome::Halted {
            exit_code: fault.exit_code,
        },
    };
    trace
        .resolve(occurrence, outcome)
        .expect("occurrence was minted three lines up and cannot be resolved yet");

    NativeExecution { occurrence, result }
}
