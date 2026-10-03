//! Verification semantics: what was asked, what was checked, what came back.
//!
//! # Why verification is not Boolean
//!
//! Phase 126 §6 established that the three zkVM substrates do not agree
//! about what a proof covers:
//!
//! ```text
//! SP1        does not commit to its input at all. SP1Stdin is never
//!            hashed and never reaches verify_proof, which checks
//!            version, exit code and public-values digest only.
//! RISC Zero  has a ReceiptClaim.input field, but Input is an
//!            UNINHABITED type; the only value that can reach it is a
//!            host-DECLARED input_digest, and Receipt::verify requires
//!            that digest to be zero.
//! Nexus      genuinely binds it -- verify_expected() reconstructs the
//!            whole execution View, input memory included.
//! ```
//!
//! Given `fn verify(proof, expectation) -> bool`, an SP1 backend returns
//! `true` having checked program and output only; a Nexus backend
//! returns the identical `true` having also checked the input. The
//! caller cannot tell them apart and is entitled to believe the stronger
//! claim in both cases -- Phase 111's failure mode (an unwarranted claim
//! entering through a gate that looks like it checked) reintroduced by
//! the abstraction itself. `Result<(), Error>` carries the same single
//! bit and fails identically.
//!
//! # The two Phase 128 repairs
//!
//! The Phase 128 adversarial review ran two probes against the Phase 127
//! version of this module and both drew blood:
//!
//! **The detachable warrant.** `Verified { coverage, proof, backend }`
//! did not name the expectation it satisfied. Verifying one artifact
//! against program A and against program B produced IDENTICAL result
//! objects: the warrant floated free of its proposition, and a later
//! reader could attach it to a claim it never checked. Phase 111 one
//! level up -- Phase 127 kept HOW MUCH was checked and discarded WHAT
//! was checked. Repair: every [`VerificationResult`] variant embeds the
//! [`Expectation`] it answered, and the sealed entry point embeds it, so
//! an adapter cannot mis-attach it.
//!
//! **Coverage inflation.** The Phase 127 entry point screened
//! capabilities BEFORE dispatch but returned the adapter's claimed
//! coverage verbatim -- an adapter whose own `capabilities()` said
//! `input_checked: false` answered `Verified` with `input_checked: true`
//! and it passed through. Repair: adapters no longer construct
//! [`VerificationResult`] at all. They return the narrower
//! [`AdapterVerdict`], and [`ProofBackend::verify`] assembles the result
//! itself: the proof identity is computed from the artifact actually
//! examined, the expectation is embedded verbatim, and claimed coverage
//! outside `capabilities()` or below the expectation's requirements is
//! refused as [`VerificationFailure::AdapterContractViolation`].
//!
//! What remains trusted -- and is stated as trusted rather than
//! disguised as verified -- is the adapter's word that its coverage
//! reflects what its backend's verifier actually enforced. That is the
//! trusted adapter boundary (`docs/ZKVM_ADAPTER_BOUNDARY.md`); it is
//! auditable by tamper-vector conformance tests, not provable from here.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

use alloc::vec::Vec;
use execution_model::{
    BackendId, InputIdentity, OutputIdentity, ProgramIdentity, ProofArtifact, ProofIdentity,
};

/// One thing a caller can require a verifier to check.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub enum RequiredCheck {
    /// That the proved execution ran THIS program.
    Program,
    /// That the proved execution ran on THIS input.
    ///
    /// Requiring this is the strong ask. Per
    /// [`execution_model::INPUT_COMMITMENT_INVARIANT`], a backend may
    /// only claim to have checked it if the proved execution itself
    /// binds the canonical [`InputIdentity`].
    Input,
    /// That the proved execution produced THIS output.
    Output,
    /// That the proved execution ended with THIS exit code.
    ExitCode,
}

/// What a caller requires of a verification -- the STATEMENT to check.
///
/// The program is always required: a proof about an unspecified program
/// is not a claim about anything. Everything else is opt-in, and opting
/// in is what makes a backend that cannot deliver return
/// [`VerificationResult::Unsupported`] instead of a success.
///
/// Since Phase 128 this type is also the payload of every
/// [`VerificationResult`]: a result names the statement it answered, so
/// it can never again be read as answering a different one.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Expectation {
    program: ProgramIdentity,
    input: Option<InputIdentity>,
    output: Option<OutputIdentity>,
    exit_code: Option<u32>,
}

