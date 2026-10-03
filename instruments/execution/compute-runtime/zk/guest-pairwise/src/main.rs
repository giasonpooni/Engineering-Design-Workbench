//! The SP1 guest: links 4-5 of the input-commitment chain, closed.
//!
//! ```text
//! 4. guest READS bytes B          -- sp1_zkvm::io::read_vec()
//! 5. guest computes H(B) INSIDE the proved execution and commits it
//!    in its own committed output  -- execution_commitment::commit,
//!                                    the SAME no_std crate the host
//!                                    uses, so host and guest compute
//!                                    the SAME function
//! ```
//!
//! This is what upgrades SP1's `input_checked` from the recon's `false`
//! to an honest `true`: the binding lives inside the proved execution.
//! A host-supplied digest could not do this (RISC Zero's `input_digest`
//! is the counterexample); a digest merely ECHOED by the guest could not
//! either -- the commitment below is computed from the bytes the read
//! syscall actually returned, not read from anywhere.
//!
//! The kernel is `execution_kernel::pairwise_energy` -- the identical
//! function the native backend runs. One implementation, two substrates.
//!
//! # Committed public-values layout (`ste.sp1.kernel-io.v1`)
//!
//! ```text
//! [22B convention tag][32B input commitment][1B marker]
//!     marker 0 (completed): [32B output commitment][4B exit code LE]
//!     marker 1 (halted):    [4B fault exit code LE]
//! ```
//!
//! The tag domain-separates this layout from anything else a program
//! might commit; the marker byte distinguishes "no output" explicitly --
//! an absent output is a one-byte fact, never a zeroed digest.
//!
//! What a proof of this guest does NOT establish: that the input bytes
//! were ever measured. A fabricated value is computed -- and proved --
//! faithfully. COMPUTATION != MEASUREMENT survives proof generation
//! unchanged.

#![no_main]

use execution_commitment::commit;
use execution_model::{INPUT_TAG, OUTPUT_TAG};

sp1_zkvm::entrypoint!(main);

/// The public-values layout tag (kernel-agnostic since stage 4).
/// Must match `sp1_adapter::SP1_IO_CONVENTION_TAG`.
const CONVENTION_TAG: &[u8] = b"ste.sp1.kernel-io.v1";

pub fn main() {
    let input = sp1_zkvm::io::read_vec();

    // Link 5: the commitment to what was READ, computed in-circuit,
    // before the kernel touches anything.
    let input_commitment = commit(INPUT_TAG, &[&input]);
    sp1_zkvm::io::commit_slice(CONVENTION_TAG);
    sp1_zkvm::io::commit_slice(input_commitment.as_bytes());

    match execution_kernel::pairwise_energy(&input) {
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
