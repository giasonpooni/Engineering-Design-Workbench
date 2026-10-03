"""Stage 9 experiment -- parallel warrant manufacture, MEASURED.

The Stage 8 campaign measured (same machine, same 17-point workload,
same policy identity):

    arm A  uncached, serial proving      502.1 s wall / 501.8 s proving
    arm B  cold cache, serial proving    403.0 s wall / 402.5 s proving

This script runs the OPTIMIZED form: `prefetch_warrants` manufactures
the deduplicated planned statements concurrently (workers = cpu count;
measured prover concurrency on this box: x1.52 with 2 workers, x2.33
with 4), then the identical campaign runs through the unchanged seam on
the warm cache. Evidence is asserted against a no-verification baseline
run of the same points.
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.driver import make_campaign_pool, run_campaign
from campaign.policy import (
    VerificationPolicy, WarrantRecord, default_lanes, policy_runner,
)
from campaign.prefetch import prefetch_warrants
from campaign.warrant_cache import WarrantCache
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace
from scripts.stage8_warrant_campaign import POLICY, build_points

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage9"))
OUT.mkdir(parents=True, exist_ok=True)

ARM_A_WALL, ARM_A_PROVING = 502.1, 501.8   # stage-8 measured, same workload
ARM_B_WALL, ARM_B_PROVING = 403.0, 402.5


def main():
    cache = WarrantCache(OUT / "warrant-cache")
    lanes = default_lanes()

    # the provable specs are exactly the campaign points' specs; the
    # planner dedups statements and applies the policy's own sampling.
    probe_points, keys = build_points(None, None)
    specs = [p.spec for p in probe_points if p.label not in ("fail-rejected",)]

    t0 = time.monotonic()
    pre = prefetch_warrants(POLICY, specs, cache, OUT, lanes=lanes)
    prefetch_wall = time.monotonic() - t0

    # identical campaign, unchanged seam, warm cache
    warrants: list[WarrantRecord] = []
    runner = policy_runner(POLICY, OUT, warrants, lanes=lanes, cache=cache)
    esc_lanes = dict(lanes)
    from execution.proving import default_nexus_host_path
    from scripts.stage8_warrant_campaign import WrongArtifactLane
    esc_lanes["broken-nexus"] = WrongArtifactLane("nexus", default_nexus_host_path())
    esc_policy = VerificationPolicy(routine="broken-nexus", independent="nexus",
                                    heavyweight=None, independent_rate_bp=0)
    esc_runner = policy_runner(esc_policy, OUT, warrants, lanes=esc_lanes, cache=cache)
    points, keys = build_points(runner, esc_runner)
    pool, doc = make_campaign_pool(keys)
    trace = OperationTrace()
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace, points)
    campaign_wall = time.monotonic() - t0

    # evidence baseline: the same points, no verification at all
    plain_points, plain_keys = build_points(None, None)
    plain_pool, plain_doc = make_campaign_pool(plain_keys)
    plain = run_campaign(plain_pool, plain_doc.id, OperationTrace(), plain_points)

    total = prefetch_wall + campaign_wall
    hits = [w for w in warrants if w.cache == "hit"]
    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    by_cache = {}
    for w in warrants:
        by_cache[w.cache] = by_cache.get(w.cache, 0) + 1

    print("=== STE STAGE 9 PREFETCH CAMPAIGN ===")
    print(f"policy identity        : {POLICY.identity()[:16]}  workers {os.cpu_count()}")
    retried = sum(1 for o in pre.outcomes if o.retried)
    print(f"prefetch               : planned {pre.planned}  proved {pre.proved} "
          f"(of which {retried} on the serial retry pass)  "
          f"already-cached {pre.already_cached}  failed {pre.failed}")
    for o in pre.outcomes:
        if o.retried:
            print(f"    retried {o.backend} {o.key[:12]}: concurrent pass saw: {o.first_error}")
        elif o.outcome == "failed":
            print(f"    failed  {o.backend} {o.key[:12]}: {o.error}")
    print(f"prefetch wall          : {prefetch_wall:.1f}s  "
          f"(sum of individual proof times {pre.proving_seconds:.1f}s -> "
          f"concurrency x{pre.proving_seconds / max(prefetch_wall, 1e-9):.2f})")
    print(f"campaign               : executions {report.executions}  successes {report.successes}  "
          f"failures {report.failures} {report.failure_kinds}")
    print(f"observations/unique    : {len(report.observation_ids)}/{report.unique_evidence}  "
          f"occurrences {len(trace.occurrences())} "
          f"(S={states.count(SUCCEEDED)} F={states.count(FAILED)} R={states.count(REJECTED)})")
    print(f"warrants by cache state: {by_cache}")
    print(f"campaign wall          : {campaign_wall:.1f}s  "
          f"(hit re-verification {sum(w.seconds for w in hits):.1f}s over {len(hits)} hits)")
    assert plain.observation_ids == report.observation_ids, "prefetch moved evidence"
    print("evidence invariance    : prefetched campaign == unverified baseline -- CONFIRMED")
    print(f"TOTAL (prefetch+campaign): {total:.1f}s")
    print(f"vs arm A (uncached serial)   {ARM_A_WALL:.1f}s  -> {100 * (1 - total / ARM_A_WALL):.1f}% faster")
    print(f"vs arm B (cold-cache serial) {ARM_B_WALL:.1f}s  -> {100 * (1 - total / ARM_B_WALL):.1f}% faster")


if __name__ == "__main__":
    main()