impl Expectation {
    /// Require only that the proof is about this program.
    pub const fn of_program(program: ProgramIdentity) -> Self {
        Self {
            program,
            input: None,
            output: None,
            exit_code: None,
        }
    }

    /// Additionally require that the execution ran on this input.
    #[must_use]
    pub fn with_input(mut self, input: InputIdentity) -> Self {
        self.input = Some(input);
        self
    }

    /// Additionally require that the execution produced this output.
    #[must_use]
    pub fn with_output(mut self, output: OutputIdentity) -> Self {
        self.output = Some(output);
        self
    }

    /// Additionally require that the execution ended with this exit code.
    #[must_use]
    pub fn with_exit_code(mut self, exit_code: u32) -> Self {
        self.exit_code = Some(exit_code);
        self
    }

    /// The required program.
    pub const fn program(&self) -> &ProgramIdentity {
        &self.program
    }

    /// The required input, if the caller required one.
    pub const fn input(&self) -> Option<&InputIdentity> {
        self.input.as_ref()
    }

    /// The required output, if the caller required one.
    pub const fn output(&self) -> Option<&OutputIdentity> {
        self.output.as_ref()
    }

    /// The required exit code, if the caller required one.
    pub const fn exit_code(&self) -> Option<u32> {
        self.exit_code
    }

    /// Everything this expectation requires a verifier to check.
    pub fn required_checks(&self) -> Vec<RequiredCheck> {
        let mut checks = alloc::vec![RequiredCheck::Program];
        if self.input.is_some() {
            checks.push(RequiredCheck::Input);
        }
        if self.output.is_some() {
            checks.push(RequiredCheck::Output);
        }
        if self.exit_code.is_some() {
            checks.push(RequiredCheck::ExitCode);
        }
        checks
    }
}

/// What a verification ACTUALLY checked -- or what a backend is capable
/// of checking.
///
/// Four independent facts, deliberately not reducible to one. There is
/// no `is_complete() -> bool` and no `From<VerificationCoverage> for
/// bool`, because either would restore exactly the collapse this type
/// exists to prevent.
///
/// In a [`VerificationResult::Failed`], coverage means EXAMINED against
/// the expectation -- the failure cause names what mismatched. In a
/// [`VerificationResult::Verified`], examined and matched coincide.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct VerificationCoverage {
    /// The proved execution was checked to be of the expected program.
    pub program_checked: bool,
    /// The proved execution was checked to have run on the expected input.
    pub input_checked: bool,
    /// The proved execution was checked to have produced the expected output.
    pub output_checked: bool,
    /// The proved execution was checked to have ended with the expected exit code.
    pub exit_code_checked: bool,
}

impl VerificationCoverage {
    /// Nothing was checked. The only safe starting point, and the
    /// capability of any backend that cannot verify anything.
    pub const NONE: Self = Self {
        program_checked: false,
        input_checked: false,
        output_checked: false,
        exit_code_checked: false,
    };

    /// All four were checked.
    ///
    /// Named so that "complete" has to be written out by whoever claims
    /// it, and so tests can state the distinction from a partial coverage
    /// explicitly.
    pub const COMPLETE: Self = Self {
        program_checked: true,
        input_checked: true,
        output_checked: true,
        exit_code_checked: true,
    };

    /// Whether this coverage includes one particular check.
    pub const fn includes(&self, check: RequiredCheck) -> bool {
        match check {
            RequiredCheck::Program => self.program_checked,
            RequiredCheck::Input => self.input_checked,
            RequiredCheck::Output => self.output_checked,
            RequiredCheck::ExitCode => self.exit_code_checked,
        }
    }

    /// Whether every check this coverage claims is also claimed by
    /// `limit`. Used by the sealed entry point to refuse an adapter
    /// whose reported coverage exceeds its own declared capabilities.
    pub const fn within(&self, limit: &Self) -> bool {
        (!self.program_checked || limit.program_checked)
            && (!self.input_checked || limit.input_checked)
            && (!self.output_checked || limit.output_checked)
            && (!self.exit_code_checked || limit.exit_code_checked)
    }

    /// Which of `expectation`'s required checks this coverage does NOT
    /// include. Empty means the expectation is fully covered.
    pub fn missing(&self, expectation: &Expectation) -> Vec<RequiredCheck> {
        expectation
            .required_checks()
            .into_iter()
            .filter(|check| !self.includes(*check))
            .collect()
    }
}

