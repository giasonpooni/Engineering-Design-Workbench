"""The canonical commitment function, in Python, byte-for-byte the Rust one.

This is NOT a second identity system -- it is the SAME function in a
second language, and `tests/test_execution_commitments.py` pins the
agreement against the exact vectors `crates/execution-core/tests/
semantics.rs` pins from the other side. The Rust side is authoritative
(`docs/RUST_EXECUTION_ARCHITECTURE.md`); this module exists so the
Python orchestration layer can RECOMPUTE every identity the execution
engine echoes across the process boundary and refuse any mismatch --
the engine is checked, never trusted (`execution/engine.py`).

The encoding is `execution-serialization`'s `canonical(tag, fields)`:

    len(tag) u64 LE | tag | count(fields) u64 LE | (len u64 LE | bytes)*

and the commitment is SHA-256 of it, lowercase hex -- the same primitive
and the same hex form `evidence.identity.content_hash` already uses.
What is deliberately NOT here: canonical JSON. Execution identities
commit to raw bytes (an ELF is not a JSON document), which is exactly
why this module exists beside `evidence/identity.py` rather than being
replaced by it.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Sequence

#: Domain tags -- mirrored verbatim from `crates/execution-model/src/lib.rs`.
PROGRAM_TAG = "scout.execution.program.v1"
INPUT_TAG = "scout.execution.input.v1"
OUTPUT_TAG = "scout.execution.output.v1"
PROOF_TAG = "scout.execution.proof.v1"
COMPUTATION_TAG = "scout.execution.computation.v1"
SPECIFICATION_TAG = "scout.execution.specification.v1"


def canonical(tag: str, fields: Sequence[bytes]) -> bytes:
    """`execution_serialization::canonical`, byte-identical."""
    tag_bytes = tag.encode("utf-8")
    out = struct.pack("<Q", len(tag_bytes)) + tag_bytes + struct.pack("<Q", len(fields))
    for field in fields:
        out += struct.pack("<Q", len(field)) + field
    return out


def commit_hex(tag: str, fields: Sequence[bytes]) -> str:
    """`execution_commitment::commit(...).to_hex()`, byte-identical."""
    return hashlib.sha256(canonical(tag, fields)).hexdigest()


def canonical_u32(value: int) -> bytes:
    """`execution_serialization::canonical_u32`: u32 LE, fixed width."""
    return struct.pack("<I", value)
