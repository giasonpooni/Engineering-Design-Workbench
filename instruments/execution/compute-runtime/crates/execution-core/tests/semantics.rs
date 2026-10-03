//! Semantic tests for the execution substrate.
//!
//! These test MEANINGS, not implementation volume. Each one corresponds
//! to a claim the substrate makes, and each would fail if that claim
//! quietly stopped being true.

use execution_core::*;

// ---------------------------------------------------------------------
// A test-only backend. It proves nothing and verifies nothing; it exists
// so the SEMANTICS of capability screening can be exercised without a
// real prover. Every result it returns is a fixture.
// ---------------------------------------------------------------------

struct ScriptedBackend {
    id: BackendId,
    capabilities: VerificationCoverage,
    outcome: ScriptedOutcome,
}

enum ScriptedOutcome {
    Accept,
    Reject(VerificationFailure),
}

impl ProofBackend for ScriptedBackend {
    fn backend(&self) -> &BackendId {
        &self.id
    }

    fn capabilities(&self) -> VerificationCoverage {
        self.capabilities
    }

    fn verify_supported(
        &self,
        _artifact: &ProofArtifact,
        expectation: &Expectation,
    ) -> AdapterVerdict {
        // A real backend checks the proof here. This one reports exactly
        // the coverage the expectation required and nothing more, which
        // is what an honest backend does. Since Phase 128 an adapter
        // reports a VERDICT; the sealed entry point assembles the result.
        let required = expectation.required_checks();
        let coverage = VerificationCoverage {
            program_checked: required.contains(&RequiredCheck::Program),
            input_checked: required.contains(&RequiredCheck::Input),
            output_checked: required.contains(&RequiredCheck::Output),
            exit_code_checked: required.contains(&RequiredCheck::ExitCode),
        };
        match &self.outcome {
            ScriptedOutcome::Accept => AdapterVerdict::Accept { coverage },
            ScriptedOutcome::Reject(failure) => AdapterVerdict::Reject {
                coverage,
                failure: failure.clone(),
            },
        }
    }
}

/// Capabilities matching what Phase 126 found SP1 can actually do:
/// program, output and exit code -- never the input, because `SP1Stdin`
/// is never committed to.
const SP1_SHAPED: VerificationCoverage = VerificationCoverage {
    program_checked: true,
    input_checked: false,
    output_checked: true,
    exit_code_checked: true,
};

/// Capabilities matching what Phase 126 found Nexus can do: the input
/// too, because `verify_expected` reconstructs the whole `View`.
const NEXUS_SHAPED: VerificationCoverage = VerificationCoverage::COMPLETE;

// ---------------------------------------------------------------------
// Canonical encoding and identity
// ---------------------------------------------------------------------

#[test]
fn canonical_input_a_yields_identity_x_every_time() {
    let a = b"canonical input A";
    let x1 = InputIdentity::of(a);
    let x2 = InputIdentity::of(a);
    assert_eq!(
        x1, x2,
        "the same canonical input must yield the same identity"
    );
    assert_eq!(x1.to_hex(), x2.to_hex());
}

#[test]
fn canonical_input_b_yields_a_different_identity() {
    let x = InputIdentity::of(b"canonical input A");
    let y = InputIdentity::of(b"canonical input B");
    assert_ne!(x, y, "different inputs must not share an identity");
}

#[test]
fn identity_kinds_are_domain_separated() {
    // The same bytes as a program and as an input are NOT the same
    // identity. Without the domain tag they would be, and a program
    // could be mistaken for the input it ran on.
    let bytes = b"identical bytes";
    assert_ne!(
        ProgramIdentity::of(bytes).to_hex(),
        InputIdentity::of(bytes).to_hex()
    );
    assert_ne!(
        InputIdentity::of(bytes).to_hex(),
        OutputIdentity::of(bytes).to_hex()
    );
    assert_ne!(
        ProgramIdentity::of(bytes).to_hex(),
        OutputIdentity::of(bytes).to_hex()
    );
}

#[test]
fn identity_hex_matches_the_repositorys_existing_form() {
    // 64 lowercase hex characters -- the same shape
    // `evidence/identity.py::content_hash` produces. A second hex
    // convention is how identities silently stop matching.
    let hex = ProgramIdentity::of(b"p").to_hex();
    assert_eq!(hex.len(), 64);
    assert_eq!(hex, hex.to_lowercase());
}

