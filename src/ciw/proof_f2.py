"""Prepare a bounded ordinary-F2 checker statement; this never proves execution.

The independent Python reference uses dense row elimination. The staged SCR
Rust guest reconstructs boundaries separately and uses bitset column elimination.
No source/ELF registration or fresh cryptographic authority is inferred here.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct

from .adapters.subprocess import _json
from .declared_workload import _commit
from .proof_obligations import obligation

SCHEMA = "ciw.f2-checker-input.v1"
PROFILE = "bounded-simplicial-v1"
MAX_INPUT = 2325
DESCRIPTOR = (
    b"notations.f2-checker.v1\n"
    b"NSF2: version=1 field=2 homology=ordinary bounds=1; u16 little-endian counts\n"
    b"1<=vertices<=64; 1<=simplices<=256; dimension<=3; full canonical face set\n"
    b"ordinary F2 boundary ranks and Betti vector; candidate must equal recomputation\n"
    b"output NSF2O1: u8 dimension-count then u16 counts, ranks(D_k), Betti\n"
    b"faults: 2=malformed 3=bounds 4=order 5=face 6=chain 7=candidate 8=policy"
)


def validate(value: dict) -> dict:
    """Copy and validate without repairing, sorting or filling missing faces."""
    value = deepcopy(value)
    fields = {"schema", "profile", "coefficient_field", "homology", "vertex_count", "simplices", "candidate_betti"}
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError("Require the exact F2 checker input fields")
    if (value["schema"], value["profile"], value["coefficient_field"], value["homology"]) != (
        SCHEMA, PROFILE, "F2", "ordinary"
    ):
        raise ValueError("Unsupported checker version, field, homology or bounds profile")
    n = value["vertex_count"]
    simplices = value["simplices"]
    if type(n) is not int or not 1 <= n <= 64 or not isinstance(simplices, list) or not 1 <= len(simplices) <= 256:
        raise ValueError("F2 checker requires 1..64 vertices and 1..256 simplices")
    previous = None
    present = set()
    for simplex in simplices:
        if not isinstance(simplex, list) or not 1 <= len(simplex) <= 4:
            raise ValueError("Only explicitly listed nonempty simplices through dimension three are supported")
        if any(type(v) is not int or not 0 <= v < n for v in simplex):
            raise ValueError("Vertex identifier outside the declared range")
        key = (len(simplex), tuple(simplex))
        if list(sorted(set(simplex))) != simplex or (previous is not None and key <= previous):
            raise ValueError("Simplices must be unique and ordered by dimension then increasing vertex identifiers")
        present.add(tuple(simplex)); previous = key
        if len(simplex) > 1:
            for i in range(len(simplex)):
                if tuple(simplex[:i] + simplex[i + 1:]) not in present:
                    raise ValueError("Missing explicitly listed codimension-one face")
    if any((v,) not in present for v in range(n)):
        raise ValueError("Every declared vertex must have its singleton simplex")
    size = len(simplices[-1])
    candidate = value["candidate_betti"]
    if not isinstance(candidate, list) or len(candidate) != size or any(type(b) is not int or not 0 <= b <= 256 for b in candidate):
        raise ValueError("Candidate must supply one bounded ordinary Betti number per dimension")
    return value


def encode(value: dict) -> bytes:
    """All mathematically relevant settings and the candidate enter guest input."""
    value = validate(value)
    result = bytearray(b"NSF2\x01\x02\x00\x01")
    result += struct.pack("<HH", value["vertex_count"], len(value["simplices"]))
    for simplex in value["simplices"]:
        result.append(len(simplex))
        result += struct.pack("<" + "H" * len(simplex), *simplex)
    result.append(len(value["candidate_betti"]))
    result += struct.pack("<" + "H" * len(value["candidate_betti"]), *value["candidate_betti"])
    return bytes(result)


def decode(raw: bytes) -> dict:
    """Strict bounded wire decoder, including complete consumption of the bytes."""
    if type(raw) is not bytes or not 12 <= len(raw) <= MAX_INPUT or raw[:8] != b"NSF2\x01\x02\x00\x01":
        raise ValueError("Malformed or unsupported F2 input header")
    n, count = struct.unpack_from("<HH", raw, 8)
    if not 1 <= n <= 64 or not 1 <= count <= 256:
        raise ValueError("F2 input dimensions exceed the profile")
    at = 12; simplices = []
    try:
        for _ in range(count):
            size = raw[at]; at += 1
            if not 1 <= size <= 4:
                raise ValueError("Invalid simplex size")
            simplices.append(list(struct.unpack_from("<" + "H" * size, raw, at))); at += 2 * size
        size = raw[at]; at += 1
        if not 1 <= size <= 4:
            raise ValueError("Invalid candidate length")
        candidate = list(struct.unpack_from("<" + "H" * size, raw, at)); at += 2 * size
    except (IndexError, struct.error) as exc:
        raise ValueError("Truncated F2 input") from exc
    if at != len(raw):
        raise ValueError("F2 input has trailing bytes")
    return validate({"schema": SCHEMA, "profile": PROFILE, "coefficient_field": "F2", "homology": "ordinary",
                     "vertex_count": n, "simplices": simplices, "candidate_betti": candidate})


def _rank(rows: list[list[int]], columns: int) -> int:
    matrix = deepcopy(rows)
    r = 0
    for c in range(columns):
        pivot = next((i for i in range(r, len(matrix)) if matrix[i][c]), None)
        if pivot is None:
            continue
        matrix[r], matrix[pivot] = matrix[pivot], matrix[r]
        for i in range(r + 1, len(matrix)):
            if matrix[i][c]:
                matrix[i] = [a ^ b for a, b in zip(matrix[i], matrix[r])]
        r += 1
    return r


def reference(value: dict) -> dict:
    """Independently recompute counts/ranks; a candidate match is not a zk proof."""
    value = validate(value)
    length = len(value["candidate_betti"])
    groups = [[tuple(s) for s in value["simplices"] if len(s) == k + 1] for k in range(length)]
    matrices = [[]]
    for k in range(1, length):
        rows = [[0] * len(groups[k]) for _ in groups[k - 1]]
        index = {s: i for i, s in enumerate(groups[k - 1])}
        for j, s in enumerate(groups[k]):
            for v in range(len(s)):
                rows[index[s[:v] + s[v + 1:]]][j] ^= 1
        matrices.append(rows)
    for k in range(2, length):
        for row in matrices[k - 1]:
            for j in range(len(groups[k])):
                if sum(a * matrices[k][i][j] for i, a in enumerate(row)) % 2:
                    raise ValueError("Boundary composition is nonzero")
    ranks = [0] + [_rank(matrices[k], len(groups[k])) for k in range(1, length)] + [0]
    counts = [len(g) for g in groups]
    betti = [counts[k] - ranks[k] - ranks[k + 1] for k in range(length)]
    return {"counts": counts, "ranks": ranks[:-1], "betti": betti, "candidate_matches": betti == value["candidate_betti"]}


def output_bytes(result: dict) -> bytes:
    length = len(result["betti"])
    return b"NSF2O1" + bytes([length]) + b"".join(struct.pack("<H", x) for key in ("counts", "ranks", "betti") for x in result[key])


def prepare(raw: bytes) -> dict:
    """Prepare the exact checker statement, retaining the original source bytes."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 32768:
        raise ValueError("F2 JSON source must contain 1..32768 bytes")
    value = validate(_json(raw)); inputs = encode(value); result = reference(value)
    if not result["candidate_matches"]:
        raise ValueError("Candidate Betti vector disagrees with independent exact reference")
    output = output_bytes(result)
    return {"schema": "ciw.f2-checker-preparation.v1", "status": "prepared_not_proved",
            "source_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "source_bytes_b64": base64.b64encode(raw).decode("ascii"),
            "specification": {"program": DESCRIPTOR.hex(), "configuration": "", "input_payload": inputs.hex()},
            "specification_identity": _commit("specification", [DESCRIPTOR, b"", inputs]),
            "program_identity": _commit("program", [DESCRIPTOR]), "input_identity": _commit("input", [inputs]),
            "expected_output": output.hex(), "expected_output_identity": _commit("output", [output]),
            "reference": result, "proof_obligation": obligation(
                "ordinary_f2_betti_equals_candidate.v1", DESCRIPTOR, inputs, output,
                unproved_context={"source_sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}),
            "guest_registration": "pending", "cryptographic_verification": "not_performed",
            "physical_validation": "not_performed", "state_admission": "not_performed"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    try:
        with args.source.open("rb") as stream:
            raw = stream.read(32769)
        print(json.dumps(prepare(raw), indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, "F2 preparation refused: " + str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
