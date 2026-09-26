//! The SP1 adapter: the first backend for which `Verified` is EARNED.
//!
//! Implements `execution_core::ProofBackend` over the SP1 fork's CPU
//! prover/verifier for ONE REGISTERED GUEST AT A TIME -- any guest that
//! follows the `ste.sp1.kernel-io.v1` public-values layout (stage 4
//! generalization: the layout was never pairwise-specific; the pairwise
//! and heat-diffusion guests both carry it, and the adapter is
//! constructed with whichever ELF + descriptor binding the caller
//! registers).
//!
//! # What a verified proof from this adapter establishes
//!
//! Assuming SP1 circuit soundness at the verifier's version:
//!
//!   1. The RISC-V program whose verifying key this adapter holds
//!      executed under SP1 semantics.                         [program*]
//!   2. That execution READ input bytes whose canonical commitment
//!      (SHA-256 under `scout.execution.input.v1`, computed INSIDE the
//!      proved execution by the same `execution-commitment` crate the
//!      host uses) is the one in the public values.           [input]
//!   3. It produced output bytes whose canonical commitment is the one
//!      in the public values, or halted with the committed fault code
//!      and NO output.                                        [output]
//!   4. It ended with the committed exit code.                [exit]
//!
//! [program*] carries one declared link, stated rather than hidden: the
//! proof binds the GUEST ELF (via its verifying key). The claim that
//! this ELF implements `PAIRWISE_ENERGY_DESCRIPTOR`'s semantics is a
//! BINDING registered at setup -- made credible by both substrates
//! compiling the identical `execution-kernel` function, and checked
//! empirically every proved run (native output must equal proved
//! output), but not itself proven. An `Expectation` naming any other
//! program identity is rejected as `ProgramMismatch`.
//!
//! # What it does NOT establish
//!
//! That the input corresponds to any physical event. A fabricated value
//! is computed -- and proved -- faithfully. Nothing produced here is
//! Evidence, nothing here touches the EvidencePool, and no field in any
//! type of this crate asserts measurement.
//!
//! # No mock path
//!
//! This adapter constructs the CPU prover explicitly. There is no code
//! path to SP1's mock prover from here: a `Verified` from this crate is
//! backed by a real proof or it does not exist.

use execution_core::{
    AdapterVerdict, BackendId, Expectation, ProgramIdentity, ProofArtifact, ProofBackend,
    VerificationCoverage, VerificationFailure,
};
use sp1_sdk::blocking::{CpuProver, LightProver, ProveRequest, Prover, ProverClient};
use sp1_sdk::{
    Elf, HashableKey, ProvingKey, SP1ProofWithPublicValues, SP1ProvingKey, SP1Stdin,
    SP1VerificationError, SP1VerifyingKey,
};

/// The bounded exact affine profile and its profile-specific SP1 convention.
pub mod affine;

/// The verifier machinery behind the backend -- either the full CPU
/// prover node (can prove and verify) or the SDK's `LightProver`
/// ("only executes and verifies but does not generate proofs"), which
/// is what a persisted verification artifact reconstructs. Both verify
/// through the SAME `verify_proof` path in the SDK; the light node
/// simply never built the proving machinery.
enum Sp1Client {
    Full(CpuProver),
    Light(LightProver),
}

impl Sp1Client {
    fn verify(
        &self,
        proof: &SP1ProofWithPublicValues,
        vk: &SP1VerifyingKey,
    ) -> Result<(), SP1VerificationError> {
        match self {
            Sp1Client::Full(client) => client.verify(proof, vk, None),
            Sp1Client::Light(client) => client.verify(proof, vk, None),
        }
    }
}

/// The public-values layout tag. Must match the guest's constant.
pub const SP1_IO_CONVENTION_TAG: &[u8] = b"ste.sp1.kernel-io.v1";

/// What the guest committed, parsed from the public values.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommittedStatement {
    /// The guest-computed canonical input commitment (32 bytes hex).
    pub input_commitment_hex: String,
    /// The guest-computed canonical output commitment; `None` when the
    /// guest halted -- absence is a marker byte, never a zeroed digest.
    pub output_commitment_hex: Option<String>,
    /// The committed exit code (0, or the kernel fault code on halt).
    pub exit_code: u32,
}

