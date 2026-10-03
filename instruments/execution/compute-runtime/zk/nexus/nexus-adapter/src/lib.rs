//! The Nexus adapter: the second independent implementer of the
//! verification contract.
//!
//! Same trait, same sealed entry point, same statement shape as the SP1
//! adapter -- over a completely different proving stack (Nexus's stwo
//! prover, RV32, standard nightly toolchain). What this crate exists to
//! demonstrate is that `VerifiedExecution` is a verified computational
//! fact, not an SP1 fact.
//!
//! # The two substrate-specific dimensions, found by reading source
//!
//! **Confirm vs extract.** SP1's verifier EXTRACTS the committed
//! statement from the proof's public values and compares per field.
//! Nexus's verifier (`Verifiable::verify_expected`, `sdk/src/traits.rs`)
//! can only CONFIRM: it reconstructs the whole expected execution view
//! -- public input bytes, exit code, public output bytes, the FULL ELF,
//! associated data -- and checks the proof against it in one aggregate
//! act. A Nexus proof does not carry a readable statement at all.
//! Consequences, both expressed through the shared vocabulary rather
//! than papered over:
//!
//!   - a partial expectation (program-only) is UNANSWERABLE here:
//!     `verify_supported` returns `AdapterVerdict::Decline` and the
//!     sealed entry point reports `Unsupported` (Stage 3 extension);
//!   - a failed confirmation cannot be attributed to input vs output vs
//!     exit: the honest failure is `StatementMismatch`, never a
//!     manufactured `InputMismatch`.
//!
//! **Program commitment.** Nexus has none (Phase 126 §5): the ELF is the
//! commitment, and the verifier requires it wholesale. This adapter
//! therefore HOLDS the ELF and registers the descriptor binding exactly
//! as the SP1 adapter registers its verifying key -- the declared
//! ELF-implements-descriptor link is the same class of claim as SP1's
//! vkey binding, and it is stated, not hidden.
//!
//! # No mock path
//!
//! `Stwo<Local>` is the real stwo prover. There is no mock prover in
//! this crate and no route to one.

use execution_core::{
    AdapterVerdict, BackendId, Expectation, ProgramIdentity, ProofArtifact, ProofBackend,
    RequiredCheck, VerificationCoverage, VerificationFailure,
};
use nexus_sdk::stwo::seq::{Proof, Stwo};
use nexus_sdk::{KnownExitCodes, Local, Prover, Verifiable, Viewable};

/// The statement layout tag: "STE1" as LE u32. Must match the guest.
pub const LAYOUT_STE1: u32 = u32::from_le_bytes(*b"STE1");

/// The statement the guest commits, as the postcard-encoded tuple both
/// guest and verifier construct:
/// `(LAYOUT_STE1, input_commitment, output_commitment: Option, exit_code)`.
/// `None` for the output commitment means the kernel faulted -- absence
/// is `Option::None`, never a zeroed digest.
pub type NexusStatement = (u32, [u8; 32], Option<[u8; 32]>, u32);

/// What the guest committed, in backend-neutral terms (mirrors the SP1
/// adapter's `CommittedStatement`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommittedStatement {
    /// The guest-computed canonical input commitment (hex).
    pub input_commitment_hex: String,
    /// The guest-computed canonical output commitment; `None` = fault.
    pub output_commitment_hex: Option<String>,
    /// The committed exit code.
    pub exit_code: u32,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The Nexus backend for the pairwise-energy guest.
pub struct NexusKernelBackend {
    elf: nexus_core::nvm::ElfFile,
    backend_id: BackendId,
    program_binding: ProgramIdentity,
}

impl NexusKernelBackend {
    /// Load the guest ELF and register the descriptor binding.
    ///
    /// `version` should name the fork revision (e.g. "0.3.6@f2ad126"):
    /// Nexus embeds the memory layout in each proof, and a proof is
    /// verifiable by a compatible verifier, not forever (Phase 126 §8).
    pub fn setup(
        elf_path: &std::path::Path,
        program_binding: ProgramIdentity,
        version: &str,
    ) -> anyhow::Result<Self> {
        let elf = nexus_core::nvm::ElfFile::from_path(elf_path)
            .map_err(|e| anyhow::anyhow!("loading guest ELF: {e:?}"))?;
        Ok(Self {
            elf,
            backend_id: BackendId::new("nexus-stwo", version),
            program_binding,
        })
    }

