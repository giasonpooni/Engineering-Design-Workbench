//! Phase 129 adversarial semantic tests.
//!
//! Cases A-L from the phase specification, the two Phase 128 probes
//! inverted (each probe demonstrated a hole; here the same construction
//! must hit the repair), the end-to-end integration walk, and the two
//! honest negative results -- COMPUTATION != MEASUREMENT and
//! bytes-not-behavior -- encoded as tests rather than left as prose.

use execution_core::reference::{encode_positions, PairwiseEnergyKernel};
use execution_core::*;

// ---------------------------------------------------------------------
// Test-local programs. Fixtures, not shipped workloads.
// ---------------------------------------------------------------------

/// Deterministic xorshift64* stream: input = 8-byte LE seed; output =
/// 32 bytes of stream. "Stochastic with explicit seed" means exactly
/// this -- the randomness is in the seed, so it is in the INPUT, so it
/// is in the identity (case L).
struct SeededStream;
impl DeterministicProgram for SeededStream {
    fn canonical_bytes(&self) -> &[u8] {
        b"test.seeded-xorshift64star.v1: input=8B LE seed(nonzero), output=4 rounds of 8B LE"
    }
    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        let Ok(seed_bytes) = <[u8; 8]>::try_from(input) else {
            return Err(NativeFault {
                exit_code: 2,
                detail: "seed must be 8 bytes".into(),
            });
        };
        let mut state = u64::from_le_bytes(seed_bytes);
        if state == 0 {
            return Err(NativeFault {
                exit_code: 3,
                detail: "seed must be nonzero".into(),
            });
        }
        let mut output = Vec::with_capacity(32);
        for _ in 0..4 {
            state ^= state >> 12;
            state ^= state << 25;
            state ^= state >> 27;
            output.extend_from_slice(&state.wrapping_mul(0x2545F4914F6CDD1D).to_le_bytes());
        }
        Ok(NativeCompletion {
            output,
            exit_code: 0,
        })
    }
}

/// A program with a CONFIGURATION dimension. The honest variant folds
/// the configuration into its canonical bytes; case C uses both an
/// honest and a dishonest pairing.
struct ThresholdCounter {
    threshold: u8,
    canonical: Vec<u8>,
}
impl ThresholdCounter {
    /// Configuration declared: the threshold is part of the program's
    /// canonical bytes, so two configurations are two programs.
    fn declared(threshold: u8) -> Self {
        Self {
            threshold,
            canonical: format!("test.threshold-counter.v1 threshold={threshold}").into_bytes(),
        }
    }
    /// Configuration hidden: canonical bytes omit the threshold. Two
    /// configurations share one ProgramIdentity -- the declaration lies.
    fn hidden(threshold: u8) -> Self {
        Self {
            threshold,
            canonical: b"test.threshold-counter.v1".to_vec(),
        }
    }
}
impl DeterministicProgram for ThresholdCounter {
    fn canonical_bytes(&self) -> &[u8] {
        &self.canonical
    }
    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        let count = input.iter().filter(|b| **b >= self.threshold).count() as u64;
        Ok(NativeCompletion {
            output: count.to_le_bytes().to_vec(),
            exit_code: 0,
        })
    }
}

/// Completes with EMPTY output (case F): zero pairs to sum is a real
/// result; contrast with a fault, which commits nothing.
struct EmptyCommitter;
impl DeterministicProgram for EmptyCommitter {
    fn canonical_bytes(&self) -> &[u8] {
        b"test.empty-committer.v1"
    }
    fn run(&self, _input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        Ok(NativeCompletion {
            output: Vec::new(),
            exit_code: 0,
        })
    }
}

/// Echoes a constant (case G): a second, different program arranged to
/// produce byte-identical output to another program.
struct ConstantEcho(&'static [u8], &'static [u8]);
impl DeterministicProgram for ConstantEcho {
    fn canonical_bytes(&self) -> &[u8] {
        self.0
    }
    fn run(&self, _input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        Ok(NativeCompletion {
            output: self.1.to_vec(),
            exit_code: 0,
        })
    }
}

