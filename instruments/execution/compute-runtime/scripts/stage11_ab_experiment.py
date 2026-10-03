"""Stage 11, part 2: unconstrained vs memory-aware manufacture, A/B.

The IDENTICAL thirteen fresh statements (stage-9's sweep shape with a
stage-11 marker so every statement is genuinely new), manufactured
twice with 4 workers:

    arm A  no worker limits        (stage-9 behavior: OOM kills land in
                                    the serial retry pass)
    arm B  worker_limits nexus<=2  (the measured memory class: ~10 GB
                                    peak/worker against 16 GB)

Separate cache roots so arm B never hits arm A's warrants. The gate is
successful only if USEFUL throughput or reliability improves -- OOM
kills never count as parallelism.
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.policy import VerificationPolicy, default_lanes
from campaign.prefetch import prefetch_warrants
from campaign.warrant_cache import WarrantCache
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)
from scripts.stage11_memory_curve import RssSampler

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage11-ab"))
OUT.mkdir(parents=True, exist_ok=True)

MARKER = 222_221  # distinct from the curve's marker: all statements new


def profile(kind, n):
    if kind == "hot-center":
        return [MARKER] * (n // 2) + [1_000_000] + [MARKER] * (n - n // 2 - 1)
    if kind == "hot-left":
        return [1_000_000, 800_000] + [MARKER] * (n - 2)
    return [MARKER + int(1_000_000 * i / (n - 1)) for i in range(n)]


SPECS = [
    ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"",
                           encode_heat_input(200, profile(kind, n)))
    for kind in ("hot-center", "hot-left", "gradient")
    for n in (6, 12, 24)
] + [
    ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"",
                           encode_heat_input(201, profile("gradient", n)))
    for n in (8, 10, 16, 20)
]


def run_arm(tag, worker_limits):
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    cache = WarrantCache(OUT / f"cache-{tag}")
    sampler = RssSampler(); sampler.start()
    started = time.monotonic()
    report = prefetch_warrants(policy, SPECS, cache, OUT / f"proofs-{tag}",
                               lanes=default_lanes(), max_workers=4,
                               worker_limits=worker_limits)
    wall = time.monotonic() - started
    sampler.stop.set(); sampler.join()
    retried = sum(1 for o in report.outcomes if o.retried)
    ooms = sum(1 for o in report.outcomes
               if "host exited -9" in ((o.first_error or "") + (o.error or "")))
    print(f"arm {tag:12} proved {report.proved}/{report.planned}  "
          f"failed {report.failed}  retried {retried}  oom-events {ooms}")
    print(f"    wall {wall:6.1f}s  throughput {report.proved / wall * 60:5.2f} proofs/min  "
          f"peak/worker {sampler.peak_single/1024/1024:4.1f} GB  "
          f"aggregate peak {sampler.peak_aggregate/1024/1024:4.1f} GB")
    return report, wall


def main():
    print(f"=== STE STAGE 11 A/B: {len(SPECS)} identical fresh statements, 4 workers ===")
    a_report, a_wall = run_arm("A-uncapped", None)
    b_report, b_wall = run_arm("B-nexus<=2", {"nexus": 2})
    print(f"A vs B wall: {a_wall:.1f}s -> {b_wall:.1f}s "
          f"({100 * (1 - b_wall / a_wall):+.1f}% change; negative = B slower)")
    a_first_try = a_report.proved - sum(1 for o in a_report.outcomes if o.retried)
    b_first_try = b_report.proved - sum(1 for o in b_report.outcomes if o.retried)
    print(f"first-attempt successes: A {a_first_try}/{a_report.planned}  "
          f"B {b_first_try}/{b_report.planned}")


if __name__ == "__main__":
    main()
