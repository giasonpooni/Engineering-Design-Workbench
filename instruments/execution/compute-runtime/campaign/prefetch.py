"""Warrant prefetch: parallel proof MANUFACTURE, never parallel trust.

Stage 8 measured where campaign time goes once warrants are reusable:
proving genuinely new statements is >96% of wall in every arm, it runs
strictly serially, and one Nexus prover uses only ~half of this
machine. The reducible cost left is therefore not WHAT we prove but
WHEN: independent statements can be proven concurrently.

This module is deliberately upstream of everything trusted:

    plan      = pure function of (policy identity, points, lanes)
    workers   = N concurrent (native run -> prove -> host verify -> store)
    output    = WarrantCache entries -- content-addressed BYTES

and nothing else. The prefetcher:

  - never touches EvidencePool or OperationTrace (structurally: it is
    not handed them);
  - never creates WarrantRecords (records belong to the campaign's own
    dispatches);
  - never lets anything consume its artifacts without the Stage 8 gate:
    a campaign hit on a prefetched warrant still goes through
    `verify_existing_proof`, mandatorily, like any other hit.

So the campaign after a prefetch is byte-for-byte the campaign without
one -- same seam, same records modulo cache-state, same evidence -- it
just finds the proofs already manufactured.

The native execution a worker runs to build the statement is warrant
manufacture (exactly like the zkVM guest's own re-execution of the
computation), not a scientific dispatch: it produces no occurrence and
no evidence. The campaign's dispatch remains the only place occurrences
and observations come from.

Failure semantics: a failed task is REPORTED and its key left absent --
the campaign then handles that statement through the unchanged inline
semantics (miss -> prove fresh, or fail the lane attributably). Prefetch
can therefore only ever add artifacts, never subtract behavior.

Determinism: the PLAN is deterministic (same policy, points and lanes
-> same task set, in statement-key order). Worker completion order is
not, and nothing downstream can see it: artifacts are content-addressed
and the campaign's decisions read only (policy, spec) identities.
"""

from __future__ import annotations

import os
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional

from campaign.policy import VerificationPolicy, default_lanes
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import run_specification
from execution.proving import (
    ProvedRunError,
    ProvingUnavailable,
    prove_and_verify_result,
)


@dataclass(frozen=True)
class PrefetchTask:
    """One statement to manufacture: lane + spec, keyed."""

    key: str
    lane_name: str
    spec: object  # ExecutionSpecification


@dataclass(frozen=True)
class PrefetchOutcome:
    key: str
    backend: str
    spec_identity: str
    outcome: str  # proved | already-cached | unavailable | failed
    seconds: float
    error: Optional[str] = None
    #: True when the CONCURRENT attempt failed and the serial retry pass
    #: manufactured the warrant; `first_error` keeps the concurrent
    #: failure visible (measured cause on this machine class: the
    #: prover's ~8.5 GB peak RSS OOM-killing under 4-way concurrency --
    #: memory, not CPU, is the binding constraint, and the retry pass
    #: makes the degradation self-healing without hiding it).
    retried: bool = False
    first_error: Optional[str] = None


@dataclass
class PrefetchReport:
    """Manufacture accounting. Data about a run -- never evidence, never
    a warrant record."""

    planned: int = 0
    proved: int = 0
    already_cached: int = 0
    unavailable: int = 0
    failed: int = 0
    wall_seconds: float = 0.0
    outcomes: List[PrefetchOutcome] = field(default_factory=list)

    @property
    def proving_seconds(self) -> float:
        return sum(o.seconds for o in self.outcomes if o.outcome == "proved")


def plan_prefetch(policy: VerificationPolicy, specs,
                  lanes: Optional[dict] = None) -> List[PrefetchTask]:
    """The deterministic task set: every (role-planned lane, spec) the
    policy would attempt for these specs, deduplicated by statement key,
    in statement-key order. A pure function of its inputs plus the
    registered artifacts the lanes resolve."""
    lanes = lanes if lanes is not None else default_lanes()
    tasks = {}
    for spec in specs:
        for _role, lane_name in policy.planned_roles(spec):
            lane = lanes.get(lane_name)
            if lane is None:
                continue
            artifact = lane.artifact_for(spec)
            if artifact is None or not artifact.exists():
                continue
            key = statement_key(lane.name, artifact, spec)
            tasks.setdefault(key, PrefetchTask(key, lane_name, spec))
    return [tasks[k] for k in sorted(tasks)]