fn scripted_accepting_backend(id: &BackendId) -> impl ProofBackend {
    struct Accepting(BackendId);
    impl ProofBackend for Accepting {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage::COMPLETE
        }
        fn verify_supported(&self, _a: &ProofArtifact, e: &Expectation) -> AdapterVerdict {
            let required = e.required_checks();
            AdapterVerdict::Accept {
                coverage: VerificationCoverage {
                    program_checked: required.contains(&RequiredCheck::Program),
                    input_checked: required.contains(&RequiredCheck::Input),
                    output_checked: required.contains(&RequiredCheck::Output),
                    exit_code_checked: required.contains(&RequiredCheck::ExitCode),
                },
            }
        }
    }
    Accepting(id.clone())
}

// ---------------------------------------------------------------------
// STEP 13 -- the end-to-end walk, executed twice
// ---------------------------------------------------------------------

#[test]
fn end_to_end_two_executions_one_computation() {
    // program -> input -> occurrence -> execution -> output ->
    // computation identity -> verification interface. Twice.
    let kernel = PairwiseEnergyKernel;
    let input = encode_positions(&[(0, 0, 0), (5, 0, 0), (0, 5, 0), (3, 3, 3)]);
    let mut trace = ExecutionTrace::new();

    let first = execute(&mut trace, &kernel, &input);
    let second = execute(&mut trace, &kernel, &input);

    // Operation A != Operation B.
    assert_ne!(first.occurrence, second.occurrence);
    let a = trace.get(first.occurrence).unwrap();
    let b = trace.get(second.occurrence).unwrap();
    assert_ne!(a, b, "two executions remain two executions");

    // Output A == Output B, Computation A == Computation B.
    let out_a = first.result.as_ref().unwrap();
    let out_b = second.result.as_ref().unwrap();
    assert_eq!(
        out_a.output, out_b.output,
        "deterministic kernel, identical output bytes"
    );
    let computation_a = a.computation_identity().expect("completed");
    let computation_b = b.computation_identity().expect("completed");
    assert_eq!(computation_a, computation_b, "one computation");

    // The computation reaches the verification interface as an
    // EXPECTATION -- the statement a future proof would have to answer.
    let expectation = Expectation::of_program(*a.program())
        .with_input(*a.input())
        .with_output(OutputIdentity::of(&out_a.output))
        .with_exit_code(0);
    let backend_id = BackendId::new("scripted-complete", "1.0.0");
    let backend = scripted_accepting_backend(&backend_id);
    let artifact = ProofArtifact::new(backend_id, vec![0xAA]);
    match backend.verify(&artifact, &expectation) {
        VerificationResult::Verified {
            expectation: answered,
            coverage,
            ..
        } => {
            // The result names the very statement we built from the run.
            assert_eq!(answered, expectation);
            assert_eq!(coverage, VerificationCoverage::COMPLETE);
        }
        other => panic!("expected Verified, got {other:?}"),
    }
}

// ---------------------------------------------------------------------
// Cases A-L
// ---------------------------------------------------------------------

/// A + D: same computation executed twice, across occurrences.
#[test]
fn case_a_d_same_computation_twice_two_occurrences_one_identity() {
    let mut trace = ExecutionTrace::new();
    let input = encode_positions(&[(0, 0, 0), (6, 0, 0)]);
    let x = execute(&mut trace, &PairwiseEnergyKernel, &input);
    let y = execute(&mut trace, &PairwiseEnergyKernel, &input);
    assert_ne!(x.occurrence, y.occurrence);
    assert_eq!(
        trace.get(x.occurrence).unwrap().computation_identity(),
        trace.get(y.occurrence).unwrap().computation_identity(),
    );
}

/// B: same program, different input.
#[test]
fn case_b_same_program_different_input_different_computation() {
    let mut trace = ExecutionTrace::new();
    let x = execute(
        &mut trace,
        &PairwiseEnergyKernel,
        &encode_positions(&[(0, 0, 0), (4, 0, 0)]),
    );
    let y = execute(
        &mut trace,
        &PairwiseEnergyKernel,
        &encode_positions(&[(0, 0, 0), (9, 0, 0)]),
    );
    let a = trace.get(x.occurrence).unwrap();
    let b = trace.get(y.occurrence).unwrap();
    assert_eq!(a.program(), b.program());
    assert_ne!(a.input(), b.input());
    assert_ne!(a.computation_identity(), b.computation_identity());
}

