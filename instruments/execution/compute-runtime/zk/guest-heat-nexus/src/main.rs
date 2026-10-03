//! The Nexus heat-diffusion guest -- the STE1 layout, the heat kernel.
//! All of the pairwise Nexus guest's documentation applies verbatim.

#![cfg_attr(target_arch = "riscv32", no_std, no_main)]

extern crate alloc;

use alloc::vec::Vec;

use execution_commitment::commit;
use execution_model::{INPUT_TAG, OUTPUT_TAG};

/// Layout tag: "STE1" as LE u32, shared by every STE Nexus guest.
pub const LAYOUT_STE1: u32 = u32::from_le_bytes(*b"STE1");

#[nexus_rt::main]
#[nexus_rt::private_input(input)]
fn main(input: Vec<u8>) -> (u32, [u8; 32], Option<[u8; 32]>, u32) {
    let input_commitment = *commit(INPUT_TAG, &[&input]).as_bytes();
    match execution_kernel::heat_diffusion(&input) {
        Ok(output) => (
            LAYOUT_STE1,
            input_commitment,
            Some(*commit(OUTPUT_TAG, &[&output]).as_bytes()),
            0,
        ),
        Err(fault) => (LAYOUT_STE1, input_commitment, None, fault.exit_code),
    }
}