#[test]
fn proof_identity_binds_the_backend_version() {
    // Phase 126 §8: a proof is verifiable by a COMPATIBLE verifier, not
    // forever. The same bytes under two versions are two proofs.
    let bytes = vec![1u8, 2, 3];
    let v1 = ProofArtifact::new(BackendId::new("scripted", "1.0.0"), bytes.clone());
    let v2 = ProofArtifact::new(BackendId::new("scripted", "2.0.0"), bytes);
    assert_ne!(v1.identity(), v2.identity());
}

// ---------------------------------------------------------------------
// Occurrence: the same computation, two executions
// ---------------------------------------------------------------------

#[test]
fn two_executions_of_one_computation_remain_two_executions() {
    let program = ProgramIdentity::of(b"program");
    let input = InputIdentity::of(b"input");
    let output = OutputIdentity::of(b"output");

    let mut trace = ExecutionTrace::new();
    let first = trace.begin(program, input, BackendKind::Native);
    let second = trace.begin(program, input, BackendKind::Native);

    trace
        .resolve(
            first,
            ExecutionOutcome::Completed {
                output,
                exit_code: 0,
            },
        )
        .unwrap();
    trace
        .resolve(
            second,
            ExecutionOutcome::Completed {
                output,
                exit_code: 0,
            },
        )
        .unwrap();

    let a = trace.get(first).unwrap();
    let b = trace.get(second).unwrap();

    // Identical program, input and output...
    assert_eq!(a.program(), b.program());
    assert_eq!(a.input(), b.input());
    assert_eq!(a.outcome(), b.outcome());

    // ...therefore the SAME COMPUTATION...
    assert_eq!(
        a.computation_identity(),
        b.computation_identity(),
        "same program + same input + same output = same computation"
    );
    assert!(a.computation_identity().is_some());

    // ...but STILL TWO EXECUTIONS.
    assert_ne!(a, b, "execution #1 must not equal execution #2");
    assert_ne!(a.occurrence(), b.occurrence());
    assert_eq!(trace.occurrences().len(), 2);
}

#[test]
fn a_different_computation_has_a_different_computation_identity() {
    let mut trace = ExecutionTrace::new();
    let program = ProgramIdentity::of(b"program");

    let first = trace.begin(program, InputIdentity::of(b"in-1"), BackendKind::Native);
    let second = trace.begin(program, InputIdentity::of(b"in-2"), BackendKind::Native);
    for occurrence in [first, second] {
        trace
            .resolve(
                occurrence,
                ExecutionOutcome::Completed {
                    output: OutputIdentity::of(b"out"),
                    exit_code: 0,
                },
            )
            .unwrap();
    }
    assert_ne!(
        trace.get(first).unwrap().computation_identity(),
        trace.get(second).unwrap().computation_identity()
    );
}

#[test]
fn an_unresolved_execution_has_no_computation_identity() {
    // Unknown stays unknown. There is no placeholder output, and no zero
    // standing in for one.
    let mut trace = ExecutionTrace::new();
    let occurrence = trace.begin(
        ProgramIdentity::of(b"p"),
        InputIdentity::of(b"i"),
        BackendKind::Native,
    );
    assert_eq!(trace.get(occurrence).unwrap().computation_identity(), None);

    trace
        .resolve(occurrence, ExecutionOutcome::Indeterminate)
        .unwrap();
    assert_eq!(
        trace.get(occurrence).unwrap().computation_identity(),
        None,
        "an indeterminate outcome yields no computation identity"
    );
}

#[test]
fn an_occurrence_is_resolved_once() {
    let mut trace = ExecutionTrace::new();
    let occurrence = trace.begin(
        ProgramIdentity::of(b"p"),
        InputIdentity::of(b"i"),
        BackendKind::Native,
    );
    trace
        .resolve(occurrence, ExecutionOutcome::Halted { exit_code: 1 })
        .unwrap();
    assert_eq!(
        trace.resolve(occurrence, ExecutionOutcome::Indeterminate),
        Err(TraceError::AlreadyResolved(occurrence)),
        "history is written once"
    );
}

// ---------------------------------------------------------------------
// Native execution
// ---------------------------------------------------------------------

#[test]
fn native_execution_produces_an_occurrence_but_never_a_proof() {
    let mut trace = ExecutionTrace::new();
    let occurrence = trace.begin(
        ProgramIdentity::of(b"p"),
        InputIdentity::of(b"i"),
        BackendKind::Native,
    );
    trace
        .resolve(
            occurrence,
            ExecutionOutcome::Completed {
                output: OutputIdentity::of(b"o"),
                exit_code: 0,
            },
        )
        .unwrap();

    // It IS an execution: it has an occurrence and a computation identity.
    assert!(trace
        .get(occurrence)
        .unwrap()
        .computation_identity()
        .is_some());

    // It is NOT cryptographically witnessed, and cannot borrow a witness.
    let artifact = ProofArtifact::new(BackendId::new("scripted", "1.0.0"), vec![9, 9, 9]);
    assert_eq!(
        trace.attach_proof(occurrence, &artifact),
        Err(TraceError::Proof(
            AttachProofError::NativeExecutionHasNoProof
        ))
    );
    assert_eq!(trace.get(occurrence).unwrap().proof(), None);
}

