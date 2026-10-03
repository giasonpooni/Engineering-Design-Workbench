//! Commitments: SHA-256 over canonical bytes, in the repository's
//! existing hex form.
//!
//! One type, `Commitment`, and one constructor, [`commit`]. Everything
//! above this crate names things by calling [`commit`] with a domain tag;
//! nothing above it hashes anything itself.
//!
//! # A commitment is not a claim
//!
//! A `Commitment` says only "these exact bytes". It does not say the
//! bytes are true, that they came from an instrument, or that anyone
//! executed anything. Phase 111b established that identity is a function
//! of content while authenticity is a function of history, and that
//! content does not encode history. A hash is the clearest possible case
//! of that: two byte-identical programs have one identity regardless of
//! who wrote them or why.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

mod sha256;

use alloc::string::String;
use core::fmt;
use execution_serialization::canonical;

pub use sha256::sha256;

/// A 32-byte SHA-256 digest of canonically encoded bytes.
///
/// Stored as bytes, rendered as lowercase hex. Lowercase hex is not a
/// stylistic choice: it is what `evidence/identity.py::content_hash`
/// already produces (`hashlib.sha256(...).hexdigest()`), and having two
/// hex conventions in one system is how identities silently stop
/// matching.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Commitment([u8; 32]);

impl Commitment {
    /// The raw digest bytes.
    pub const fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }

    /// Lowercase hex, the form this repository stores identities in.
    pub fn to_hex(&self) -> String {
        let mut s = String::with_capacity(64);
        for byte in self.0.iter() {
            s.push(hex_digit(byte >> 4));
            s.push(hex_digit(byte & 0x0f));
        }
        s
    }
}

fn hex_digit(nibble: u8) -> char {
    match nibble {
        0..=9 => (b'0' + nibble) as char,
        _ => (b'a' + nibble - 10) as char,
    }
}

impl fmt::Debug for Commitment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Full hex, never truncated. A truncated digest in a log is how
        // two different identities come to look like one.
        write!(f, "{}", self.to_hex())
    }
}

impl fmt::Display for Commitment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_hex())
    }
}

/// Commit to `fields` under the domain separator `tag`.
///
/// This is the ONLY place bytes become an identity in this substrate.
/// The `tag` makes each identity kind a distinct domain, so the same
/// bytes committed as a program and as an input are different
/// commitments -- see [`execution_serialization::canonical`].
pub fn commit(tag: &str, fields: &[&[u8]]) -> Commitment {
    Commitment(sha256(&canonical(tag, fields)))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// FIPS 180-4 / NIST published vectors. These are the reason this
    /// implementation needs no third-party crate to be trustworthy.
    #[test]
    fn matches_published_sha256_vectors() {
        let cases: [(&[u8], &str); 3] = [
            (
                b"",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                b"abc",
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ),
            (
                b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
                "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
            ),
        ];
        for (message, expected) in cases {
            let digest = Commitment(sha256(message));
            assert_eq!(digest.to_hex(), expected, "vector failed: {message:?}");
        }
    }

    #[test]
    fn handles_block_boundary_lengths() {
        // 55, 56, 63, 64, 65 bytes exercise every padding branch.
        for len in [55usize, 56, 63, 64, 65, 119, 120] {
            let message = alloc::vec![b'a'; len];
            let digest = sha256(&message);
            assert_eq!(digest.len(), 32);
            // Determinism at each boundary.
            assert_eq!(digest, sha256(&message));
        }
    }

    #[test]
    fn hex_is_lowercase_and_full_width() {
        let hex = commit("t", &[b"x"]).to_hex();
        assert_eq!(hex.len(), 64);
        assert!(hex
            .chars()
            .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c)));
    }

    #[test]
    fn the_tag_separates_domains() {
        assert_ne!(commit("program", &[b"x"]), commit("input", &[b"x"]));
    }
}
