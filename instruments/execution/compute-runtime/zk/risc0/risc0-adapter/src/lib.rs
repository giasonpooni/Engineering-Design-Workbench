//! The RISC Zero adapter: the third independent implementer.
//!
//! An EXTRACT-style verifier like SP1: `Receipt::verify(image_id)`
//! cryptographically binds the journal to the program, and the journal
//! carries the guest's committed statement (`ste.r0.kernel-io.v1`
//! layout), so the adapter reads the statement out of the artifact and
//! compares per field -- attributable failures, unlike Nexus's
//! confirm-style aggregate.
//!
//! Native program commitment: the ImageID, a pure function of the ELF
//! (`compute_image_id`) -- reported BESIDE our descriptor identity,
//! never as it. The descriptor binding is registered, exactly as for
//! the other two backends, and made checkable by the stage-5
//! reproducible-build machinery.
//!
//! # No dev mode, structurally
//!
//! RISC Zero ships `RISC0_DEV_MODE`, which produces FakeReceipts "with
//! no cryptographic integrity, used only for development" (their words,
//! `receipt.rs:324`). This adapter refuses to construct if that
//! variable is set at all: a Verified from this crate is backed by a
//! real proof or the adapter does not exist.
//!
//! COMPUTATION != MEASUREMENT: unchanged, verbatim, forever.

use execution_core::{
    AdapterVerdict, BackendId, Expectation, ProgramIdentity, ProofArtifact, ProofBackend,
    VerificationCoverage, VerificationFailure,
};
use risc0_binfmt::ProgramBinary;
use risc0_zkos_v1compat::V1COMPAT_ELF;
use risc0_zkvm::{compute_image_id, default_prover, ExecutorEnv, Receipt};

/// The journal layout tag. Must match the guest's constant.
pub const R0_IO_CONVENTION_TAG: &[u8] = b"ste.r0.kernel-io.v1";

/// What the guest committed, parsed from the journal (identical shape
/// to the SP1 adapter's).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommittedStatement {
    /// Guest-computed canonical input commitment (hex).
    pub input_commitment_hex: String,
    /// Guest-computed canonical output commitment; `None` = fault.
    pub output_commitment_hex: Option<String>,
    /// The committed exit code.
    pub exit_code: u32,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Strictly parse the `ste.r0.kernel-io.v1` journal layout.
pub fn parse_committed_statement(journal: &[u8]) -> Option<CommittedStatement> {
    let rest = journal.strip_prefix(R0_IO_CONVENTION_TAG)?;
    let (input_commitment, rest) = rest.split_at_checked(32)?;
    let (marker, rest) = rest.split_first()?;
    match marker {
        0 => {
            let (output_commitment, rest) = rest.split_at_checked(32)?;
            let exit: [u8; 4] = rest.try_into().ok()?;
            Some(CommittedStatement {
                input_commitment_hex: hex(input_commitment),
                output_commitment_hex: Some(hex(output_commitment)),
                exit_code: u32::from_le_bytes(exit),
            })
        }
        1 => {
            let exit: [u8; 4] = rest.try_into().ok()?;
            Some(CommittedStatement {
                input_commitment_hex: hex(input_commitment),
                output_commitment_hex: None,
                exit_code: u32::from_le_bytes(exit),
            })
        }
        _ => None,
    }
}

/// The RISC Zero backend for STE kernel guests.
pub struct Risc0KernelBackend {
    elf: Vec<u8>,
    image_id: risc0_zkvm::sha::Digest,
    backend_id: BackendId,
    program_binding: ProgramIdentity,
}