#[test]
fn a_proving_backend_may_attach_its_own_proof_and_only_its_own() {
    let sp1 = BackendId::new("scripted-sp1", "1.0.0");
    let nexus = BackendId::new("scripted-nexus", "1.0.0");

    let mut trace = ExecutionTrace::new();
    let occurrence = trace.begin(
        ProgramIdentity::of(b"p"),
        InputIdentity::of(b"i"),
        BackendKind::Proving(sp1.clone()),
    );

    let foreign = ProofArtifact::new(nexus.clone(), vec![1]);
    assert!(matches!(
        trace.attach_proof(occurrence, &foreign),
        Err(TraceError::Proof(AttachProofError::BackendMismatch { .. }))
    ));

    let own = ProofArtifact::new(sp1, vec![1]);
    trace.attach_proof(occurrence, &own).unwrap();
    assert_eq!(
        trace.get(occurrence).unwrap().proof(),
        Some(&own.identity())
    );

    assert_eq!(
        trace.attach_proof(occurrence, &own),
        Err(TraceError::Proof(AttachProofError::AlreadyAttached))
    );
}

// ---------------------------------------------------------------------
// Verification semantics
// ---------------------------------------------------------------------

#[test]
fn partial_coverage_is_not_complete_verification() {
    let partial = VerificationCoverage {
        program_checked: true,
        input_checked: false,
        output_checked: true,
        exit_code_checked: true,
    };

    // The claim under test, stated three ways.
    assert_ne!(partial, VerificationCoverage::COMPLETE);
    assert!(!partial.includes(RequiredCheck::Input));

    // And, concretely: it does not satisfy an expectation that requires
    // the input, no matter how much else it covers.
    let full = Expectation::of_program(ProgramIdentity::of(b"p"))
        .with_input(InputIdentity::of(b"i"))
        .with_output(OutputIdentity::of(b"o"))
        .with_exit_code(0);
    assert_eq!(partial.missing(&full), vec![RequiredCheck::Input]);
}

#[test]
fn coverage_defaults_to_nothing_checked() {
    assert_eq!(VerificationCoverage::default(), VerificationCoverage::NONE);
    for check in [
        RequiredCheck::Program,
        RequiredCheck::Input,
        RequiredCheck::Output,
        RequiredCheck::ExitCode,
    ] {
        assert!(!VerificationCoverage::NONE.includes(check));
    }
}

#[test]
fn an_unsupported_expectation_cannot_become_success() {
    // THE test. An SP1-shaped backend cannot check an input (Phase 126
    // §6: SP1Stdin is never committed to). Asked to confirm one, it must
    // NOT return Verified with input_checked: false -- it must decline.
    let backend = ScriptedBackend {
        id: BackendId::new("scripted-sp1", "1.0.0"),
        capabilities: SP1_SHAPED,
        outcome: ScriptedOutcome::Accept, // it would happily accept
    };
    let artifact = ProofArtifact::new(backend.id.clone(), vec![1, 2, 3]);
    let expectation =
        Expectation::of_program(ProgramIdentity::of(b"p")).with_input(InputIdentity::of(b"i"));

    let result = backend.verify(&artifact, &expectation);

    match result {
        VerificationResult::Unsupported {
            capabilities,
            missing,
            backend: reported,
            ..
        } => {
            assert_eq!(missing, vec![RequiredCheck::Input]);
            assert_eq!(capabilities, SP1_SHAPED);
            assert_eq!(reported, backend.id);
        }
        other => panic!("an uncheckable requirement became {other:?}"),
    }

    // Restated as the invariant it protects: no Verified anywhere.
    assert!(!matches!(
        backend.verify(&artifact, &expectation),
        VerificationResult::Verified { .. }
    ));
}