def prefetch_warrants(
    policy: VerificationPolicy,
    specs,
    cache: WarrantCache,
    proof_dir: pathlib.Path,
    lanes: Optional[dict] = None,
    max_workers: Optional[int] = None,
    worker_limits: Optional[dict] = None,
) -> PrefetchReport:
    """Manufacture the planned warrants concurrently. Each worker runs
    the full existing pipeline -- native execution, real proof, host
    recomputation and verification (`prove_and_verify_result`, with the
    Stage 5 registry gate) -- and stores the proof BYTES under the
    statement key. Nothing is trusted here and nothing is recorded
    anywhere but this report.

    Stage 11: `worker_limits` caps CONCURRENT MANUFACTURE per backend
    ({lane name: max simultaneous provers}) -- the smallest memory-aware
    control, at the boundary that already schedules work. Provers are
    memory-bound, not CPU-bound, on this machine class (stage 9/11
    measured ~7-9 GB peak RSS per prover against a 16 GB cgroup), so an
    uncapped pool loses workers to the OOM killer and pays the serial
    retry pass. The limit controls WHEN a proof is manufactured and
    nothing else: statement, computation, proof and evidence identities,
    and every failure semantic, are exactly as without it."""
    import threading

    lanes = lanes if lanes is not None else default_lanes()
    # measured on this class of machine (stage 9): one prover uses ~1.4
    # cores, and workers == cpu_count gave the best throughput (x2.33
    # over serial on 4 cores); the default follows the machine.
    max_workers = max_workers or (os.cpu_count() or 2)
    gates = {name: threading.Semaphore(max(1, count))
             for name, count in (worker_limits or {}).items()}
    tasks = plan_prefetch(policy, specs, lanes)
    report = PrefetchReport(planned=len(tasks))
    proof_dir.mkdir(parents=True, exist_ok=True)
    started_all = time.monotonic()

    def _work(task: PrefetchTask) -> PrefetchOutcome:
        gate = gates.get(task.lane_name)
        if gate is not None:
            with gate:
                return _manufacture(task)
        return _manufacture(task)

    def _manufacture(task: PrefetchTask) -> PrefetchOutcome:
        lane = lanes[task.lane_name]
        started = time.monotonic()
        if cache.lookup(task.key) is not None:
            # leave verification to the consumption boundary -- the
            # campaign hit re-verifies mandatorily either way.
            return PrefetchOutcome(task.key, lane.name, task.spec.identity(),
                                   "already-cached", time.monotonic() - started)
        if not lane.available_for(task.spec):
            return PrefetchOutcome(task.key, lane.name, task.spec.identity(),
                                   "unavailable", time.monotonic() - started)
        try:
            native = run_specification(task.spec)
            if native.status != "completed":
                raise ProvedRunError(
                    f"execution halted (exit {native.exit_code}); no statement to prove"
                )
            proof_out = proof_dir / f"prefetch-{task.key[:16]}.bin"
            proved = prove_and_verify_result(
                native, task.spec, proof_out, lane.host_path,
                lane.artifact_for(task.spec),
            )
        except (ProvedRunError, ProvingUnavailable) as error:
            return PrefetchOutcome(task.key, lane.name, task.spec.identity(),
                                   "failed", time.monotonic() - started,
                                   error=str(error)[:300])
        cache.store(task.key, pathlib.Path(proved.proof_path).read_bytes(),
                    lane.name, task.spec.identity())
        return PrefetchOutcome(task.key, lane.name, task.spec.identity(),
                               "proved", time.monotonic() - started)

    if tasks:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            report.outcomes = list(pool.map(_work, tasks))
        # serial retry pass: a task that failed CONCURRENTLY (on this
        # machine class: the prover OOM-killed under memory pressure)
        # gets one attempt with the machine to itself. A genuine
        # failure (bad spec, gate refusal) simply fails again, fast,
        # and stays failed -- nothing is hidden, `first_error` records
        # what the concurrent pass saw.
        for at, outcome in enumerate(report.outcomes):
            if outcome.outcome != "failed":
                continue
            retry = _work(tasks[at])
            if retry.outcome == "proved":
                report.outcomes[at] = PrefetchOutcome(
                    retry.key, retry.backend, retry.spec_identity, "proved",
                    retry.seconds, retried=True, first_error=outcome.error,
                )
    for outcome in report.outcomes:
        if outcome.outcome == "proved":
            report.proved += 1
        elif outcome.outcome == "already-cached":
            report.already_cached += 1
        elif outcome.outcome == "unavailable":
            report.unavailable += 1
        else:
            report.failed += 1
    report.wall_seconds = time.monotonic() - started_all
    return report
