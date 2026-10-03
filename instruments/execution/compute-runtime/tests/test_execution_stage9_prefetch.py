"""Stage 9 locks -- parallel warrant MANUFACTURE, unchanged trust.

The prefetcher may only ever add proof artifacts to the WarrantCache;
everything downstream of it -- hit verification, evidence admission,
occurrence recording, escalation -- is the unchanged Stage 8 machinery,
and these tests pin that the campaign after a prefetch is the campaign
without one, just faster.

Proof budget: 2 real Nexus proofs (manufactured concurrently in the
end-to-end test); everything else is proof-free.
"""

from __future__ import annotations

import pytest

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import (
    VerificationLane,
    VerificationPolicy,
    WarrantRecord,
    policy_runner,
)
from campaign.prefetch import plan_prefetch, prefetch_warrants
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import default_cli_path
from execution.proving import default_nexus_host_path
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)
from operations.trace import SUCCEEDED, OperationTrace
from tests.test_execution_stage8_warrant_cache import (
    NEXUS_ELF,
    NEXUS_OK,
    REPO,
    _instrumented_nexus,
    _peak,
    _single_lane_policy,
)

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)

SPEC_A = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"",
    encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]),
)
SPEC_B = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"",
    encode_heat_input(50, [0, 700_000, 1_000_001, 700_000, 0, 0]),
)


def test_plan_is_deterministic_and_deduplicates_statements():
    """The plan is a pure function of (policy, specs, lanes): repeated
    specs collapse to one task per statement, ordering is by statement
    key, and two calls agree exactly."""
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    lanes = {"nexus": VerificationLane("nexus", default_nexus_host_path())}
    plan = plan_prefetch(policy, [SPEC_A, SPEC_A, SPEC_B, SPEC_A], lanes)
    assert plan == plan_prefetch(policy, [SPEC_A, SPEC_A, SPEC_B, SPEC_A], lanes)
    assert len(plan) == 2, "three repeats of A and one B -> two statements"
    assert [t.key for t in plan] == sorted(t.key for t in plan)
    assert {t.spec.identity() for t in plan} == {SPEC_A.identity(), SPEC_B.identity()}


def test_failed_manufacture_stores_nothing_and_is_reported(tmp_path):
    """A lane whose artifact resolution is broken (wrong program's ELF,
    refused by the stage-5 registry gate) fails its task: the failure is
    on the prefetch report, the cache stays empty, and the campaign's
    inline semantics remain the fallback (locked by the stage-8 miss
    tests). Proof-free: the gate refuses before any proving."""
    class WrongArtifactLane(VerificationLane):
        def artifact_for(self, spec):
            return REPO / "zk" / "artifacts" / "sp1-pairwise.elf"

    lanes = {"nexus": WrongArtifactLane("nexus", default_nexus_host_path())}
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    cache = WarrantCache(tmp_path / "cache")
    report = prefetch_warrants(policy, [SPEC_A], cache, tmp_path, lanes=lanes)
    assert (report.planned, report.failed, report.proved) == (1, 1, 0)
    assert "not the reproducible-build artifact" in report.outcomes[0].error
    assert not any((tmp_path / "cache").iterdir()), "nothing stored"


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_prefetched_campaign_is_the_same_campaign_but_all_hits(tmp_path):
    """End to end with an instrumented host: prefetch manufactures the
    two planned statements (concurrently, `prove` x 2), then the
    3-point campaign runs entirely on hits (`verify` x 3, no new
    `prove`), with occurrences, observations, and observation ids
    identical to the never-cached baseline. The prefetcher touched no
    pool and no trace -- it is not even handed them."""
    shim, log = _instrumented_nexus(tmp_path)
    policy, lanes = _single_lane_policy(shim)
    cache = WarrantCache(tmp_path / "cache")

    report = prefetch_warrants(policy, [SPEC_A, SPEC_A, SPEC_B], cache,
                               tmp_path, lanes=lanes, max_workers=2)
    assert (report.planned, report.proved, report.failed) == (2, 2, 0)
    calls = log.read_text().split()
    assert calls.count("prove") == 2, "manufacture proved each statement once"
    # second prefetch over the same specs: everything already cached
    again = prefetch_warrants(policy, [SPEC_A, SPEC_B], cache, tmp_path, lanes=lanes)
    assert (again.planned, again.already_cached, again.proved) == (2, 2, 0)
    assert log.read_text().split().count("prove") == 2, "no re-manufacture"

    # baseline: same campaign, no verification anywhere
    pool0, doc0 = make_campaign_pool(["rod-A", "rod-B"])
    trace0 = OperationTrace()
    points0 = [
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak),
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak),
        CampaignPoint("rod-B", "peak_temperature", SPEC_B, _peak),
    ]
    plain = run_campaign(pool0, doc0.id, trace0, points0)

    # the prefetched campaign: unchanged seam, warm cache
    warrants: list[WarrantRecord] = []
    runner = policy_runner(policy, tmp_path, warrants, lanes=lanes, cache=cache)
    pool, doc = make_campaign_pool(["rod-A", "rod-B"])
    trace = OperationTrace()
    points = [
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak, runner=runner),
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak, runner=runner),
        CampaignPoint("rod-B", "peak_temperature", SPEC_B, _peak, runner=runner),
    ]
    proved = run_campaign(pool, doc.id, trace, points)

    assert proved.successes == 3
    assert [w.cache for w in warrants] == ["hit", "hit", "hit"]
    assert all(w.outcome == "verified" for w in warrants)
    assert len(trace.occurrences()) == 3
    assert all(trace.state_of(i) == SUCCEEDED for i in range(3))
    assert proved.unique_evidence == 2
    assert plain.observation_ids == proved.observation_ids, (
        "prefetch moved no evidence")
    final_calls = log.read_text().split()
    assert final_calls.count("prove") == 2, "the campaign generated NO proof"
    # 2 verifies during manufacture (prove_and_verify_result always
    # verifies what it just proved) + 3 mandatory hit re-verifications
    assert final_calls.count("verify") == 5, "every hit still re-verified"


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_transient_concurrent_failure_is_retried_serially_and_stays_visible(tmp_path):
    """The stage-9 experiment measured the concurrent pass losing
    provers to the OOM killer (`host exited -9`); the serial retry pass
    absorbs exactly that class of failure. Here the host shim fails its
    FIRST prove invocation and works afterwards: the outcome is
    `proved` with `retried=True` and the concurrent failure preserved
    in `first_error` -- self-healing, never silent."""
    log = tmp_path / "calls.log"
    marker = tmp_path / "failed-once"
    shim = tmp_path / "flaky-nexus"
    shim.write_text(
        f"#!/bin/bash\necho \"$1\" >> {log}\n"
        f"if [ \"$1\" = prove ] && [ ! -e {marker} ]; then touch {marker}; exit 1; fi\n"
        f"exec {default_nexus_host_path()} \"$@\"\n"
    )
    shim.chmod(0o755)
    lanes = {"nexus": VerificationLane("nexus", shim)}
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    cache = WarrantCache(tmp_path / "cache")

    report = prefetch_warrants(policy, [SPEC_A], cache, tmp_path, lanes=lanes)
    assert (report.planned, report.proved, report.failed) == (1, 1, 0)
    outcome = report.outcomes[0]
    assert outcome.retried, "the serial retry manufactured it"
    assert "host exited" in (outcome.first_error or ""), "the concurrent failure stays visible"
    assert cache.lookup(outcome.key) is not None, "the warrant exists"
    assert log.read_text().split().count("prove") == 2, "failed once, retried once"


