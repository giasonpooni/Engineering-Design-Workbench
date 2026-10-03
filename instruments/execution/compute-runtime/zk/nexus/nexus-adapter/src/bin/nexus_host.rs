//! nexus-host: the same CLI protocol as sp1-host, second implementer.
//!
//! Identical commands, identical result lines (`ste-host-result v1`), so
//! the Python driver (`execution/proving.py`) runs against either binary
//! unchanged -- the substrate-independence demonstration extends to the
//! process boundary. Differences surface only where the substrates
//! genuinely differ: `native_commitment` reports that Nexus has no
//! program digest (the ELF is the commitment), and failed verifications
//! report `StatementMismatch` where SP1 names a dimension.

use std::io::Write;

use execution_core::{Expectation, ProofArtifact, ProofBackend, VerificationResult};
use nexus_adapter::NexusKernelBackend;

fn from_hex(text: &str) -> Result<Vec<u8>, String> {
    if text.len() % 2 != 0 {
        return Err(format!("odd-length hex: {text:?}"));
    }
    (0..text.len())
        .step_by(2)
        .map(|at| u8::from_str_radix(&text[at..at + 2], 16).map_err(|e| e.to_string()))
        .collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if let Err(error) = run(&args) {
        eprintln!("nexus-host error: {error}");
        std::process::exit(2);
    }
}

const VERSION: &str = "0.3.6@f2ad126";

fn setup(elf_path: &str, descriptor_path: &str) -> Result<NexusKernelBackend, String> {
    let descriptor = std::fs::read(descriptor_path)
        .map_err(|e| format!("reading descriptor file {descriptor_path}: {e}"))?;
    let binding = execution_core::ProgramIdentity::of(&descriptor);
    NexusKernelBackend::setup(std::path::Path::new(elf_path), binding, VERSION)
        .map_err(|e| format!("setup: {e:?}"))
}

fn run(args: &[String]) -> Result<(), String> {
    match args.get(1).map(String::as_str) {
        Some("prove") => prove(args),
        Some("verify") => verify(args),
        other => Err(format!("unknown or missing command {other:?}")),
    }
}

fn prove(args: &[String]) -> Result<(), String> {
    let [_, _, elf_path, descriptor_path, input_hex, proof_out] = args else {
        return Err("usage: prove <elf> <descriptor-file> <input-hex> <proof-out>".into());
    };
    let backend = setup(elf_path, descriptor_path)?;
    let input = from_hex(input_hex)?;
    let (proof_bytes, statement) = backend.prove(&input).map_err(|e| format!("prove: {e:?}"))?;
    std::fs::write(proof_out, &proof_bytes).map_err(|e| format!("writing proof: {e}"))?;

    let mut out = String::new();
    out.push_str("ste-host-result v1\n");
    out.push_str("command prove\n");
    out.push_str(&format!(
        "backend {} {}\n",
        backend.backend().name,
        backend.backend().version
    ));
    // Nexus has no program digest: the ELF itself is the commitment
    // (Phase 126 §5), and pretending otherwise here would fabricate one.
    out.push_str("native_commitment elf\n");
    out.push_str(&format!(
        "input_commitment {}\n",
        statement.input_commitment_hex
    ));
    match &statement.output_commitment_hex {
        Some(output) => {
            out.push_str("guest_status completed\n");
            out.push_str(&format!("output_commitment {output}\n"));
        }
        None => out.push_str("guest_status halted\n"),
    }
    out.push_str(&format!("exit_code {}\n", statement.exit_code));
    out.push_str(&format!("proof_bytes {}\n", proof_bytes.len()));
    print!("{out}");
    std::io::stdout().flush().map_err(|e| e.to_string())
}

fn verify(args: &[String]) -> Result<(), String> {
    let [_, _, elf_path, descriptor_path, proof_in, expect_program, expect_input, expect_output, expect_exit] =
        args
    else {
        return Err(
            "usage: verify <elf> <descriptor-file> <proof-in> <registered|program-file> \
             <input-hex> <output-hex> <exit>"
                .into(),
        );
    };
    let backend = setup(elf_path, descriptor_path)?;
    let proof_bytes = std::fs::read(proof_in).map_err(|e| format!("reading proof: {e}"))?;
    let artifact = ProofArtifact::new(backend.backend().clone(), proof_bytes);

    let program = execution_core::ProgramIdentity::of(
        &std::fs::read(if expect_program == "registered" {
            descriptor_path.clone()
        } else {
            expect_program.clone()
        })
        .map_err(|e| format!("reading program preimage: {e}"))?,
    );
    let input_bytes = from_hex(expect_input)?;
    let output_bytes = from_hex(expect_output)?;
    let exit: u32 = expect_exit.parse().map_err(|e| format!("exit code: {e}"))?;

    let expectation = Expectation::of_program(program)
        .with_input(execution_core::InputIdentity::of(&input_bytes))
        .with_output(execution_core::OutputIdentity::of(&output_bytes))
        .with_exit_code(exit);

    let result = backend.verify(&artifact, &expectation);

    let mut out = String::new();
    out.push_str("ste-host-result v1\n");
    out.push_str("command verify\n");
    match &result {
        VerificationResult::Verified {
            coverage,
            proof,
            backend: by,
            ..
        } => {
            out.push_str("outcome verified\n");
            out.push_str(&format!(
                "coverage program={} input={} output={} exit_code={}\n",
                coverage.program_checked,
                coverage.input_checked,
                coverage.output_checked,
                coverage.exit_code_checked
            ));
            out.push_str(&format!("proof_identity {}\n", proof.to_hex()));
            out.push_str(&format!("backend {} {}\n", by.name, by.version));
        }
        VerificationResult::Failed {
            failure, coverage, ..
        } => {
            out.push_str("outcome failed\n");
            out.push_str(&format!("failure {failure:?}\n"));
            out.push_str(&format!(
                "coverage program={} input={} output={} exit_code={}\n",
                coverage.program_checked,
                coverage.input_checked,
                coverage.output_checked,
                coverage.exit_code_checked
            ));
        }
        VerificationResult::Unsupported { missing, .. } => {
            out.push_str("outcome unsupported\n");
            out.push_str(&format!("missing {missing:?}\n"));
        }
    }
    print!("{out}");
    std::io::stdout().flush().map_err(|e| e.to_string())
}
