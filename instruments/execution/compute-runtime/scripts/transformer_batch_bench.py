"""Batched-forward benchmark: per_forward_cost(B), measured.

Same model, same water/methane token matrices as the phase-1 baseline;
each batch size timed over enough repetitions to average the spawn
cost. Startup attribution = the B=1 per-forward cost minus the
marginal per-item cost at large B.
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from structures.library import METHANE, WATER
from transformer.model import AttentionModel
from transformer.representation import molecule_representation

EYE = tuple(tuple(1 if i == j else 0 for j in range(4)) for i in range(4))
MIXER = tuple(tuple((i * 7 + j * 3 + 1) % 5 - 2 for j in range(4)) for i in range(4))
MODEL = AttentionModel(EYE, MIXER, EYE)
REPS = [molecule_representation(m) for m in (WATER, METHANE)]


def bench(batch_size: int, total_forwards: int = 512):
    reps = [REPS[i % 2] for i in range(batch_size)]
    rounds = max(1, total_forwards // batch_size)
    t0 = time.monotonic()
    for _ in range(rounds):
        MODEL.forward_batch(reps)
    wall = time.monotonic() - t0
    forwards = rounds * batch_size
    per = wall / forwards
    print(f"  B={batch_size:4d}  total {wall:6.2f}s over {forwards:4d} forwards  "
          f"{per * 1e3:7.3f} ms/forward  {forwards / wall:7.0f} forwards/s")
    return per


def main():
    print("=== BATCHED FORWARD BENCHMARK (d=4 molecular tokens) ===")
    costs = {b: bench(b) for b in (1, 2, 4, 8, 16, 64, 256)}
    marginal = costs[256]
    startup = costs[1] - marginal
    print(f"per-item marginal cost (B=256) : {marginal * 1e3:.3f} ms")
    print(f"amortized boundary cost (B=1)  : {startup * 1e3:.3f} ms/forward "
          f"({100 * startup / costs[1]:.0f}% of the single-forward cost)")
    print(f"speedup at B=16 / B=256        : "
          f"x{costs[1] / costs[16]:.1f} / x{costs[1] / costs[256]:.1f}")


if __name__ == "__main__":
    main()