def test_prefetch_skips_unavailable_lanes_explicitly(tmp_path):
    """A statement whose backend host is not built here is reported
    `unavailable` -- visible, never a quiet success, never a store."""
    import pathlib

    lanes = {"ghost": VerificationLane("nexus", pathlib.Path("/nonexistent/ghost"))}
    policy = VerificationPolicy(routine="ghost", independent=None, heavyweight=None)
    cache = WarrantCache(tmp_path / "cache")
    report = prefetch_warrants(policy, [SPEC_A], cache, tmp_path, lanes=lanes)
    assert (report.planned, report.unavailable, report.proved) == (1, 1, 0)
    assert not any((tmp_path / "cache").iterdir())


def test_worker_limits_cap_concurrent_manufacture_per_backend(tmp_path):
    """Stage 11: `worker_limits` gates how many provers for one backend
    run at once -- execution control only. The instrumented host logs
    start/end stamps; with limit 2 and four eager workers, no more than
    two prove invocations ever overlap. (The shim fails every prove --
    the failure semantics are untouched by the gate, and the retry pass
    runs serially by construction.)"""
    import time as _time

    log = tmp_path / "spans.log"
    shim = tmp_path / "slow-nexus"
    shim.write_text(
        "#!/bin/bash\n"
        f"if [ \"$1\" = prove ]; then\n"
        f"  echo \"start $(date +%s.%N)\" >> {log}\n"
        f"  sleep 0.6\n"
        f"  echo \"end $(date +%s.%N)\" >> {log}\n"
        f"  exit 1\nfi\nexit 1\n"
    )
    shim.chmod(0o755)
    lanes = {"nexus": VerificationLane("nexus", shim)}
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    specs = [
        ExecutionSpecification(
            HEAT_DIFFUSION_DESCRIPTOR, b"",
            encode_heat_input(50, [0, 700_000, 1_000_000 + i, 700_000, 0, 0]))
        for i in range(4)
    ]
    report = prefetch_warrants(policy, specs, WarrantCache(tmp_path / "cache"),
                               tmp_path, lanes=lanes, max_workers=4,
                               worker_limits={"nexus": 2})
    assert (report.planned, report.failed) == (4, 4), "gate changes WHEN, never WHAT"

    events = []
    for line in log.read_text().splitlines():
        kind, stamp = line.split()
        events.append((float(stamp), 1 if kind == "start" else -1))
    concurrent = peak = 0
    for _, delta in sorted(events):
        concurrent += delta
        peak = max(peak, concurrent)
    assert peak <= 2, f"the memory gate held: peak concurrency {peak}"
    assert len(events) == 16, "4 concurrent attempts + 4 serial retries, all on the log"
