//! The RISC Zero heat-diffusion guest -- the third substrate, the same
//! statement.
//!
//! Identical epistemics to the SP1 and Nexus guests: the input is READ
//! (`env::read`), its canonical commitment is computed
//! IN-CIRCUIT by the same `no_std` `execution-commitment` crate, and the
//! statement is committed to the journal -- which `Receipt::verify`
//! cryptographically binds together with the image id. RISC Zero is an
//! EXTRACT-style verifier like SP1: the journal carries the statement.
//!
//! # Journal layout (`ste.r0.kernel-io.v1`)
//!
//! ```text
//! [21B layout tag][32B input commitment][1B marker]
//!     marker 0 (completed): [32B output commitment][4B exit code LE]
//!     marker 1 (halted):    [4B fault exit code LE]
//! ```
//!
//! COMPUTATION != MEASUREMENT, verbatim from the other guests: a proof
//! of this guest never establishes that its input was measured.

#![no_main]
#![no_std]

extern crate alloc;

use alloc::vec::Vec;

use execution_commitment::commit;
use execution_model::{INPUT_TAG, OUTPUT_TAG};
use risc0_zkvm::guest::env;

risc0_zkvm::guest::entry!(main);

/// The journal layout tag. Must match `risc0_adapter::R0_IO_CONVENTION_TAG`.
const CONVENTION_TAG: &[u8] = b"ste.r0.kernel-io.v1";

fn main() {
    // Stable-surface input: the host writes the byte vector with
    // ExecutorEnv::write (risc0's word-serde); the commitment is over
    // the DECODED bytes -- the same bytes the kernel consumes -- so the
    // statement semantics match the other guests exactly.
    let input: Vec<u8> = env::read();
    let input_commitment = commit(INPUT_TAG, &[&input]);
    env::commit_slice(CONVENTION_TAG);
    env::commit_slice(input_commitment.as_bytes());

    match execution_kernel::heat_diffusion(&input) {
        Ok(output) => {
            let output_commitment = commit(OUTPUT_TAG, &[&output]);
            env::commit_slice(&[0u8]);
            env::commit_slice(output_commitment.as_bytes());
            env::commit_slice(&0u32.to_le_bytes());
        }
        Err(fault) => {
            env::commit_slice(&[1u8]);
            env::commit_slice(&fault.exit_code.to_le_bytes());
        }
    }
}
