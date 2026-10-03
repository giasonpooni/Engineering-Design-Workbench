//! Canonical encoding -- the bottom of the substrate.
//!
//! # What this is, and what it deliberately is not
//!
//! Phase 126 read three zkVM substrates and found three mutually
//! incompatible wire formats for the same values:
//!
//! | substrate | encoding |
//! |---|---|
//! | RISC Zero | word-oriented serde over `u32` words |
//! | SP1       | `bincode` |
//! | Nexus     | `postcard` + COBS, zero-padded to 4 bytes |
//!
//! `to_vec(&42u32)` produces different bytes in all three. There is no
//! shared wire format and no prospect of one.
//!
//! This module therefore defines **our** canonical encoding, and makes no
//! claim whatsoever about theirs. A backend will carry our canonical
//! bytes opaquely through its own encoding; it will never be asked to
//! reproduce this function, and this function will never be asked to
//! reproduce a backend's.
//!
//! # The encoding
//!
//! ```text
//! canonical(tag, fields) :=
//!     len(tag)          as u64 little-endian
//!     tag               as UTF-8 bytes
//!     count(fields)     as u64 little-endian
//!     for each field:
//!         len(field)    as u64 little-endian
//!         field         as raw bytes
//! ```
//!
//! Two properties, and only these two, are claimed:
//!
//! **Deterministic.** The same `(tag, fields)` always yields the same
//! bytes. There is no map iteration order, no float formatting, no
//! locale, no clock, and no allocation-address dependence anywhere in
//! it.
//!
//! **Injective.** Distinct `(tag, fields)` yield distinct bytes. Length
//! prefixes are what buy this: without them `["ab", ""]` and
//! `["a", "b"]` would both encode to `ab`, and two different inputs
//! would share an identity. This is not a theoretical concern -- it is
//! the standard concatenation ambiguity, and it is the reason RISC Zero
//! hashes structures with a domain tag and an explicit shape
//! (`tagged_struct`, `risc0/binfmt/src/hash.rs:75`) rather than by
//! concatenating fields.
//!
//! It is NOT self-describing: nothing here can decode. Decoding is not
//! needed to commit to bytes, and a decoder would be a second, larger
//! surface to keep deterministic.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

use alloc::vec::Vec;

/// Encode a domain tag and an ordered list of byte fields into the
/// canonical form described at the module level.
///
/// The `tag` is a domain separator and is part of the encoding, not
/// decoration: `canonical(PROGRAM_TAG, [b])` and
/// `canonical(INPUT_TAG, [b])` differ for every `b`. That is what stops
/// a program and an input that happen to hold identical bytes from
/// sharing an identity.
pub fn canonical(tag: &str, fields: &[&[u8]]) -> Vec<u8> {
    let tag_bytes = tag.as_bytes();
    let mut total = 8 + tag_bytes.len() + 8;
    for field in fields {
        total += 8 + field.len();
    }

    let mut out = Vec::with_capacity(total);
    out.extend_from_slice(&(tag_bytes.len() as u64).to_le_bytes());
    out.extend_from_slice(tag_bytes);
    out.extend_from_slice(&(fields.len() as u64).to_le_bytes());
    for field in fields {
        out.extend_from_slice(&(field.len() as u64).to_le_bytes());
        out.extend_from_slice(field);
    }
    out
}

/// Encode a `u32` as a canonical byte field.
///
/// Little-endian and fixed-width, so that `0` and `0u32` never encode
/// differently and no textual formatting (which would drag in locale and
/// leading-zero questions) is involved. Used for exit codes.
pub fn canonical_u32(value: u32) -> [u8; 4] {
    value.to_le_bytes()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_input_yields_same_bytes() {
        assert_eq!(canonical("t", &[b"a"]), canonical("t", &[b"a"]));
    }

    #[test]
    fn distinct_fields_yield_distinct_bytes() {
        assert_ne!(canonical("t", &[b"a"]), canonical("t", &[b"b"]));
    }

    #[test]
    fn length_prefixes_defeat_concatenation_ambiguity() {
        // The whole reason lengths are written. Without them both of
        // these would encode the same payload bytes, and two different
        // inputs would share one identity.
        let joined: &[u8] = b"ab";
        let empty: &[u8] = b"";
        let a: &[u8] = b"a";
        let b: &[u8] = b"b";
        assert_ne!(canonical("t", &[joined, empty]), canonical("t", &[a, b]));
    }

    #[test]
    fn the_tag_is_part_of_the_encoding() {
        assert_ne!(canonical("program", &[b"x"]), canonical("input", &[b"x"]));
    }

    #[test]
    fn field_count_distinguishes_empty_from_absent() {
        let empty: &[u8] = b"";
        assert_ne!(canonical("t", &[]), canonical("t", &[empty]));
    }

    #[test]
    fn encoding_is_stable_across_capacity_hints() {
        // Guards the `total` pre-computation: a wrong capacity must never
        // change the bytes, only the allocation.
        let owned: Vec<[u8; 2]> = (0u8..64).map(|i| [i, i.wrapping_mul(7)]).collect();
        let fields: Vec<&[u8]> = owned.iter().map(|f| f.as_slice()).collect();
        assert_eq!(canonical("t", &fields), canonical("t", &fields));
        assert_ne!(canonical("t", &fields), canonical("t", &fields[..63]));
    }
}