/// Parse the `ste.sp1.pairwise-io.v1` public-values layout, strictly.
///
/// Anything off -- wrong tag, wrong marker, wrong length -- is `None`;
/// the caller reports `Malformed`. A layout that "almost parses" binds
/// nothing.
pub fn parse_committed_statement(public_values: &[u8]) -> Option<CommittedStatement> {
    let rest = public_values.strip_prefix(SP1_IO_CONVENTION_TAG)?;
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

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The SP1 backend for a registered guest.
///
/// STE stage 10: the backend can be constructed two ways --
/// [`Sp1KernelBackend::setup`] (full proving-key generation; can prove
/// AND verify) or [`Sp1KernelBackend::from_verification_artifact`]
/// (verify-only, from the persisted verifying key; `prove` refuses).
/// Both paths verify through the identical sealed `ProofBackend`
/// machinery -- the artifact reuses verifier SETUP, never a verdict.
pub struct Sp1KernelBackend {
    client: Sp1Client,
    vk: SP1VerifyingKey,
    /// Present only when constructed via `setup`; proving requires it,
    /// verification never touches it.
    pk: Option<SP1ProvingKey>,
    backend_id: BackendId,
    /// The descriptor-level program identity this guest is REGISTERED as
    /// implementing -- the declared binding described in the crate docs.
    program_binding: ProgramIdentity,
}

/// The persisted verification artifact's header line. The format is
/// deliberately self-identifying and fail-closed:
///
/// ```text
/// ste-sp1-verification-artifact v1
/// backend sp1-cpu <sdk-version>
/// program <64-hex ProgramIdentity of the registered descriptor>
/// elf_sha256 <64-hex of the reproducible guest ELF>
/// vkey_hash <SP1 bytes32 commitment of the verifying key>
/// payload <byte length of the bincode SP1VerifyingKey>
/// <raw payload bytes>
/// ```
///
/// Loading re-derives `vkey_hash` from the deserialized key and refuses
/// on ANY disagreement (header vs payload, backend version vs the
/// running client, program binding vs the caller's descriptor). The
/// artifact carries verifier MACHINERY -- there is no field in it that
/// could hold a verdict.
pub const SP1_VERIFICATION_ARTIFACT_HEADER: &str = "ste-sp1-verification-artifact v1";

impl Sp1KernelBackend {
    /// Set up the CPU prover for `elf_bytes`, registering the binding to
    /// `program_binding` (the canonical descriptor's ProgramIdentity).
    pub fn setup(elf_bytes: Vec<u8>, program_binding: ProgramIdentity) -> anyhow::Result<Self> {
        let client = ProverClient::builder().cpu().build();
        let pk = client.setup(Elf::from(elf_bytes))?;
        let backend_id = BackendId::new("sp1-cpu", client.version());
        Ok(Self {
            vk: pk.verifying_key().clone(),
            pk: Some(pk),
            client: Sp1Client::Full(client),
            backend_id,
            program_binding,
        })
    }

    /// Serialize this backend's verification artifact: the header
    /// described at [`SP1_VERIFICATION_ARTIFACT_HEADER`] plus the
    /// bincode `SP1VerifyingKey`. `elf_sha256_hex` records which
    /// reproducible guest build the key was derived from.
    pub fn export_verification_artifact(&self, elf_sha256_hex: &str) -> anyhow::Result<Vec<u8>> {
        let payload = bincode::serialize(&self.vk)?;
        let mut out = format!(
            "{}\nbackend {} {}\nprogram {}\nelf_sha256 {}\nvkey_hash {}\npayload {}\n",
            SP1_VERIFICATION_ARTIFACT_HEADER,
            self.backend_id.name,
            self.backend_id.version,
            self.program_binding.to_hex(),
            elf_sha256_hex,
            self.vkey_hash(),
            payload.len(),
        )
        .into_bytes();
        out.extend_from_slice(&payload);
        Ok(out)
    }

    /// Construct a VERIFY-ONLY backend from a persisted verification
    /// artifact. Fail-closed on every mismatch: malformed header, wrong
    /// backend name, SDK version disagreement, payload length or
    /// deserialization failure, a `vkey_hash` that does not re-derive
    /// from the payload, or a program binding that disagrees with
    /// `expected_binding` (the descriptor the caller registered).
    pub fn from_verification_artifact(
        artifact: &[u8],
        expected_binding: ProgramIdentity,
    ) -> anyhow::Result<(Self, String)> {
        let header_end = artifact
            .windows(9)
            .position(|w| w == b"\npayload ")
            .ok_or_else(|| anyhow::anyhow!("artifact: missing payload marker"))?;
        let header = std::str::from_utf8(&artifact[..header_end])
            .map_err(|_| anyhow::anyhow!("artifact: header is not UTF-8"))?;
        let rest = &artifact[header_end + 1..];
        let line_end = rest
            .iter()
            .position(|&b| b == b'\n')
            .ok_or_else(|| anyhow::anyhow!("artifact: unterminated payload line"))?;
        let payload_line = std::str::from_utf8(&rest[..line_end]).unwrap_or("");
        let declared_len: usize = payload_line
            .strip_prefix("payload ")
            .and_then(|n| n.parse().ok())
            .ok_or_else(|| anyhow::anyhow!("artifact: bad payload length line"))?;
        let payload = &rest[line_end + 1..];
        if payload.len() != declared_len {
            anyhow::bail!(
                "artifact: payload is {} bytes, header declares {}",
                payload.len(),
                declared_len
            );
        }

        let mut fields = std::collections::HashMap::new();
        let mut lines = header.lines();
        if lines.next() != Some(SP1_VERIFICATION_ARTIFACT_HEADER) {
            anyhow::bail!("artifact: not an {SP1_VERIFICATION_ARTIFACT_HEADER}");
        }
        for line in lines {
            if let Some((key, value)) = line.split_once(' ') {
                fields.insert(key.to_string(), value.to_string());
            }
        }

        let client = LightProver::new();
        let backend_id = BackendId::new("sp1-cpu", client.version());
        let declared_backend = fields.get("backend").cloned().unwrap_or_default();
        let expected_backend = format!("{} {}", backend_id.name, backend_id.version);
        if declared_backend != expected_backend {
            anyhow::bail!(
                "artifact: built for backend {declared_backend:?}, this verifier is {expected_backend:?}"
            );
        }
        if fields.get("program").map(String::as_str) != Some(&expected_binding.to_hex()[..]) {
            anyhow::bail!("artifact: program binding disagrees with the registered descriptor");
        }

        let vk: SP1VerifyingKey = bincode::deserialize(payload)
            .map_err(|e| anyhow::anyhow!("artifact: verifying key does not deserialize: {e}"))?;
        let rederived = vk.vk.bytes32();
        if fields.get("vkey_hash") != Some(&rederived) {
            anyhow::bail!("artifact: vkey_hash does not re-derive from the payload");
        }
        let elf_sha = fields
            .get("elf_sha256")
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("artifact: missing elf_sha256"))?;

        Ok((
            Self {
                client: Sp1Client::Light(client),
                vk,
                pk: None,
                backend_id,
                program_binding: expected_binding,
            },
            elf_sha,
        ))
    }

    /// The verifying-key hash (`bytes32`) -- SP1's native program
    /// commitment for the guest ELF, reported BESIDE our identity and
    /// never as it.
    pub fn vkey_hash(&self) -> String {
        self.vk.vk.bytes32()
    }

    /// Execute + prove (core mode) the guest over `input`, then verify
    /// the fresh proof immediately. Returns the serialized proof bundle
    /// and the statement the guest committed. Refuses on a verify-only
    /// backend: a verification artifact can never manufacture a proof.
    pub fn prove(&self, input: &[u8]) -> anyhow::Result<(Vec<u8>, CommittedStatement)> {
        let (Sp1Client::Full(client), Some(pk)) = (&self.client, self.pk.as_ref()) else {
            anyhow::bail!("this backend was built from a verification artifact; it cannot prove");
        };
        let mut stdin = SP1Stdin::new();
        stdin.write_vec(input.to_vec());
        let proof = client.prove(pk, stdin).core().run()?;
        // Verify immediately: a proof this adapter cannot verify is not
        // handed to anyone.
        self.client.verify(&proof, &self.vk)?;
        let statement = parse_committed_statement(proof.public_values.as_slice())
            .ok_or_else(|| anyhow::anyhow!("guest committed an unparseable statement"))?;
        Ok((bincode::serialize(&proof)?, statement))
    }

    /// Prove one already checked `affine-d256.v1` statement and immediately
    /// verify the resulting SP1 proof.  The generic kernel convention remains
    /// untouched; this method selects the profile-specific public-values
    /// parser and refuses if the guest commits anything other than the exact
    /// checked statement.
    pub fn prove_affine(
        &self,
        statement: &[u8],
    ) -> anyhow::Result<(Vec<u8>, affine::AffinePublicValues)> {
        if self.program_binding != ProgramIdentity::of(affine::DESCRIPTOR) {
            anyhow::bail!("SP1 backend is not bound to the registered affine descriptor");
        }
        let checked = affine::check_statement(statement)
            .map_err(|error| anyhow::anyhow!("affine statement refused: {error}"))?;
        let (Sp1Client::Full(client), Some(pk)) = (&self.client, self.pk.as_ref()) else {
            anyhow::bail!("this backend was built from a verification artifact; it cannot prove");
        };
        let mut stdin = SP1Stdin::new();
        stdin.write_vec(statement.to_vec());
        let proof = client.prove(pk, stdin).core().run()?;
        self.client.verify(&proof, &self.vk)?;
        let public = affine::parse_public_values(proof.public_values.as_slice())
            .map_err(|error| anyhow::anyhow!("guest committed malformed affine values: {error}"))?;
        if !public.matches(&checked) {
            anyhow::bail!("guest affine public values do not match checked statement");
        }
        Ok((bincode::serialize(&proof)?, public))
    }

    /// Verify a serialized exact-affine proof against the exact canonical
    /// statement.  The proof's public values, operation/profile revision,
    /// fixed bounds, dimensions, input commitment, and output commitment are
    /// all checked after SP1's cryptographic verification.
    pub fn verify_affine(
        &self,
        proof_bytes: &[u8],
        statement: &[u8],
    ) -> anyhow::Result<affine::AffinePublicValues> {
        if self.program_binding != ProgramIdentity::of(affine::DESCRIPTOR) {
            anyhow::bail!("SP1 backend is not bound to the registered affine descriptor");
        }
        let checked = affine::check_statement(statement)
            .map_err(|error| anyhow::anyhow!("affine statement refused: {error}"))?;
        let proof: SP1ProofWithPublicValues = bincode::deserialize(proof_bytes)?;
        self.client.verify(&proof, &self.vk)?;
        let public = affine::parse_public_values(proof.public_values.as_slice())
            .map_err(|error| anyhow::anyhow!("guest committed malformed affine values: {error}"))?;
        if !public.matches(&checked) {
            anyhow::bail!("affine proof public values do not match checked statement");
        }
        Ok(public)
    }
}

