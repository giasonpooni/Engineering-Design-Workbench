"""Stage 8 warrant-reuse experiment -- MEASURED, not estimated.

Three arms over the IDENTICAL campaign the Stage 7 experiment ran
(9-cell sweep + 3 repeats + near-identical variant + escalation +
failure + retry + rejection), same policy identity, same deterministic
samples:

    arm A  policy, NO cache          -- re-measures the Stage 7 cost here
    arm B  policy + COLD cache       -- unique statements prove once,
                                        repeats hit and re-verify
    arm C  policy + WARM cache       -- the whole campaign re-runs on
                                        reused warrants; before it runs,
                                        one cached artifact is CORRUPTED
                                        (regenerate_invalid=True makes the
                                        recovery an explicit, recorded
                                        invalidate+reprove) and one NEW
                                        spec is appended (identity-based
                                        invalidation: changed statement =
                                        different key = miss)

Every hit still passes the backend verifier; the script separates
proving time from hit-verification overhead so the reuse win and its
cost are both measured. Evidence is asserted identical across all arms.
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
from campaign.warrant_cache import WarrantCache, statement_key
from execution.proving import default_nexus_host_path
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage8"))
OUT.mkdir(parents=True, exist_ok=True)
REPO = pathlib.Path(__file__).resolve().parent.parent

STAGE7_MEASURED_TOTAL_PROVING_S = 366.8  # the Stage 7 run's own measurement

POLICY = VerificationPolicy(routine="nexus", independent="risc0",
                            heavyweight="sp1",
                            independent_rate_bp=2500, heavyweight_rate_bp=800)

FRESH = (None, "miss+stored", "miss", "regenerated+stored")


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
        return REPO / "zk" / "artifacts" / "sp1-pairwise.elf"


SPEC_A = heat_spec(50, [0, 700_000, 1_000_000, 700_000, 0, 0])
SPEC_NEW = heat_spec(200, profile("gradient", 8))  # arm C only: a CHANGED statement


def build_points(runner, escalation_runner, include_new_spec=False):
    points, keys = [], set()
    for kind in ("hot-center", "hot-left", "gradient"):
        for n in (6, 12, 24):
            key = f"rod-{kind}-n{n}"; keys.add(key)
            points.append(CampaignPoint(key, "peak_temperature",
                                        heat_spec(200, profile(kind, n)), peak,
                                        runner=runner, label="policy"))
    keys.update({"rod-A", "rod-B", "rod-esc", "rod-fail", "rod-reject"})
    for _ in range(3):
        points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak,
                                    runner=runner, label="policy-repeat"))
    points.append(CampaignPoint("rod-B", "peak_temperature",
                                heat_spec(50, [0, 700_000, 1_000_001, 700_000, 0, 0]),
                                peak, runner=runner, label="policy"))
    points.append(CampaignPoint("rod-esc", "peak_temperature", SPEC_A, peak,
                                runner=escalation_runner, label="escalation"))
    points.append(CampaignPoint("rod-fail", "peak_temperature",
                                ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"bad"),
                                peak, runner=runner, label="fail-execution"))
    points.append(CampaignPoint("rod-fail", "peak_temperature", SPEC_A, peak,
                                runner=runner, label="retry"))
    points.append(CampaignPoint("rod-reject", "peak_temperature", SPEC_A,
                                lambda c, r: {"property": "wrong", "value": 1, "unit": "x"},
                                label="fail-rejected"))
    if include_new_spec:
        keys.add("rod-new")
        points.append(CampaignPoint("rod-new", "peak_temperature", SPEC_NEW, peak,
                                    runner=runner, label="changed-spec"))
    return points, sorted(keys)


def run_arm(name, cache, regenerate_invalid=False, include_new_spec=False):
    warrants: list[WarrantRecord] = []
    lanes = default_lanes()
    runner = policy_runner(POLICY, OUT, warrants, lanes=lanes,
                           cache=cache, regenerate_invalid=regenerate_invalid)
    esc_lanes = dict(lanes)
    esc_lanes["broken-nexus"] = WrongArtifactLane("nexus", default_nexus_host_path())
    esc_policy = VerificationPolicy(routine="broken-nexus", independent="nexus",
                                    heavyweight=None, independent_rate_bp=0)
    esc_runner = policy_runner(esc_policy, OUT, warrants, lanes=esc_lanes,
                               cache=cache, regenerate_invalid=regenerate_invalid)

    points, keys = build_points(runner, esc_runner, include_new_spec=include_new_spec)
    pool, doc = make_campaign_pool(keys)
    trace = OperationTrace()
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace, points)
    wall = time.monotonic() - t0
    return dict(name=name, warrants=warrants, pool=pool, trace=trace,
                report=report, wall=wall)


def summarize(arm):
    warrants, report, trace = arm["warrants"], arm["report"], arm["trace"]
    verified = [w for w in warrants if w.outcome == "verified"]
    proving = sum(w.seconds for w in verified if w.cache in FRESH)
    hits = [w for w in verified if w.cache == "hit"]
    hit_overhead = sum(w.seconds for w in hits)
    n_lookup = len([w for w in warrants
                    if w.cache in ("hit", "hit-invalid", "miss+stored", "miss")])
    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    by_cache = {}
    for w in warrants:
        by_cache[w.cache] = by_cache.get(w.cache, 0) + 1
    print(f"--- arm {arm['name']} ---")
    print(f"  executions {report.executions}  successes {report.successes}  "
          f"failures {report.failures} {report.failure_kinds}")
    print(f"  observations/unique {len(report.observation_ids)}/{report.unique_evidence}  "
          f"occurrences {len(trace.occurrences())} "
          f"(S={states.count(SUCCEEDED)} F={states.count(FAILED)} R={states.count(REJECTED)})")
    print(f"  warrant records by cache state: {by_cache}")
    print(f"  proof generations      : {len([w for w in verified if w.cache in FRESH])}"
          f"   proving time {proving:7.1f}s")
    print(f"  reused warrants (hits) : {len(hits)}"
          f"   hit-verify overhead {hit_overhead:7.1f}s")
    if n_lookup:
        rate = 100 * len([w for w in warrants if w.cache in ('hit', 'hit-invalid')]) / n_lookup
        print(f"  hit rate               : {rate:.0f}% of {n_lookup} lookups")
    print(f"  wall time              : {arm['wall']:.1f}s")
    return proving, hits, hit_overhead


def main():
    cache_root = OUT / "warrant-cache"

    arm_a = run_arm("A: policy, no cache", None)
    cache = WarrantCache(cache_root)
    arm_b = run_arm("B: policy + cold cache", cache)

    # before arm C: corrupt ONE cached artifact (rod-A's nexus warrant)
    key = statement_key("nexus", REPO / "zk" / "artifacts" / "nexus-heat.elf", SPEC_A)
    proof = cache_root / key / "proof.bin"
    raw = bytearray(proof.read_bytes()); raw[len(raw) // 2] ^= 0xFF
    proof.write_bytes(bytes(raw))
    print(f"[arm C setup] corrupted cached artifact for statement {key[:16]}")

    arm_c = run_arm("C: policy + warm cache (1 corrupted entry, 1 new spec)",
                    cache, regenerate_invalid=True, include_new_spec=True)

    print("=== STE STAGE 8 WARRANT-REUSE CAMPAIGN ===")
    print(f"policy identity {POLICY.identity()[:16]}   "
          f"stage-7 measured proving baseline {STAGE7_MEASURED_TOTAL_PROVING_S:.1f}s")
    prov_a, _, _ = summarize(arm_a)
    prov_b, hits_b, over_b = summarize(arm_b)
    prov_c, hits_c, over_c = summarize(arm_c)

    # evidence invariance across ALL arms (common prefix; arm C appends one new spec)
    ids_a, ids_b, ids_c = (a["report"].observation_ids for a in (arm_a, arm_b, arm_c))
    assert ids_a == ids_b, "arm B moved evidence"
    assert ids_c[:len(ids_a)] == ids_a, "arm C moved evidence"
    assert len(arm_a["pool"].fingerprint_history()) == len(arm_b["pool"].fingerprint_history())
    print("evidence invariance    : arm A == arm B == arm C (common points) -- CONFIRMED")

    avoided = len(hits_b) + len(hits_c)
    print(f"proof generations avoided (B+C) : {avoided}")
    print(f"hit-verification overhead (B+C) : {over_b + over_c:.1f}s total, "
          f"{(over_b + over_c) / max(avoided, 1):.1f}s per reused warrant")
    print(f"same-campaign reuse    : arm A proving {prov_a:.1f}s -> arm B proving {prov_b:.1f}s "
          f"({100 * (1 - prov_b / prov_a):.1f}% less proving)")
    print(f"cross-campaign reuse   : arm C proving {prov_c:.1f}s "
          f"({100 * (1 - prov_c / prov_a):.1f}% less than uncached; "
          f"remaining cost = corrupted-entry regeneration + new spec)")
    corr = [w for w in arm_c["warrants"] if w.cache in ("hit-invalid", "invalidated",
                                                        "regenerated+stored")]
    print("corruption recovery    : " + " -> ".join(w.cache for w in corr))


if __name__ == "__main__":
    main()