/// C: same input, different configuration -- both halves of the burden.
#[test]
fn case_c_configuration_must_be_declared_to_be_identified() {
    let input = b"same bytes for every configuration".as_slice();
    let mut trace = ExecutionTrace::new();

    // Honest: configuration folded into the canonical program bytes.
    // Two configurations are two programs, hence two computations.
    let declared_low = execute(&mut trace, &ThresholdCounter::declared(10), input);
    let declared_high = execute(&mut trace, &ThresholdCounter::declared(200), input);
    let dl = trace.get(declared_low.occurrence).unwrap();
    let dh = trace.get(declared_high.occurrence).unwrap();
    assert_ne!(dl.program(), dh.program());
    assert_ne!(dl.computation_identity(), dh.computation_identity());

    // Dishonest: configuration hidden from the canonical bytes. The two
    // runs share a ProgramIdentity AND an InputIdentity -- the identity
    // layer cannot see the lie. What stays visible is the DIVERGENCE:
    // different outputs force different computation identities, so the
    // hidden configuration surfaces as "one specification, two
    // computations" -- a contradiction a consumer can notice, though
    // never one the substrate can prevent.
    let hidden_low = execute(&mut trace, &ThresholdCounter::hidden(10), input);
    let hidden_high = execute(&mut trace, &ThresholdCounter::hidden(200), input);
    let hl = trace.get(hidden_low.occurrence).unwrap();
    let hh = trace.get(hidden_high.occurrence).unwrap();
    assert_eq!(
        hl.program(),
        hh.program(),
        "the lie is invisible at identity level"
    );
    assert_eq!(hl.input(), hh.input());
    assert_ne!(
        hl.computation_identity(),
        hh.computation_identity(),
        "but the divergence is not"
    );
}

/// E: execution failure -- fault means no output, no computation identity.
#[test]
fn case_e_fault_yields_no_output_and_no_computation_identity() {
    let mut trace = ExecutionTrace::new();
    let run = execute(&mut trace, &PairwiseEnergyKernel, b"bad");
    let fault = run.result.unwrap_err();
    assert_eq!(fault.exit_code, 2);
    let occurrence = trace.get(run.occurrence).unwrap();
    assert!(matches!(
        occurrence.outcome(),
        ExecutionOutcome::Halted { exit_code: 2 }
    ));
    assert_eq!(
        occurrence.computation_identity(),
        None,
        "unknown output stays unknown"
    );
}

/// F: EMPTY output is a real output; ABSENT output is not.
#[test]
fn case_f_empty_output_is_not_absent_output() {
    let mut trace = ExecutionTrace::new();
    let empty = execute(&mut trace, &EmptyCommitter, b"anything");
    let faulted = execute(&mut trace, &PairwiseEnergyKernel, b"bad");

    let committed = trace.get(empty.occurrence).unwrap();
    assert!(
        committed.computation_identity().is_some(),
        "zero bytes committed IS a result"
    );
    match committed.outcome() {
        ExecutionOutcome::Completed { output, .. } => {
            assert_eq!(*output, OutputIdentity::of(b""));
        }
        other => panic!("expected Completed, got {other:?}"),
    }

    let absent = trace.get(faulted.occurrence).unwrap();
    assert_eq!(absent.computation_identity(), None);
}

/// G: identical output bytes from different computations.
#[test]
fn case_g_identical_output_different_computations() {
    let mut trace = ExecutionTrace::new();
    let first = ConstantEcho(b"test.echo-alpha.v1", b"identical output bytes");
    let second = ConstantEcho(b"test.echo-beta.v1", b"identical output bytes");
    let x = execute(&mut trace, &first, b"in");
    let y = execute(&mut trace, &second, b"in");
    let a = trace.get(x.occurrence).unwrap();
    let b = trace.get(y.occurrence).unwrap();
    // Same OutputIdentity...
    assert_eq!(x.result.unwrap().output, y.result.unwrap().output);
    // ...but the computation identities differ, because the program does.
    assert_ne!(a.computation_identity(), b.computation_identity());
}

