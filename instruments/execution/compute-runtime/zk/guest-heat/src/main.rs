//! The SP1 heat-diffusion guest.
//!
//! Identical structure and identical `ste.sp1.kernel-io.v1` layout as
//! the pairwise guest -- the kernel call is the only difference, which
//! is the point: a new provable workload is a new guest around the same
//! `no_std` kernel crate, not a new convention. All the pairwise guest's
//! epistemics apply verbatim, including COMPUTATION != MEASUREMENT.

#![no_main]

use execution_commitment::commit;
use execution_model::{INPUT_TAG, OUTPUT_TAG};

sp1_zkvm::entrypoint!(main);

const CONVENTION_TAG: &[u8] = b"ste.sp1.kernel-io.v1";

pub fn main() {
    let input = sp1_zkvm::io::read_vec();
    let input_commitment = commit(INPUT_TAG, &[&input]);
    sp1_zkvm::io::commit_slice(CONVENTION_TAG);
    sp1_zkvm::io::commit_slice(input_commitment.as_bytes());

    match execution_kernel::heat_diffusion(&input) {
        Ok(output) => {
            let output_commitment = commit(OUTPUT_TAG, &[&output]);
            sp1_zkvm::io::commit_slice(&[0u8]);
            sp1_zkvm::io::commit_slice(output_commitment.as_bytes());
            sp1_zkvm::io::commit_slice(&0u32.to_le_bytes());
        }
        Err(fault) => {
            sp1_zkvm::io::commit_slice(&[1u8]);
            sp1_zkvm::io::commit_slice(&fault.exit_code.to_le_bytes());
        }
    }
}