impl Default for VerificationCoverage {
    /// [`VerificationCoverage::NONE`]. A default that assumed anything
    /// had been checked would be a fabricated warrant with a derive
    /// macro in front of it.
    fn default() -> Self {
        Self::NONE
    }
}

/// Why a verification failed.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum VerificationFailure {
    /// The proof is not about the expected program.
    ProgramMismatch,
    /// The proved execution did not run on the expected input.
    InputMismatch,
    /// The proved execution did not produce the expected output.
    OutputMismatch,
    /// The proved execution did not end with the expected exit code.
    ExitCodeMismatch,
    /// The proof itself did not verify.
    InvalidProof,
    /// The proof was produced by a version this verifier cannot check.
    ///
    /// Not an edge case: SP1's own verifier hard-fails on version
    /// mismatch (Phase 126 §8). A proof is verifiable by a compatible
    /// verifier, not forever.
    VersionMismatch {
        /// The version this verifier can check.
        expected: BackendId,
        /// The version the proof was produced under.
        found: BackendId,
    },
    /// The proof bytes could not be interpreted by this backend.
    Malformed,
    /// The proof does not prove the claimed statement, and this backend
    /// cannot attribute the mismatch to a single dimension.
    ///
    /// Added by Stage 3, from reading the Nexus verifier's source: a
    /// CONFIRM-style verifier (`verify_expected` reconstructs the whole
    /// expected execution view and checks the proof against it in one
    /// aggregate act) answers "is THIS TOTAL statement proven?" with one
    /// bit. When the answer is no, it cannot say whether input, output
    /// or exit code was the wrong part -- unlike an EXTRACT-style
    /// verifier (SP1), which reads the committed statement out of the
    /// proof and can name the mismatched dimension. Reporting a
    /// specific `InputMismatch` a confirm-style backend cannot actually
    /// attribute would be manufacturing precision; this variant is the
    /// honest alternative.
    StatementMismatch,
    /// The adapter's reported coverage broke its own contract: it
    /// claimed a check outside its declared capabilities, or accepted
    /// while covering less than the expectation required.
    ///
    /// Added by Phase 128, whose second probe demonstrated exactly this
    /// inflation passing through the Phase 127 entry point unexamined.
    /// The substrate cannot distinguish adapter dishonesty from an
    /// adapter bug, so it refuses both identically rather than
    /// forwarding either as a success.
    AdapterContractViolation {
        /// The coverage the adapter claimed.
        claimed: VerificationCoverage,
        /// The capabilities the adapter itself declared.
        capabilities: VerificationCoverage,
    },
}

/// What an adapter reports back from its backend-specific check.
///
/// Deliberately NOT a [`VerificationResult`]. Phase 128's first probe
/// showed that letting adapters construct the final result lets them
/// omit or mis-attach the statement it answers; its second probe showed
/// they can inflate coverage. So the adapter reports only what its
/// backend concluded, and the sealed entry point assembles the result --
/// embedding the expectation verbatim and computing the proof identity
/// from the artifact actually examined. Structurally, an adapter can no
/// longer detach a warrant from its claim or name a different proof.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum AdapterVerdict {
    /// The backend's verifier accepted, having examined `coverage`.
    Accept {
        /// What the backend actually checked.
        coverage: VerificationCoverage,
    },
    /// The backend's verifier rejected (or could not interpret the
    /// artifact), having examined `coverage` before stopping.
    Reject {
        /// What was examined before the failure was reached.
        coverage: VerificationCoverage,
        /// Why it rejected.
        failure: VerificationFailure,
    },
    /// The backend cannot answer THIS SHAPE of question, and did not try.
    ///
    /// Added by Stage 3. Capability screening handles the caller asking
    /// MORE than a backend can check; a confirm-style backend (Nexus)
    /// has the inverse constraint -- it can only verify a TOTAL
    /// statement, so an expectation that OMITS input, output or exit
    /// code leaves it nothing to reconstruct and confirm. `missing`
    /// names the omitted-but-mandatory checks; the sealed entry point
    /// maps this to [`VerificationResult::Unsupported`], so an
    /// unanswerable question stays visibly unanswered instead of
    /// becoming a weaker success.
    Decline {
        /// The checks the expectation omitted but this backend requires.
        missing: Vec<RequiredCheck>,
    },
}