/// H: malformed verification artifact.
#[test]
fn case_h_malformed_artifact_fails_with_nothing_examined() {
    struct RejectsMalformed(BackendId);
    impl ProofBackend for RejectsMalformed {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage::COMPLETE
        }
        fn verify_supported(&self, a: &ProofArtifact, _e: &Expectation) -> AdapterVerdict {
            if a.bytes().is_empty() {
                return AdapterVerdict::Reject {
                    coverage: VerificationCoverage::NONE,
                    failure: VerificationFailure::Malformed,
                };
            }
            AdapterVerdict::Accept {
                coverage: VerificationCoverage::COMPLETE,
            }
        }
    }
    let id = BackendId::new("scripted", "1.0.0");
    let backend = RejectsMalformed(id.clone());
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"))
        .with_input(InputIdentity::of(b"i"))
        .with_output(OutputIdentity::of(b"o"))
        .with_exit_code(0);
    match backend.verify(&ProofArtifact::new(id, vec![]), &expectation) {
        VerificationResult::Failed {
            coverage,
            failure,
            expectation: answered,
            ..
        } => {
            assert_eq!(failure, VerificationFailure::Malformed);
            assert_eq!(coverage, VerificationCoverage::NONE, "nothing was examined");
            assert_eq!(answered, expectation);
        }
        other => panic!("expected Failed, got {other:?}"),
    }
}

/// I: unsupported requirement declines rather than succeeding.
/// (The core construction already lives in semantics.rs; this variant
/// checks the Phase 129 shape -- the declined statement is named.)
#[test]
fn case_i_unsupported_names_the_statement_it_declined() {
    struct NoInput(BackendId);
    impl ProofBackend for NoInput {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage {
                program_checked: true,
                input_checked: false,
                output_checked: true,
                exit_code_checked: true,
            }
        }
        fn verify_supported(&self, _a: &ProofArtifact, _e: &Expectation) -> AdapterVerdict {
            AdapterVerdict::Accept {
                coverage: VerificationCoverage::COMPLETE,
            }
        }
    }
    let id = BackendId::new("scripted-sp1", "1.0.0");
    let backend = NoInput(id.clone());
    let expectation =
        Expectation::of_program(ProgramIdentity::of(b"p")).with_input(InputIdentity::of(b"i"));
    match backend.verify(&ProofArtifact::new(id, vec![1]), &expectation) {
        VerificationResult::Unsupported {
            expectation: answered,
            missing,
            ..
        } => {
            assert_eq!(answered, expectation);
            assert_eq!(missing, vec![RequiredCheck::Input]);
        }
        other => panic!("expected Unsupported, got {other:?}"),
    }
}

/// J: downstream rejection is NOT an execution outcome.
///
/// The Python operation ledger (Phase 125) records succeeded->rejected
/// when a boundary refuses what a dispatch produced. The Rust execution
/// outcome deliberately has no such state: the execution DID complete,
/// and its record is written once. Rejection is a fact about a
/// different ledger at a different seam; representing it here would
/// let a downstream veto rewrite execution history.
#[test]
fn case_j_downstream_rejection_cannot_rewrite_the_execution() {
    let mut trace = ExecutionTrace::new();
    let input = encode_positions(&[(0, 0, 0), (7, 0, 0)]);
    let run = execute(&mut trace, &PairwiseEnergyKernel, &input);
    let identity_before = trace.get(run.occurrence).unwrap().computation_identity();

    // A downstream consumer rejects the result. The only thing it could
    // try against this ledger is a re-resolution -- which is refused.
    assert_eq!(
        trace.resolve(run.occurrence, ExecutionOutcome::Indeterminate),
        Err(TraceError::AlreadyResolved(run.occurrence)),
    );
    assert_eq!(
        trace.get(run.occurrence).unwrap().computation_identity(),
        identity_before
    );
}