#[test]
fn the_same_expectation_is_supported_by_a_backend_that_can_bind_the_input() {
    // The other half of the asymmetry: a Nexus-shaped backend CAN bind
    // the input, so the identical expectation reaches it.
    let backend = ScriptedBackend {
        id: BackendId::new("scripted-nexus", "1.0.0"),
        capabilities: NEXUS_SHAPED,
        outcome: ScriptedOutcome::Accept,
    };
    let artifact = ProofArtifact::new(backend.id.clone(), vec![1, 2, 3]);
    let expectation =
        Expectation::of_program(ProgramIdentity::of(b"p")).with_input(InputIdentity::of(b"i"));

    match backend.verify(&artifact, &expectation) {
        VerificationResult::Verified { coverage, .. } => {
            assert!(coverage.input_checked);
            assert!(coverage.program_checked);
        }
        other => panic!("expected Verified, got {other:?}"),
    }
}

#[test]
fn verified_reports_coverage_and_does_not_imply_all_four() {
    // A caller who asked only about the program gets a Verified whose
    // input_checked is false. That is correct, and it must stay visible.
    let backend = ScriptedBackend {
        id: BackendId::new("scripted-sp1", "1.0.0"),
        capabilities: SP1_SHAPED,
        outcome: ScriptedOutcome::Accept,
    };
    let artifact = ProofArtifact::new(backend.id.clone(), vec![7]);
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"));

    match backend.verify(&artifact, &expectation) {
        VerificationResult::Verified { coverage, .. } => {
            assert!(coverage.program_checked);
            assert!(
                !coverage.input_checked,
                "nothing was checked about the input"
            );
            assert_ne!(
                coverage,
                VerificationCoverage::COMPLETE,
                "a success must never be read as complete verification"
            );
        }
        other => panic!("expected Verified, got {other:?}"),
    }
}

#[test]
fn a_failure_still_reports_what_was_checked() {
    let backend = ScriptedBackend {
        id: BackendId::new("scripted-sp1", "1.0.0"),
        capabilities: SP1_SHAPED,
        outcome: ScriptedOutcome::Reject(VerificationFailure::OutputMismatch),
    };
    let artifact = ProofArtifact::new(backend.id.clone(), vec![7]);
    let expectation =
        Expectation::of_program(ProgramIdentity::of(b"p")).with_output(OutputIdentity::of(b"o"));

    match backend.verify(&artifact, &expectation) {
        VerificationResult::Failed {
            coverage, failure, ..
        } => {
            assert_eq!(failure, VerificationFailure::OutputMismatch);
            assert!(coverage.program_checked);
            assert!(coverage.output_checked);
        }
        other => panic!("expected Failed, got {other:?}"),
    }
}

#[test]
fn the_three_results_are_mutually_distinguishable() {
    // Verified / Failed / Unsupported must never collapse into each
    // other. A caller matching on the result cannot mistake a decline
    // for a success or a success for a failure.
    let coverage = VerificationCoverage::NONE;
    let backend = BackendId::new("scripted", "1.0.0");
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"));
    let verified = VerificationResult::Verified {
        expectation: expectation.clone(),
        coverage,
        proof: ProofArtifact::new(backend.clone(), vec![]).identity(),
        backend: backend.clone(),
    };
    let failed = VerificationResult::Failed {
        expectation: expectation.clone(),
        coverage,
        failure: VerificationFailure::InvalidProof,
        backend: backend.clone(),
    };
    let unsupported = VerificationResult::Unsupported {
        expectation,
        capabilities: coverage,
        missing: vec![RequiredCheck::Input],
        backend,
    };
    assert_ne!(verified, failed);
    assert_ne!(failed, unsupported);
    assert_ne!(verified, unsupported);
}

#[test]
fn the_input_commitment_invariant_is_recorded_in_the_substrate() {
    // Documented now, implemented later. A backend that reports
    // input_checked on the strength of a host-supplied digest has
    // violated this, and Phase 126 found RISC Zero's `input_digest` is
    // exactly such a digest.
    assert!(INPUT_COMMITMENT_INVARIANT.contains("host-side assertion"));
    assert!(INPUT_COMMITMENT_INVARIANT.contains("insufficient"));
}

#[test]
fn the_rust_commitment_agrees_with_the_repositorys_python_primitive() {
    // These vectors were computed by Python -- `hashlib.sha256` over the
    // canonical encoding reimplemented in `struct.pack('<Q', ...)` form --
    // and pasted here. They are the proof that implementing SHA-256 in
    // this workspace rather than depending on a crate did not quietly
    // create a SECOND identity system alongside
    // `evidence/identity.py::content_hash`.
    //
    // If the canonical encoding or the hash ever changes, these fail, and
    // they should: every identity this substrate has ever issued would
    // have changed with it.
    assert_eq!(
        ProgramIdentity::of(b"hello").to_hex(),
        "9ebc0016a12b82a8588c1e021d46b5cf3f43f330ebc71ead63a6e36fab8f4535"
    );
    assert_eq!(
        InputIdentity::of(b"hello").to_hex(),
        "df8dafd17d787e3f0ae9b123547bc46e2188c6259fabcf0b0f3c5ac9c24dc4a7"
    );
    assert_eq!(
        OutputIdentity::of(b"").to_hex(),
        "86a35cb4e4a48a18646c34a9986f3fcf85eb3bbaa3089809904844c12d38cff1"
    );
}