impl ProofBackend for Sp1KernelBackend {
    fn backend(&self) -> &BackendId {
        &self.backend_id
    }

    /// All four -- and each is a claim with a mechanism, not an
    /// aspiration: program via the verifying key (plus the declared
    /// descriptor binding, see crate docs), input via the guest
    /// convention (the recon's `input_checked: false` for SP1 was about
    /// the SUBSTRATE; the guest convention is exactly the construction
    /// Phase 126 identified as the only honest upgrade), output and exit
    /// code via the committed public values.
    fn capabilities(&self) -> VerificationCoverage {
        VerificationCoverage::COMPLETE
    }

    fn verify_supported(
        &self,
        artifact: &ProofArtifact,
        expectation: &Expectation,
    ) -> AdapterVerdict {
        let mut coverage = VerificationCoverage::NONE;

        let Ok(proof) = bincode::deserialize::<SP1ProofWithPublicValues>(artifact.bytes()) else {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::Malformed,
            };
        };

        // The cryptographic check: the SDK's real verifier, which also
        // hard-fails on version mismatch (Phase 126 §8).
        if let Err(error) = self.client.verify(&proof, &self.vk) {
            let text = format!("{error:?}");
            let failure = if text.contains("VersionMismatch") {
                VerificationFailure::VersionMismatch {
                    expected: self.backend_id.clone(),
                    found: BackendId::new("sp1-cpu", proof.sp1_version.clone()),
                }
            } else {
                VerificationFailure::InvalidProof
            };
            return AdapterVerdict::Reject { coverage, failure };
        }

        let Some(statement) = parse_committed_statement(proof.public_values.as_slice()) else {
            return AdapterVerdict::Reject {
                coverage,
                failure: VerificationFailure::Malformed,
            };
        };

        // Program: the proof is bound to OUR verifying key (the SDK
        // verify above used self.pk); what remains is whether the caller
        // asked about the program this guest is registered as.
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
                // A halted execution committed NO output; it cannot
                // match any expected output, and saying so is the
                // mismatch, not a fabricated comparison against zeros.
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

        // Coverage reports what was examined: exactly the required set.
        debug_assert!(coverage.missing(expectation).is_empty());
        AdapterVerdict::Accept { coverage }
    }
}