/// K: retry after failure is a new occurrence; the failure stands.
#[test]
fn case_k_retry_is_a_new_occurrence_and_the_failure_stands() {
    let mut trace = ExecutionTrace::new();
    let failed = execute(&mut trace, &PairwiseEnergyKernel, b"bad");
    let retried = execute(
        &mut trace,
        &PairwiseEnergyKernel,
        &encode_positions(&[(0, 0, 0), (5, 5, 5)]),
    );
    assert_ne!(failed.occurrence, retried.occurrence);
    assert!(
        matches!(
            trace.get(failed.occurrence).unwrap().outcome(),
            ExecutionOutcome::Halted { .. }
        ),
        "the failure is not erased by the retry"
    );
    assert!(trace
        .get(retried.occurrence)
        .unwrap()
        .computation_identity()
        .is_some());
}

/// L: stochastic computation with explicit seed. The seed is input, so
/// it is identity: same seed collapses across occurrences, different
/// seed separates.
#[test]
fn case_l_seeded_stochastic_computation() {
    let mut trace = ExecutionTrace::new();
    let seed_a = 42u64.to_le_bytes();
    let seed_b = 43u64.to_le_bytes();

    let first = execute(&mut trace, &SeededStream, &seed_a);
    let second = execute(&mut trace, &SeededStream, &seed_a);
    let third = execute(&mut trace, &SeededStream, &seed_b);

    assert_eq!(
        first.result.as_ref().unwrap().output,
        second.result.as_ref().unwrap().output,
        "same seed, same stream"
    );
    assert_eq!(
        trace.get(first.occurrence).unwrap().computation_identity(),
        trace.get(second.occurrence).unwrap().computation_identity(),
    );
    assert_ne!(
        trace.get(first.occurrence).unwrap().computation_identity(),
        trace.get(third.occurrence).unwrap().computation_identity(),
        "a different seed is a different computation"
    );
}

// ---------------------------------------------------------------------
// The Phase 128 probes, inverted: each demonstrated a hole in the
// Phase 127 shape; the identical construction must now hit the repair.
// ---------------------------------------------------------------------

/// Probe 1 inverted: the warrant is no longer detachable. Verifying one
/// artifact against two different programs yields two DIFFERENT result
/// objects, each naming the statement it answered.
#[test]
fn repaired_verified_results_name_their_statements() {
    let id = BackendId::new("scripted", "1.0.0");
    let backend = scripted_accepting_backend(&id);
    let artifact = ProofArtifact::new(id, vec![1, 2, 3]);

    let e1 = Expectation::of_program(ProgramIdentity::of(b"program A"));
    let e2 = Expectation::of_program(ProgramIdentity::of(b"program B"));
    let r1 = backend.verify(&artifact, &e1);
    let r2 = backend.verify(&artifact, &e2);

    assert_ne!(r1, r2, "distinct claims now yield distinguishable warrants");
    match r1 {
        VerificationResult::Verified { expectation, .. } => {
            assert_eq!(expectation.program(), &ProgramIdentity::of(b"program A"));
        }
        other => panic!("expected Verified, got {other:?}"),
    }
}

/// Probe 2 inverted: coverage inflation is refused by the entry point.
/// An adapter declaring input_checked: false that reports having
/// checked the input is an adapter contract violation, never a success.
#[test]
fn repaired_coverage_inflation_is_refused() {
    struct Inflator(BackendId);
    impl ProofBackend for Inflator {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage {
                program_checked: true,
                input_checked: false,
                output_checked: true,
                exit_code_checked: true,
            }
        }
        fn verify_supported(&self, _a: &ProofArtifact, _e: &Expectation) -> AdapterVerdict {
            AdapterVerdict::Accept {
                coverage: VerificationCoverage::COMPLETE,
            }
        }
    }
    let id = BackendId::new("scripted", "1.0.0");
    let backend = Inflator(id.clone());
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"));
    match backend.verify(&ProofArtifact::new(id, vec![9]), &expectation) {
        VerificationResult::Failed {
            failure, coverage, ..
        } => {
            assert!(matches!(
                failure,
                VerificationFailure::AdapterContractViolation { .. }
            ));
            assert_eq!(coverage, VerificationCoverage::NONE);
        }
        other => panic!("inflation produced {other:?}"),
    }
}

