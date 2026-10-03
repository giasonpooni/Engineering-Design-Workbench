"""Stage 11, part 1: the proof-manufacture memory/concurrency curve.

Genuinely NEW statements (inputs carrying a stage-11 marker never proven
before), fresh cache roots, no warrant hits, no verifier-artifact hits
-- this benchmarks MANUFACTURE, nothing else. RSS is sampled from /proc
every 0.5 s across all live prover processes; OOM kills arrive as
`host exited -9` and are counted, never explained away.

Output: throughput(concurrency, memory) for Nexus at c=1,2,3 over the
same three medium statements, plus single-prove baselines (time + peak
RSS + component split) for Nexus, RISC Zero and SP1.
"""

import os
import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.policy import VerificationPolicy, default_lanes
from campaign.prefetch import prefetch_warrants
from campaign.warrant_cache import WarrantCache
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage11-curve"))
OUT.mkdir(parents=True, exist_ok=True)

MARKER = 111_113  # stage-11 curve marker: makes every statement new


def heat_spec(kind: str, n: int, steps: int = 200) -> ExecutionSpecification:
    if kind == "hot-center":
        values = [MARKER] * (n // 2) + [1_000_000] + [MARKER] * (n - n // 2 - 1)
    else:
        values = [MARKER + int(1_000_000 * i / (n - 1)) for i in range(n)]
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(steps, values))


class RssSampler(threading.Thread):
    """Samples RSS of every live *-host process each 0.5 s."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.peak_single = 0      # largest single-process sample (KB)
        self.peak_aggregate = 0   # largest same-instant sum (KB)

    def run(self):
        while not self.stop.is_set():
            try:
                out = subprocess.run(
                    ["ps", "-o", "rss=,comm="], capture_output=True, timeout=5
                ).stdout.decode()
                samples = [int(line.split()[0]) for line in out.splitlines()
                           if line.strip() and line.split()[-1].endswith("-host")]
                if samples:
                    self.peak_single = max(self.peak_single, max(samples))
                    self.peak_aggregate = max(self.peak_aggregate, sum(samples))
            except Exception:
                pass
            self.stop.wait(0.5)


def run_curve_point(tag, specs, max_workers, worker_limits=None):
    cache = WarrantCache(OUT / f"cache-{tag}")
    sampler = RssSampler(); sampler.start()
    started = time.monotonic()
    kwargs = {}
    if worker_limits is not None:
        kwargs["worker_limits"] = worker_limits
    report = prefetch_warrants(
        VerificationPolicy(routine="nexus", independent=None, heavyweight=None),
        specs, cache, OUT / f"proofs-{tag}", lanes=default_lanes(),
        max_workers=max_workers, **kwargs)
    wall = time.monotonic() - started
    sampler.stop.set(); sampler.join()
    retried = sum(1 for o in report.outcomes if o.retried)
    ooms = sum(1 for o in report.outcomes
               if "host exited -9" in ((o.first_error or "") + (o.error or "")))
    print(f"  c={max_workers} {tag:12} proved {report.proved}/{report.planned} "
          f"(retried {retried}, oom-events {ooms})  wall {wall:6.1f}s  "
          f"throughput {report.proved / wall * 60:5.2f} proofs/min  "
          f"peak/worker {sampler.peak_single / 1024 / 1024:4.1f} GB  "
          f"aggregate {sampler.peak_aggregate / 1024 / 1024:4.1f} GB")
    return report, wall, sampler


def main():
    print("=== STE STAGE 11: MEMORY/CONCURRENCY CURVE (fresh statements) ===")

    # -- Nexus curve: the same THREE medium statements at c=1,2,3 -----
    # (fresh statement set per level -- separate inputs, separate cache
    # roots -- so no level ever hits another level's warrants)
    for level in (1, 2, 3):
        specs = [heat_spec("hot-center", n, steps=200 + level) for n in (6, 12, 24)]
        run_curve_point(f"nexus-c{level}", specs, level)

    # -- single-prove baselines for the other backends ----------------
    print("  -- single-prove baselines (c=1, fresh statements) --")
    r0_policy = VerificationPolicy(routine="risc0", independent=None, heavyweight=None)
    cache = WarrantCache(OUT / "cache-risc0")
    sampler = RssSampler(); sampler.start()
    t0 = time.monotonic()
    rep = prefetch_warrants(r0_policy, [heat_spec("gradient", 12, steps=207)],
                            cache, OUT / "proofs-risc0", max_workers=1)
    sampler.stop.set(); sampler.join()
    print(f"  risc0: proved {rep.proved}  wall {time.monotonic()-t0:6.1f}s  "
          f"peak {sampler.peak_single / 1024 / 1024:4.1f} GB")

    sp1_policy = VerificationPolicy(routine="sp1", independent=None, heavyweight=None)
    cache = WarrantCache(OUT / "cache-sp1")
    sampler = RssSampler(); sampler.start()
    t0 = time.monotonic()
    rep = prefetch_warrants(sp1_policy, [heat_spec("gradient", 12, steps=208)],
                            cache, OUT / "proofs-sp1", max_workers=1)
    sampler.stop.set(); sampler.join()
    print(f"  sp1  : proved {rep.proved}  wall {time.monotonic()-t0:6.1f}s  "
          f"peak {sampler.peak_single / 1024 / 1024:4.1f} GB")


if __name__ == "__main__":
    main()
