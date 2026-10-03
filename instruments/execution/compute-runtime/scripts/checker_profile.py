"""Profile the per-item batch result path: where do the 0.088 ms go?"""

import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from execution.commitments import COMPUTATION_TAG, OUTPUT_TAG, canonical_u32, commit_hex
from execution.engine import (
    _check_result, _encode_request, _parse_lines, _split_blocks,
    default_cli_path, run_specifications,
)
from structures.library import METHANE, WATER
from transformer.model import AttentionModel
from transformer.representation import molecule_representation

EYE = tuple(tuple(1 if i == j else 0 for j in range(4)) for i in range(4))
MODEL = AttentionModel(EYE, EYE, EYE)
B = 256
SPECS = [MODEL.forward_spec(molecule_representation([WATER, METHANE][i % 2]))
         for i in range(B)]


def timeit(label, fn, n=1):
    t0 = time.monotonic()
    for _ in range(n):
        fn()
    per = (time.monotonic() - t0) / n / B * 1e6
    print(f"  {label:38} {per:8.2f} us/item")
    return per


def main():
    request = b"".join(_encode_request(s) for s in SPECS)

    # engine alone (no Python checking at all)
    t0 = time.monotonic()
    proc = subprocess.run([str(default_cli_path())], input=request, capture_output=True)
    engine = (time.monotonic() - t0) / B * 1e6
    stdout = proc.stdout.decode()
    print(f"  {'engine subprocess (spawn+exec+IPC)':38} {engine:8.2f} us/item")

    # full path for comparison
    t0 = time.monotonic()
    run_specifications(SPECS)
    total = (time.monotonic() - t0) / B * 1e6
    print(f"  {'FULL run_specifications':38} {total:8.2f} us/item")
    print(f"  {'=> Python-side checking total':38} {total - engine:8.2f} us/item")
    print()

    timeit("request serialization", lambda: [_encode_request(s) for s in SPECS], n=20)
    timeit("stdout decode+split blocks", lambda: _split_blocks(proc.stdout.decode()), n=20)
    blocks = _split_blocks(stdout)
    timeit("parse lines (all blocks)", lambda: [_parse_lines(b) for b in blocks], n=20)
    fields = [_parse_lines(b) for b in blocks]
    timeit("spec.identity()", lambda: [s.identity() for s in SPECS], n=20)
    timeit("spec.program_identity()", lambda: [s.program_identity() for s in SPECS], n=20)
    timeit("spec.input_identity()", lambda: [s.input_identity() for s in SPECS], n=20)
    outs = [f.get("output", "") for f in fields]
    timeit("hex decode outputs", lambda: [bytes.fromhex(o) for o in outs], n=50)
    raw = [bytes.fromhex(o) for o in outs]
    timeit("output commit", lambda: [commit_hex(OUTPUT_TAG, [r]) for r in raw], n=50)
    pid = SPECS[0].program_identity()
    iids = [s.input_identity() for s in SPECS]
    oids = [commit_hex(OUTPUT_TAG, [r]) for r in raw]
    timeit("computation commit", lambda: [
        commit_hex(COMPUTATION_TAG, [bytes.fromhex(pid), bytes.fromhex(i),
                                     bytes.fromhex(o), canonical_u32(0)])
        for i, o in zip(iids, oids)], n=50)
    timeit("full _check_result (reference)",
           lambda: [_check_result(s, f) for s, f in zip(SPECS, fields)], n=20)


if __name__ == "__main__":
    main()