/// The outcome of asking a backend to verify a proof against an
/// expectation.
///
/// Every variant names the [`Expectation`] it answered and carries
/// coverage. A result is therefore self-describing: separated from its
/// call site -- stored, logged, forwarded -- it still says exactly which
/// statement it warrants, which Phase 128 proved the Phase 127 shape did
/// not.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum VerificationResult {
    /// The proof verified, and covered everything the expectation
    /// required.
    ///
    /// `coverage` is still reported and is still not necessarily
    /// [`VerificationCoverage::COMPLETE`] -- it is complete with respect
    /// to what was ASKED. A caller that asked only about the program
    /// gets a `Verified` whose `input_checked` is false, and that is
    /// correct and must stay visible.
    Verified {
        /// The statement this result answers.
        expectation: Expectation,
        /// What was actually checked.
        coverage: VerificationCoverage,
        /// The proof that was checked, identified from the artifact the
        /// entry point actually examined.
        proof: ProofIdentity,
        /// The backend that checked it, and at what version.
        backend: BackendId,
    },
    /// The proof did not verify.
    Failed {
        /// The statement this result answers.
        expectation: Expectation,
        /// What was examined before the failure was reached.
        coverage: VerificationCoverage,
        /// Why it failed.
        failure: VerificationFailure,
        /// The backend that checked it.
        backend: BackendId,
    },
    /// The backend cannot check what was required, and did not try.
    ///
    /// This is the variant that stops an uncheckable requirement from
    /// silently becoming a success. An SP1-shaped backend asked to
    /// confirm an input lands here -- not in `Verified` with
    /// `input_checked: false`.
    Unsupported {
        /// The statement that was asked.
        expectation: Expectation,
        /// What this backend can check at all.
        capabilities: VerificationCoverage,
        /// The checks standing between the question and an answer:
        /// required-but-uncoverable (screened by the entry point), or --
        /// since Stage 3 -- omitted-but-mandatory for a confirm-style
        /// backend that can only verify a total statement.
        missing: Vec<RequiredCheck>,
        /// The backend that declined.
        backend: BackendId,
    },
}

/// A proving backend that can check a proof against an expectation.
///
/// Adapters implement [`backend`](ProofBackend::backend),
/// [`capabilities`](ProofBackend::capabilities) and
/// [`verify_supported`](ProofBackend::verify_supported), and nothing
/// more. Note what is NOT here: no serialization, no program-commitment
/// accessor, no proving, and -- since Phase 128 -- no authority to
/// construct the final [`VerificationResult`]. Phase 126 §10 found the
/// former cannot be shared; Phase 128 found the latter cannot be
/// entrusted.
pub trait ProofBackend {
    /// This backend's name and version.
    fn backend(&self) -> &BackendId;

    /// What this backend is capable of checking, at all, ever.
    ///
    /// Per Phase 126 this is genuinely different per backend, and an
    /// honest implementation says so:
    ///
    /// ```text
    /// SP1        input_checked: false   (SP1Stdin is never committed to)
    /// RISC Zero  input_checked: false   (Input is uninhabited; input_digest
    ///                                    is host-declared and must be zero)
    /// Nexus      input_checked: true    (verify_expected binds the input)
    /// ```
    ///
    /// This declaration is TRUSTED, not verified -- but it is no longer
    /// unaccountable: the entry point refuses any result whose claimed
    /// coverage exceeds it, so an over-claim here is at least confined
    /// to what was declared in one auditable place.
    fn capabilities(&self) -> VerificationCoverage;

    /// The backend-specific check. Implementors write THIS.
    ///
    /// Called only for expectations this backend's declared
    /// [`capabilities`](ProofBackend::capabilities) already cover, so an
    /// implementation never has to decide what to do about a requirement
    /// it cannot meet -- it will not be asked. It reports an
    /// [`AdapterVerdict`], never a [`VerificationResult`]: assembly of
    /// the result is the sealed entry point's job.
    fn verify_supported(
        &self,
        artifact: &ProofArtifact,
        expectation: &Expectation,
    ) -> AdapterVerdict;

