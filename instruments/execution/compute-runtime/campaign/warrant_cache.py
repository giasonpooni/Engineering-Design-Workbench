"""WarrantCache: proof bytes, content-addressed -- never trust.

The Stage 7 campaign measured 5 of 15 routine proofs re-proving an
IDENTICAL statement. A proof is a portable artifact, so an identical
statement can reuse it -- but reuse means re-VERIFY, never believe:

    cache hit -> retrieve bytes -> backend verifier -> VerifiedExecution
                                        (mandatory, every hit)

The cache's whole responsibility is artifact storage and retrieval. It
does not execute science, does not select backends (policy's job), does
not admit evidence, and holds no trust: a corrupted entry is discovered
by the verifier, exactly like any other bad proof.

THE STATEMENT KEY (what guarantees a proof answers the same question):

    commit( scout.campaign.warrant-statement.v1,
            [backend name, guest artifact sha256, specification identity] )

- specification identity covers program descriptor, configuration and
  input (any change -> different key -> miss);
- the guest ARTIFACT hash covers the executable (same spec, rebuilt or
  different ELF -> miss, per stage 5's identity discipline);
- the backend name isolates proof systems structurally (a Nexus proof
  can never be RETRIEVED for a RISC Zero request; even if it somehow
  were, the RISC Zero verifier would reject the bytes -- the key is the
  structural guarantee, the verifier the cryptographic one).

Output and exit code are NOT in the key, deliberately: the statement
verified on every hit is rebuilt from the FRESH native execution, so a
cached proof whose committed output disagrees with the recomputed
result fails verification -- it cannot silently pass. Determinism makes
(spec -> output) a function; the verifier enforces it per hit.

NOT in the key, ever: occurrence numbers, timestamps, filenames, hosts,
PIDs. The cache deduplicates PROOFS, not OPERATIONS -- three runs of one
spec are three occurrences, one observation, one reusable warrant
(the Phase 121-123 two-ledger distinction, applied to warrants).

Storage (deliberately minimal, per the stage's own overbuild ban): an
immutable local directory per statement key holding `proof.bin` and a
`meta` text file; the proof ARTIFACT identity is sha256 of its bytes.
No TTLs, no LRU, no databases: invalidation is identity-based (a
changed statement is a different key) plus one EXPLICIT operation,
`invalidate`, for the policy's recorded decision to discard a warrant
that failed verification.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass
from typing import Optional

from execution.commitments import commit_hex
from execution.specification import ExecutionSpecification

STATEMENT_TAG = "scout.campaign.warrant-statement.v1"


def statement_key(backend: str, elf_path: pathlib.Path, spec: ExecutionSpecification) -> str:
    elf_sha = hashlib.sha256(elf_path.read_bytes()).hexdigest()
    return commit_hex(
        STATEMENT_TAG,
        [backend.encode(), elf_sha.encode(), spec.identity().encode()],
    )


@dataclass(frozen=True)
class CachedWarrant:
    """A retrieved artifact: bytes on disk plus recorded metadata.
    `artifact_intact` reports whether the bytes still hash to the
    recorded artifact identity -- INFORMATION, not a gate: the verifier
    is the gate, and corrupted bytes go to it and fail there."""

    statement_key: str
    proof_path: pathlib.Path
    recorded_artifact_sha256: str
    backend: str
    spec_identity: str

    @property
    def artifact_intact(self) -> bool:
        return (
            hashlib.sha256(self.proof_path.read_bytes()).hexdigest()
            == self.recorded_artifact_sha256
        )


class WarrantCache:
    """Immutable local artifact store keyed by statement identity."""

    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _entry(self, key: str) -> pathlib.Path:
        return self.root / key

    def lookup(self, key: str) -> Optional[CachedWarrant]:
        entry = self._entry(key)
        proof = entry / "proof.bin"
        meta = entry / "meta"
        if not (proof.exists() and meta.exists()):
            return None
        fields = dict(
            line.partition(" ")[::2] for line in meta.read_text().splitlines() if line
        )
        return CachedWarrant(
            statement_key=key, proof_path=proof,
            recorded_artifact_sha256=fields.get("artifact_sha256", ""),
            backend=fields.get("backend", ""), spec_identity=fields.get("spec", ""),
        )

    def store(self, key: str, proof_bytes: bytes, backend: str,
              spec_identity: str) -> str:
        """Store immutably; returns the content-addressed artifact id
        (sha256 of the bytes -- same bytes, same identity, always)."""
        entry = self._entry(key)
        entry.mkdir(parents=True, exist_ok=True)
        artifact = hashlib.sha256(proof_bytes).hexdigest()
        (entry / "proof.bin").write_bytes(proof_bytes)
        (entry / "meta").write_text(
            f"artifact_sha256 {artifact}\nbackend {backend}\nspec {spec_identity}\n"
        )
        return artifact

    def invalidate(self, key: str) -> None:
        """The one explicit mutation: the POLICY's recorded decision to
        discard a warrant that failed verification. Never automatic."""
        entry = self._entry(key)
        for name in ("proof.bin", "meta"):
            path = entry / name
            if path.exists():
                path.unlink()
        if entry.exists():
            entry.rmdir()