/// The under-coverage direction of the same clamp: accepting while
/// covering LESS than the expectation required is equally a contract
/// violation -- a Verified must cover everything that was asked.
#[test]
fn repaired_under_coverage_acceptance_is_refused() {
    struct Slacker(BackendId);
    impl ProofBackend for Slacker {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage::COMPLETE
        }
        fn verify_supported(&self, _a: &ProofArtifact, _e: &Expectation) -> AdapterVerdict {
            AdapterVerdict::Accept {
                coverage: VerificationCoverage::NONE,
            }
        }
    }
    let id = BackendId::new("scripted", "1.0.0");
    let backend = Slacker(id.clone());
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"));
    match backend.verify(&ProofArtifact::new(id, vec![9]), &expectation) {
        VerificationResult::Failed { failure, .. } => {
            assert!(matches!(
                failure,
                VerificationFailure::AdapterContractViolation { .. }
            ));
        }
        other => panic!("under-coverage acceptance produced {other:?}"),
    }
}

// ---------------------------------------------------------------------
// The two honest negatives, as tests
// ---------------------------------------------------------------------

/// COMPUTATION != MEASUREMENT.
///
/// World A: `123.4` was read off a load frame and transcribed.
/// World B: `123.4` was typed into a script.
/// The bytes are identical, so every identity in this substrate is
/// identical, so the computations are identical. The substrate CANNOT
/// tell the worlds apart -- and a zkVM proof would not change this,
/// because a fabricated value can be computed faithfully. This is
/// Phase 111b, held as an executable assertion so it cannot quietly be
/// forgotten: any future change that makes this test fail is claiming
/// to witness physical history from content, and is wrong.
#[test]
fn computation_is_not_measurement() {
    let measured_world = b"specimen-7 modulus 123.4";
    let scripted_world = b"specimen-7 modulus 123.4";

    assert_eq!(
        InputIdentity::of(measured_world),
        InputIdentity::of(scripted_world)
    );

    let mut trace = ExecutionTrace::new();
    let from_instrument = execute(&mut trace, &SeededStream, &42u64.to_le_bytes());
    let from_script = execute(&mut trace, &SeededStream, &42u64.to_le_bytes());
    assert_eq!(
        trace
            .get(from_instrument.occurrence)
            .unwrap()
            .computation_identity(),
        trace
            .get(from_script.occurrence)
            .unwrap()
            .computation_identity(),
        "the provenance of the input bytes is invisible to every identity here"
    );
}

/// Native ProgramIdentity binds BYTES, not BEHAVIOR.
///
/// Two programs declaring identical canonical bytes but computing
/// different functions share one ProgramIdentity; the lie surfaces only
/// as divergent computations under one program identity. Closing this
/// gap -- computing the program commitment from the artifact the
/// machine actually executed -- is exactly what a zkVM backend is for,
/// and exactly what BackendKind::Native never claims.
#[test]
fn native_program_identity_binds_bytes_not_behavior() {
    let honest = ConstantEcho(b"claims.v1", b"result-one");
    let impostor = ConstantEcho(b"claims.v1", b"result-two");
    assert_eq!(
        ProgramIdentity::of(honest.canonical_bytes()),
        ProgramIdentity::of(impostor.canonical_bytes()),
        "identical declarations, one identity -- the substrate cannot see behavior"
    );

    let mut trace = ExecutionTrace::new();
    let x = execute(&mut trace, &honest, b"in");
    let y = execute(&mut trace, &impostor, b"in");
    assert_ne!(
        trace.get(x.occurrence).unwrap().computation_identity(),
        trace.get(y.occurrence).unwrap().computation_identity(),
        "the divergence is visible even though the deception is not"
    );
}

/// And native execution still cannot borrow a proof -- restated at the
/// engine level now that an engine exists.
#[test]
fn engine_created_occurrences_refuse_proofs() {
    let mut trace = ExecutionTrace::new();
    let run = execute(
        &mut trace,
        &PairwiseEnergyKernel,
        &encode_positions(&[(0, 0, 0), (4, 4, 4)]),
    );
    let artifact = ProofArtifact::new(BackendId::new("scripted", "1.0.0"), vec![1]);
    assert_eq!(
        trace.attach_proof(run.occurrence, &artifact),
        Err(TraceError::Proof(
            AttachProofError::NativeExecutionHasNoProof
        )),
    );
}
