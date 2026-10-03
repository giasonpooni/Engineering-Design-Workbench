"""Stage 7 policy experiment -- the proof-cost dial, measured on a real
campaign larger than Stage 6's.

Every provable point is executed ONCE and verified per the policy:
routine Nexus on everything, deterministic RISC Zero independent samples,
deterministic SP1 heavyweight samples, plus one genuine escalation
(a broken routine lane) and the usual failure/retry/rejection points.
Prints the quantitative comparison against the prove-everything-with-SP1
baseline.
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import (
    VerificationLane, VerificationPolicy, WarrantRecord, default_lanes, policy_runner,
)
from execution.proving import default_nexus_host_path
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage7"))
OUT.mkdir(parents=True, exist_ok=True)

SP1_MEASURED_BASELINE_S = 299.0  # stage-6 measured CPU core proof, used
                                 # only if no heavyweight sample is drawn


def heat_spec(steps, values):
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(steps, list(values))
    )


def peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


def profile(kind, n):
    if kind == "hot-center":
        return [0] * (n // 2) + [1_000_000] + [0] * (n - n // 2 - 1)
    if kind == "hot-left":
        return [1_000_000, 800_000] + [0] * (n - 2)
    return [int(1_000_000 * i / (n - 1)) for i in range(n)]


class WrongArtifactLane(VerificationLane):
    def artifact_for(self, spec):
        return pathlib.Path(__file__).resolve().parent.parent / "zk" / "artifacts" / "sp1-pairwise.elf"


def main():
    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="nexus", independent="risc0",
                                heavyweight="sp1",
                                independent_rate_bp=2500, heavyweight_rate_bp=800)
    lanes = default_lanes()
    verified_runner = policy_runner(policy, OUT, warrants, lanes=lanes)

    # an escalation lane-set: broken routine, honest independent
    esc_lanes = dict(lanes)
    esc_lanes["broken-nexus"] = WrongArtifactLane("nexus", default_nexus_host_path())
    esc_policy = VerificationPolicy(routine="broken-nexus", independent="nexus",
                                    heavyweight=None, independent_rate_bp=0)
    escalation_runner = policy_runner(esc_policy, OUT, warrants, lanes=esc_lanes)

    points, keys = [], set()
    for kind in ("hot-center", "hot-left", "gradient"):
        for n in (6, 12, 24):
            key = f"rod-{kind}-n{n}"; keys.add(key)
            points.append(CampaignPoint(key, "peak_temperature",
                                        heat_spec(200, profile(kind, n)), peak,
                                        runner=verified_runner, label="policy"))
    SPEC_A = heat_spec(50, [0, 700_000, 1_000_000, 700_000, 0, 0])
    keys.update({"rod-A", "rod-B", "rod-esc", "rod-fail", "rod-reject"})
    for _ in range(3):
        points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak,
                                    runner=verified_runner, label="policy-repeat"))
    points.append(CampaignPoint("rod-B", "peak_temperature",
                                heat_spec(50, [0, 700_000, 1_000_001, 700_000, 0, 0]),
                                peak, runner=verified_runner, label="policy"))
    points.append(CampaignPoint("rod-esc", "peak_temperature", SPEC_A, peak,
                                runner=escalation_runner, label="escalation"))
    # failure + retry + rejection
    points.append(CampaignPoint("rod-fail", "peak_temperature",
                                ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"bad"),
                                peak, runner=verified_runner, label="fail-execution"))
    points.append(CampaignPoint("rod-fail", "peak_temperature", SPEC_A, peak,
                                runner=verified_runner, label="retry"))
    points.append(CampaignPoint("rod-reject", "peak_temperature", SPEC_A,
                                lambda c, r: {"property": "wrong", "value": 1, "unit": "x"},
                                label="fail-rejected"))

    pool, doc = make_campaign_pool(sorted(keys))
    trace = OperationTrace()
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace, points)
    wall = time.monotonic() - t0

    by_backend = {}
    for w in warrants:
        by_backend.setdefault((w.backend, w.outcome), []).append(w.seconds)
    total_proving = sum(w.seconds for w in warrants if w.outcome == "verified")
    provable_successes = len([w for w in warrants if w.role == "routine" and w.outcome == "verified"]) \
        + len([w for w in warrants if w.role.startswith("escalated") and w.outcome == "verified"])
    sp1_samples = [w.seconds for w in warrants if w.backend == "sp1" and w.outcome == "verified"]
    sp1_unit = sp1_samples[0] if sp1_samples else SP1_MEASURED_BASELINE_S
    baseline = provable_successes * sp1_unit
    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]

    print("=== STE STAGE 7 POLICY CAMPAIGN ===")
    print(f"policy identity        : {policy.identity()[:16]}")
    print(f"executions             : {report.executions}  successes: {report.successes}  "
          f"failures: {report.failures} {report.failure_kinds}")
    print(f"observations / unique  : {len(report.observation_ids)} / {report.unique_evidence}")
    print(f"trace occurrences      : {len(trace.occurrences())}  "
          f"states SUCCEEDED={states.count(SUCCEEDED)} FAILED={states.count(FAILED)} "
          f"REJECTED={states.count(REJECTED)}")
    print(f"evidence fingerprints  : {len(pool.fingerprint_history())}")
    print("warrants by (backend, outcome):")
    for (backend, outcome), secs in sorted(by_backend.items()):
        print(f"    {backend:14} {outcome:12} n={len(secs):2}  total {sum(secs):7.1f}s")
    verified_specs = {w.spec_identity for w in warrants if w.outcome == "verified"}
    independent = {w.spec_identity for w in warrants
                   if w.outcome == "verified" and w.role in ("independent", "heavyweight")
                   or w.role.startswith("escalated") and w.outcome == "verified"}
    print(f"verification coverage  : {len(verified_specs)} specs warranted; "
          f"{len(independent)} with independent/second-system coverage")
    print(f"total proving time     : {total_proving:.1f}s")
    print(f"baseline (all-SP1)     : {provable_successes} x {sp1_unit:.0f}s = {baseline:.0f}s")
    print(f"PROOF-COST REDUCTION   : {100 * (1 - total_proving / baseline):.1f}%")
    print(f"campaign wall time     : {wall:.1f}s")


if __name__ == "__main__":
    main()