#[test]
fn verified_execution_exists_only_for_verified_results() {
    // Requirement 8's type-level half: "verified = false" is
    // unrepresentable. From a Failed or Unsupported result there is
    // NOTHING -- no object with a flag to ignore, no weaker success to
    // quietly accept.
    let backend = BackendId::new("scripted", "1.0.0");
    let expectation = Expectation::of_program(ProgramIdentity::of(b"p"));
    let coverage = VerificationCoverage {
        program_checked: true,
        input_checked: false,
        output_checked: false,
        exit_code_checked: false,
    };

    let verified = VerificationResult::Verified {
        expectation: expectation.clone(),
        coverage,
        proof: ProofArtifact::new(backend.clone(), vec![1]).identity(),
        backend: backend.clone(),
    };
    let failed = VerificationResult::Failed {
        expectation: expectation.clone(),
        coverage,
        failure: VerificationFailure::InvalidProof,
        backend: backend.clone(),
    };
    let unsupported = VerificationResult::Unsupported {
        expectation: expectation.clone(),
        capabilities: coverage,
        missing: vec![RequiredCheck::Input],
        backend,
    };

    let value = VerifiedExecution::from_result(&verified).expect("Verified yields the object");
    assert_eq!(
        value.expectation(),
        &expectation,
        "it carries its statement"
    );
    assert_eq!(VerifiedExecution::from_result(&failed), None);
    assert_eq!(VerifiedExecution::from_result(&unsupported), None);
}

#[test]
fn a_confirm_style_backend_declines_partial_statements_as_unsupported() {
    // Stage 3: a backend whose verifier can only CONFIRM a total
    // statement (Nexus's verify_expected reconstructs the whole
    // execution view) declines an expectation that omits dimensions it
    // must reconstruct -- and the sealed entry point surfaces that as
    // Unsupported, never as a weaker Verified.
    struct ConfirmOnly(BackendId);
    impl ProofBackend for ConfirmOnly {
        fn backend(&self) -> &BackendId {
            &self.0
        }
        fn capabilities(&self) -> VerificationCoverage {
            VerificationCoverage::COMPLETE
        }
        fn verify_supported(&self, _a: &ProofArtifact, e: &Expectation) -> AdapterVerdict {
            let mut missing = alloc_missing(e);
            if !missing.is_empty() {
                return AdapterVerdict::Decline {
                    missing: core::mem::take(&mut missing),
                };
            }
            AdapterVerdict::Accept {
                coverage: VerificationCoverage::COMPLETE,
            }
        }
    }
    fn alloc_missing(e: &Expectation) -> Vec<RequiredCheck> {
        let mut missing = vec![];
        if e.input().is_none() {
            missing.push(RequiredCheck::Input);
        }
        if e.output().is_none() {
            missing.push(RequiredCheck::Output);
        }
        if e.exit_code().is_none() {
            missing.push(RequiredCheck::ExitCode);
        }
        missing
    }

    let id = BackendId::new("scripted-nexus", "0.3.6");
    let backend = ConfirmOnly(id.clone());
    let artifact = ProofArtifact::new(id, vec![1]);

    // A partial statement: unanswerable by this backend, visibly so.
    let partial = Expectation::of_program(ProgramIdentity::of(b"p"));
    match backend.verify(&artifact, &partial) {
        VerificationResult::Unsupported {
            missing,
            expectation,
            ..
        } => {
            assert_eq!(
                missing,
                vec![
                    RequiredCheck::Input,
                    RequiredCheck::Output,
                    RequiredCheck::ExitCode
                ]
            );
            assert_eq!(expectation, partial);
        }
        other => panic!("a partial statement produced {other:?}"),
    }

    // A total statement: answerable.
    let total = Expectation::of_program(ProgramIdentity::of(b"p"))
        .with_input(InputIdentity::of(b"i"))
        .with_output(OutputIdentity::of(b"o"))
        .with_exit_code(0);
    assert!(matches!(
        backend.verify(&artifact, &total),
        VerificationResult::Verified { .. }
    ));
}