    /// The entry point. Callers call THIS.
    ///
    /// Three structural guarantees, none of which depend on the adapter
    /// behaving:
    ///
    /// 1. An expectation the declared capabilities cannot cover never
    ///    reaches the adapter and returns
    ///    [`VerificationResult::Unsupported`] -- an uncheckable
    ///    requirement cannot become a success by omission.
    /// 2. The result embeds the expectation VERBATIM and identifies the
    ///    proof from the artifact actually examined -- the warrant
    ///    cannot detach from its claim (Phase 128, probe 1).
    /// 3. Claimed coverage outside the declared capabilities, or an
    ///    acceptance covering less than the expectation requires, is
    ///    refused as
    ///    [`VerificationFailure::AdapterContractViolation`] -- coverage
    ///    cannot inflate (Phase 128, probe 2).
    fn verify(&self, artifact: &ProofArtifact, expectation: &Expectation) -> VerificationResult {
        let capabilities = self.capabilities();
        let missing = capabilities.missing(expectation);
        if !missing.is_empty() {
            return VerificationResult::Unsupported {
                expectation: expectation.clone(),
                capabilities,
                missing,
                backend: self.backend().clone(),
            };
        }
        match self.verify_supported(artifact, expectation) {
            AdapterVerdict::Accept { coverage } => {
                if !coverage.within(&capabilities) || !coverage.missing(expectation).is_empty() {
                    return VerificationResult::Failed {
                        expectation: expectation.clone(),
                        coverage: VerificationCoverage::NONE,
                        failure: VerificationFailure::AdapterContractViolation {
                            claimed: coverage,
                            capabilities,
                        },
                        backend: self.backend().clone(),
                    };
                }
                VerificationResult::Verified {
                    expectation: expectation.clone(),
                    coverage,
                    proof: artifact.identity(),
                    backend: self.backend().clone(),
                }
            }
            AdapterVerdict::Decline { missing } => VerificationResult::Unsupported {
                expectation: expectation.clone(),
                capabilities,
                missing,
                backend: self.backend().clone(),
            },
            AdapterVerdict::Reject { coverage, failure } => {
                if !coverage.within(&capabilities) {
                    return VerificationResult::Failed {
                        expectation: expectation.clone(),
                        coverage: VerificationCoverage::NONE,
                        failure: VerificationFailure::AdapterContractViolation {
                            claimed: coverage,
                            capabilities,
                        },
                        backend: self.backend().clone(),
                    };
                }
                VerificationResult::Failed {
                    expectation: expectation.clone(),
                    coverage,
                    failure,
                    backend: self.backend().clone(),
                }
            }
        }
    }
}

/// A verification that SUCCEEDED, as a value: the statement, what was
/// checked, which proof, which backend.
///
/// # A computational object, never an Evidence object
///
/// `VerifiedExecution` lives and dies on the execution side of the
/// architecture. It is not admissible to any pool, carries no scientific
/// claim, and -- stated as many times as it takes -- DOES NOT establish
/// that any input was physically measured: a fabricated value is
/// computed, and proved, faithfully (Phase 111b, unchanged by
/// cryptography).
///
/// # Why it can only be built from a result
///
/// The sole constructor takes a [`VerificationResult`] and yields `Some`
/// exactly for [`VerificationResult::Verified`]. `Failed` is `None`.
/// `Unsupported` is `None`. There is no field-wise constructor, so
/// "verified = false" is UNREPRESENTABLE here -- the type either exists,
/// carrying its statement, or there is nothing. A caller who wants to
/// gate work on verification holds an `Option<VerifiedExecution>` whose
/// `None` arm cannot be quietly treated as a weaker success.
///
/// (A caller determined to lie can still hand-build a fake `Verified`
/// result and wrap it; the sealed entry point is the honest path, and
/// this type makes the honest path the easy one, not the only
/// conceivable one.)
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct VerifiedExecution {
    expectation: Expectation,
    coverage: VerificationCoverage,
    proof: ProofIdentity,
    backend: BackendId,
}

impl VerifiedExecution {
    /// `Some` if and only if `result` is [`VerificationResult::Verified`].
    pub fn from_result(result: &VerificationResult) -> Option<Self> {
        match result {
            VerificationResult::Verified {
                expectation,
                coverage,
                proof,
                backend,
            } => Some(Self {
                expectation: expectation.clone(),
                coverage: *coverage,
                proof: *proof,
                backend: backend.clone(),
            }),
            VerificationResult::Failed { .. } | VerificationResult::Unsupported { .. } => None,
        }
    }

    /// The statement that was verified.
    pub const fn expectation(&self) -> &Expectation {
        &self.expectation
    }

    /// What was actually checked -- complete with respect to what was
    /// ASKED, and still not necessarily [`VerificationCoverage::COMPLETE`].
    pub const fn coverage(&self) -> &VerificationCoverage {
        &self.coverage
    }

    /// The proof that was checked.
    pub const fn proof(&self) -> &ProofIdentity {
        &self.proof
    }

    /// The backend that checked it, and at what version.
    pub const fn backend(&self) -> &BackendId {
        &self.backend
    }
}