impl Risc0KernelBackend {
    /// Load the guest ELF, derive its ImageID, register the binding.
    ///
    /// Refuses outright under `RISC0_DEV_MODE`: no code path from this
    /// crate may produce a warrant a FakeReceipt could satisfy.
    pub fn setup(elf: Vec<u8>, program_binding: ProgramIdentity) -> anyhow::Result<Self> {
        if std::env::var_os("RISC0_DEV_MODE").is_some() {
            anyhow::bail!(
                "RISC0_DEV_MODE is set; this adapter refuses to run at all under dev mode -- \
                 a FakeReceipt has no cryptographic integrity and must never back a Verified"
            );
        }
        // The prover and ImageID consume the COMBINED user+kernel
        // ProgramBinary, not the raw user ELF. The kernel is the fork's
        // v1compat ELF -- a build determinant pinned by the fork commit
        // the stage-5 recipe records; the reproducible artifact identity
        // stays the USER elf, and the combination here is deterministic.
        let elf = ProgramBinary::new(&elf, V1COMPAT_ELF).encode();
        let image_id =
            compute_image_id(&elf).map_err(|e| anyhow::anyhow!("computing image id: {e:?}"))?;
        Ok(Self {
            elf,
            image_id,
            backend_id: BackendId::new("risc0-cpu", risc0_zkvm::VERSION),
            program_binding,
        })
    }

    /// The ImageID -- RISC Zero's native program commitment, a pure
    /// function of the ELF. Reported beside our identity, never as it.
    pub fn image_id_hex(&self) -> String {
        hex(self.image_id.as_bytes())
    }

    /// Execute + prove the guest over `input`, verify the fresh receipt
    /// immediately, and return (serialized receipt, committed statement).
    pub fn prove(&self, input: &[u8]) -> anyhow::Result<(Vec<u8>, CommittedStatement)> {
        let env = ExecutorEnv::builder()
            .write(&input.to_vec())
            .map_err(|e| anyhow::anyhow!("writing input: {e:?}"))?
            .build()
            .map_err(|e| anyhow::anyhow!("building env: {e:?}"))?;
        let info = default_prover()
            .prove(env, &self.elf)
            .map_err(|e| anyhow::anyhow!("prove: {e:?}"))?;
        let receipt = info.receipt;
        receipt
            .verify(self.image_id)
            .map_err(|e| anyhow::anyhow!("fresh receipt failed verification: {e:?}"))?;
        let statement = parse_committed_statement(&receipt.journal.bytes)
            .ok_or_else(|| anyhow::anyhow!("guest committed an unparseable journal"))?;
        Ok((bincode::serialize(&receipt)?, statement))
    }
}

impl ProofBackend for Risc0KernelBackend {
    fn backend(&self) -> &BackendId {
        &self.backend_id
    }

    /// All four, extract-style: program via ImageID (plus the registered
    /// descriptor binding, checkable by rebuild since stage 5); input
    /// via the guest's in-circuit commitment; output and exit from the
    /// journal `Receipt::verify` binds.
    fn capabilities(&self) -> VerificationCoverage {
        VerificationCoverage::COMPLETE
    }

    fn verify_supported(
        &self,
        artifact: &ProofArtifact,
        expectation: &Expectation,
    ) -> AdapterVerdict {
        let mut coverage = VerificationCoverage::NONE;

        let Ok(receipt) = bincode::deserialize::<Receipt>(artifact.bytes()) else {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::Malformed,
            };
        };

        // The cryptographic check: seal + journal digest + image id.
        if receipt.verify(self.image_id).is_err() {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::InvalidProof,
            };
        }

        let Some(statement) = parse_committed_statement(&receipt.journal.bytes) else {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::Malformed,
            };
        };

        coverage.program_checked = true;
        if expectation.program() != &self.program_binding {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::ProgramMismatch,
            };
        }
        if let Some(expected_input) = expectation.input() {
            coverage.input_checked = true;
            if statement.input_commitment_hex != expected_input.to_hex() {
                return AdapterVerdict::Reject {
                    coverage,
                    failure: VerificationFailure::InputMismatch,
                };
            }
        }
        if let Some(expected_output) = expectation.output() {
            coverage.output_checked = true;
            match &statement.output_commitment_hex {
                Some(committed) if *committed == expected_output.to_hex() => {}
                _ => {
                    return AdapterVerdict::Reject {
                        coverage,
                        failure: VerificationFailure::OutputMismatch,
                    };
                }
            }
        }
        if let Some(expected_exit) = expectation.exit_code() {
            coverage.exit_code_checked = true;
            if statement.exit_code != expected_exit {
                return AdapterVerdict::Reject {
                    coverage,
                    failure: VerificationFailure::ExitCodeMismatch,
                };
            }
        }
        debug_assert!(coverage.missing(expectation).is_empty());
        AdapterVerdict::Accept { coverage }
    }
}
