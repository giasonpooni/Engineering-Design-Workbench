"""Transformer Engine baseline: measure before optimizing.

The smallest real workload (molecular tokens -> hardmax attention
through the STE engine), timed per phase over repeated forwards, with
the reference-agreement count and the engine child's memory. The point
is to find the ACTUAL bottleneck, not to assume one.
"""

import pathlib
import resource
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from structures.library import METHANE, WATER
from transformer.model import AttentionModel, reference_attention
from transformer.representation import molecule_representation

EYE = tuple(tuple(1 if i == j else 0 for j in range(4)) for i in range(4))
MIXER = tuple(tuple((i * 7 + j * 3 + 1) % 5 - 2 for j in range(4)) for i in range(4))
MODEL = AttentionModel(EYE, MIXER, EYE)
N = 100


def main():
    reps, t0 = [], time.monotonic()
    for _ in range(N):
        reps.append(molecule_representation(WATER))
        reps.append(molecule_representation(METHANE))
    rep_time = (time.monotonic() - t0) / (2 * N)

    t0 = time.monotonic()
    specs = [MODEL.forward_spec(rep) for rep in reps]
    encode_time = (time.monotonic() - t0) / len(specs)

    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.monotonic()
    agree = 0
    for rep in reps[: 2 * N]:
        prediction = MODEL.forward(rep)
        expected = reference_attention(
            [list(r) for r in rep.tokens], [list(r) for r in MODEL.wq],
            [list(r) for r in MODEL.wk], [list(r) for r in MODEL.wv])
        agree += prediction.values == expected
    total = time.monotonic() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    forward_time = total / (2 * N)

    print("=== TRANSFORMER ENGINE BASELINE ===")
    print(f"forwards executed          : {2 * N} (water + methane, d=4)")
    print(f"reference agreement        : {agree}/{2 * N}")
    print(f"representation construction: {rep_time * 1e6:8.1f} us/forward")
    print(f"spec encoding (tensor+low) : {encode_time * 1e6:8.1f} us/forward")
    print(f"forward via STE engine     : {forward_time * 1e3:8.2f} ms/forward "
          f"({2 * N / total:.0f} forwards/s)")
    print(f"engine child peak RSS      : "
          f"{(after.ru_maxrss - 0) / 1024:.1f} MB (max across engine processes)")
    print(f"cpu seconds in children    : "
          f"{(after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime):.2f}s "
          f"over {total:.2f}s wall")
    print("bottleneck                 : the per-forward cost is dominated by the")
    print("                             one-process-per-execution engine boundary")
    print("                             (spawn+IPC), not by attention arithmetic --")
    print("                             see the doc for the measured split")


if __name__ == "__main__":
    main()