    /// Prove one execution of the guest over `input` (private tape),
    /// verify the fresh proof immediately, and return the serialized
    /// proof plus the statement the guest committed.
    pub fn prove(&self, input: &[u8]) -> anyhow::Result<(Vec<u8>, CommittedStatement)> {
        let prover: Stwo<Local> =
            Stwo::new(&self.elf).map_err(|e| anyhow::anyhow!("prover setup: {e:?}"))?;
        let (view, proof) = prover
            .prove_with_input::<Vec<u8>, ()>(&input.to_vec(), &())
            .map_err(|e| anyhow::anyhow!("prove: {e:?}"))?;

        let vm_exit = view
            .exit_code()
            .map_err(|e| anyhow::anyhow!("exit code: {e:?}"))?;
        if vm_exit != KnownExitCodes::ExitSuccess as u32 {
            anyhow::bail!("guest VM exited {vm_exit}, not success; no statement was committed");
        }
        let statement: NexusStatement = view
            .public_output::<NexusStatement>()
            .map_err(|e| anyhow::anyhow!("public output: {e:?}"))?;
        if statement.0 != LAYOUT_STE1 {
            anyhow::bail!(
                "guest committed an unrecognised statement layout {:#x}",
                statement.0
            );
        }

        // Verify immediately: a proof this adapter cannot verify is not
        // handed to anyone.
        proof
            .verify_expected::<(), NexusStatement>(
                &(),
                KnownExitCodes::ExitSuccess as u32,
                &statement,
                &self.elf,
                &[],
            )
            .map_err(|e| anyhow::anyhow!("fresh proof failed verification: {e:?}"))?;

        let committed = CommittedStatement {
            input_commitment_hex: hex(&statement.1),
            output_commitment_hex: statement.2.as_ref().map(|d| hex(d)),
            exit_code: statement.3,
        };
        Ok((bincode::serialize(&proof)?, committed))
    }
}

impl ProofBackend for NexusKernelBackend {
    fn backend(&self) -> &BackendId {
        &self.backend_id
    }

    /// All four, with mechanisms: program via the full ELF the verifier
    /// reconstructs execution from (plus the registered descriptor
    /// binding); input via the guest's in-circuit commitment; output and
    /// exit via the confirmed statement. The recon's `input_checked:
    /// true` for Nexus referred to its native public-input binding; this
    /// guest takes input on the PRIVATE tape and the binding both
    /// backends share is the in-circuit commitment -- the same mechanism
    /// as SP1, deliberately.
    fn capabilities(&self) -> VerificationCoverage {
        VerificationCoverage::COMPLETE
    }

    fn verify_supported(
        &self,
        artifact: &ProofArtifact,
        expectation: &Expectation,
    ) -> AdapterVerdict {
        // Confirm-style: a partial statement is unanswerable (see the
        // crate docs). Decline names what is missing; the sealed entry
        // point reports Unsupported.
        let mut missing = Vec::new();
        if expectation.input().is_none() {
            missing.push(RequiredCheck::Input);
        }
        if expectation.output().is_none() {
            missing.push(RequiredCheck::Output);
        }
        if expectation.exit_code().is_none() {
            missing.push(RequiredCheck::ExitCode);
        }
        if !missing.is_empty() {
            return AdapterVerdict::Decline { missing };
        }

        let mut coverage = VerificationCoverage::NONE;

        let Ok(proof) = bincode::deserialize::<Proof>(artifact.bytes()) else {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::Malformed,
            };
        };

        // The declared binding: is the caller even asking about the
        // program this ELF is registered as? Attributable, unlike the
        // aggregate check below.
        coverage.program_checked = true;
        if expectation.program() != &self.program_binding {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::ProgramMismatch,
            };
        }

        // Reconstruct the expected statement from the expectation --
        // possible precisely because the expectation is total.
        let expected: NexusStatement = (
            LAYOUT_STE1,
            *expectation
                .input()
                .expect("screened above")
                .commitment()
                .as_bytes(),
            Some(
                *expectation
                    .output()
                    .expect("screened above")
                    .commitment()
                    .as_bytes(),
            ),
            expectation.exit_code().expect("screened above"),
        );

        match proof.verify_expected::<(), NexusStatement>(
            &(),
            KnownExitCodes::ExitSuccess as u32,
            &expected,
            &self.elf,
            &[],
        ) {
            Ok(()) => {
                coverage.input_checked = true;
                coverage.output_checked = true;
                coverage.exit_code_checked = true;
                AdapterVerdict::Accept { coverage }
            }
            // One aggregate act confirmed nothing; attribution to a
            // single dimension is not available on this substrate.
            Err(_) => AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::StatementMismatch,
            },
        }
    }
}
