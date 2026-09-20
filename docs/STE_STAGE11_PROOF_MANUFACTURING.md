# Scientific Computation Runtime Stage 11 — Proof-Manufacturing Throughput

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
Stage 10 left one dominant cost: the first proof of each genuinely new
statement. Stage 11 measured that cost's real shape — time, memory,
concurrency, failure — and built the smallest control the measurements
justified.

## Fresh-statement baselines (measured; new inputs, fresh caches, no hits)

| backend | prove wall (medium heat statement) | peak sampled RSS |
|---|---|---|
| Nexus | 15–50 s (3 mixed statements: 64.5 s serial) | **2.6–10.1 GB — statement-size dependent** (n=24 cell = 10.1 GB) |
| RISC Zero | 66.6 s | **1.3 GB** |
| SP1 | 216.2 s | 9.6 GB |

Two assumptions died by measurement: prover memory is **not** a
per-backend constant (Nexus varies ~4× with statement size), and cost
does **not** imply memory (RISC Zero is the slowest of the cheap lanes
*and* the lightest by far — a RISC Zero prover can co-run with almost
anything).

## The concurrency curve (Nexus, same 3 mixed statements per level)

| concurrency | proved | OOM events | wall | throughput | aggregate RSS peak |
|---|---|---|---|---|---|
| 1 | 3/3 | 0 | 64.5 s | 2.79 proofs/min | 10.1 GB |
| 2 | 3/3 | 0 | 61.8 s | 2.91 proofs/min | 12.7 GB |
| 3 | 3/3 | 0 | 61.6 s | 2.92 proofs/min | 12.5 GB |

The honest reading: for a mixed-size set the wall is the **critical
path of the biggest statement**, and small proofs hide inside it —
concurrency neither helps much nor OOMs, because only one ~10 GB
statement is in flight. Memory binds exactly when **multiple big
statements co-schedule** (Stage 9's uncapped failure: three n=24-class
statements at 4 workers → `host exited -9`). `throughput(concurrency,
memory)` is therefore a function of the statement-size mix, not of
worker count alone.

## The mechanism: per-backend worker limits (the smallest that fits)

`prefetch_warrants(..., worker_limits={"nexus": 2, "risc0": 2,
"sp1": 1})` — per-backend semaphores at the boundary that already
schedules manufacture. Execution control only: statement, computation,
proof and evidence identities, the failure taxonomy (prover failure vs
verification failure vs unavailable backend, each already distinct in
records), and the serial-retry backstop are untouched. Locked by an
instrumented-overlap test: four eager workers under limit 2 never
exceeded two concurrent proves, and every gated failure stayed on the
record. No scheduler abstraction, no queue framework, no cluster
manager. A measured residual is stated rather than hidden: per-backend
caps do not gate **across** backends (nexus-big + SP1 ≈ 19.7 GB exceeds
the machine); the retry pass remains the backstop for that co-scheduled
worst case.

## A/B: uncapped vs memory-aware (13 identical fresh statements, 4 workers)

<!-- STAGE11_AB -->

## The throughput campaign

<!-- STAGE11_CAMPAIGN -->

## First-proof deduplication (§9, ruled out empirically)

The plan is deduplicated by statement key (Stage 9 lock:
`plan_is_deterministic_and_deduplicates_statements`), repeats hit the
warrant cache, and the campaign's counters above show planned
statements == proof generations with repeats contributing zero extra
manufacture. No duplicate first-proofs remain; nothing new was built
for this.

## Backend-aware policy (§6/§10, decided from measurement)

Post-Stage-10, verification costs are 0.05–0.8 s across the ladder —
too small to move any warrant decision — and proving cost already
drives the Stage 7 role assignment (routine=cheap, independent=middle,
heavyweight=expensive), which the measured ladder still matches.
Memory is a property of **when** a proof is manufactured, not of what a
warrant means, so it enters the prefetcher's limits and stays out of
`VerificationPolicy`. The policy is unchanged and content-addressed as
before; no second policy mechanism exists.

## CUDA (§14, investigated, not built)

CPU proving is measured as the dominant cost and is memory-bound. Both
forks expose GPU acceleration behind the existing backend boundary
(sp1-sdk `cuda` feature + cuda client builder; risc0 `cuda` feature) —
a backend-implementation change, not an architectural one. This
environment has no GPU (`/dev/nvidia*` absent), so the smallest
empirical probe is hardware-deferred; no CUDA abstraction was created.

## Claim classification

**MEASURED**: every number above — baselines, RSS profiles, the
concurrency curve, OOM behavior, the A/B outcome, campaign counters,
dedup counts.

**STRUCTURALLY GUARANTEED**: worker limits change scheduling only (the
gate wraps manufacture; identity code paths are untouched); resource
telemetry lives in scripts/reports and has no path into Observation,
ExperimentalResult, or pool fingerprints; a gated failure is the same
failure it always was.

**CALLER-DECLARED**: the limit values themselves (derived from measured
classes, but chosen); which statements a campaign proves.

**EXTERNALLY UNVERIFIABLE**: prover-internal memory behavior beyond
sampled RSS; that the forks' CUDA paths preserve proving semantics
(unexercised here — no hardware).
