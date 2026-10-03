//! The Nexus guest: the identical statement, on a second substrate.
//!
//! Same kernel (`execution_kernel::pairwise_energy` -- the exact crate
//! the native backend and the SP1 guest compile), same commitment
//! function (`execution_commitment::commit`, `no_std`, computed
//! IN-CIRCUIT over the bytes actually read), same domain tags. What
//! differs is only what Phase 126 established cannot be shared: the wire
//! encoding (postcard here, raw public-values bytes on SP1) and the
//! runtime (nexus_rt vs sp1_zkvm).
//!
//! # The committed statement (`STE1` layout, postcard-encoded)
//!
//! ```text
//! (LAYOUT_STE1: u32,
//!  input_commitment:  [u8; 32],          -- computed in-circuit
//!  output_commitment: Option<[u8; 32]>,  -- None = kernel fault;
//!                                           absence is Option's None,
//!                                           never a zeroed digest
//!  exit_code: u32)                       -- 0, or the kernel fault code
//! ```
//!
//! The guest itself always exits the VM successfully; OUR exit code
//! lives inside the statement -- the same discipline as the SP1 guest,
//! so both backends prove the same statement shape.
//!
//! Input arrives on the PRIVATE tape deliberately: Nexus can bind public
//! input natively, but the cross-backend statement must not depend on a
//! facility only one backend has. The input binding both backends share
//! is the in-circuit commitment.
//!
//! COMPUTATION != MEASUREMENT, verbatim from the SP1 guest: a proof of
//! this guest establishes what was computed from the bytes read -- never
//! that those bytes were measured. A fabricated value is computed, and
//! proved, faithfully.

#![cfg_attr(target_arch = "riscv32", no_std, no_main)]

extern crate alloc;

use alloc::vec::Vec;

use execution_commitment::commit;
use execution_model::{INPUT_TAG, OUTPUT_TAG};

/// Layout tag: "STE1" as LE u32. Domain-separates this statement layout
/// from anything else a Nexus guest might output.
pub const LAYOUT_STE1: u32 = u32::from_le_bytes(*b"STE1");

#[nexus_rt::main]
#[nexus_rt::private_input(input)]
fn main(input: Vec<u8>) -> (u32, [u8; 32], Option<[u8; 32]>, u32) {
    let input_commitment = *commit(INPUT_TAG, &[&input]).as_bytes();
    match execution_kernel::pairwise_energy(&input) {
        Ok(output) => (
            LAYOUT_STE1,
            input_commitment,
            Some(*commit(OUTPUT_TAG, &[&output]).as_bytes()),
            0,
        ),
        Err(fault) => (LAYOUT_STE1, input_commitment, None, fault.exit_code),
    }
}
