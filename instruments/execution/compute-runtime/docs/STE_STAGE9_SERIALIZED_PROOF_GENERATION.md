# Scientific Computation Runtime Stage 9 — Serialized Proof Generation

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
## The measured bottleneck

Stage 8's three-arm campaign located the remaining cost precisely:
proving was **99.6% / 99.9% / 96%** of wall time in its uncached,
cold-cache and warm-cache arms, while every other component measured in
this environment is noise — native execution **1.9 ms**, statement key
**0.1 ms**, cache store **0.6 ms**, cache lookup **30 µs**, hit
re-verification **~0.12 s**. Warrant reuse had already removed the
*redundant* statements; what remained was proving **genuinely new**
statements — strictly serially, on a machine measured to have idle
capacity: one Nexus prover consumes ~36 CPU-seconds at **1.36 cores**
of the 4 available, and concurrent proving measured **×1.52** (2
workers) and **×2.33** (4 workers) over serial. Serialized proof
generation on a half-idle machine was the bottleneck — computed from
the run, not assumed.

## The mechanism: `campaign/prefetch.py`

Parallel warrant **manufacture**, never parallel trust:

    plan    = plan_prefetch(policy, specs, lanes)   -- pure function,
              deduplicated by statement key, statement-key order
    workers = N concurrent (native run -> prove_and_verify_result -> store)
    output  = WarrantCache entries: content-addressed proof BYTES

The campaign then runs **unchanged** — same seam, same records (modulo
cache-state), same evidence — it just finds the proofs already
manufactured, and every hit still passes `verify_existing_proof`
mandatorily. The prefetcher is not handed the EvidencePool or the
OperationTrace (structurally: not parameters), creates no
WarrantRecords, and a failed task simply leaves its key absent — the
campaign's inline semantics (miss → prove fresh, or fail attributably)
are the fallback, so prefetch can only ever add artifacts, never
subtract behavior. Its native runs are warrant manufacture (like the
zkVM guest's own re-execution), not scientific dispatches: no
occurrence, no evidence.

## What the first run discovered, and the fix

The first optimized run (4 workers) lost 3 tasks with `host exited -9`:
the kernel's OOM killer — a Nexus prover peaks at **~8.5 GB RSS**, and
four concurrent provers exceeded the 16 GB cgroup. **Memory, not CPU,
is the binding constraint on prover concurrency here.** The failure
semantics held (the campaign proved those statements inline; nothing
was lost), but the win shrank. The smallest genuine fix: a **serial
retry pass** inside `prefetch_warrants` — a task that failed
concurrently gets one attempt with the machine to itself, recorded as
`retried=True` with the concurrent failure preserved in `first_error`.
A genuine failure (bad spec, registry-gate refusal) fails again fast
and stays failed. Self-healing, never silent; locked by a test with a
deliberately once-flaky host.

## Measured results (same 17-point campaign, same policy identity as Stage 8)

| | arm A (Stage 8, uncached serial) | arm B (Stage 8, cold cache serial) | Stage 9: prefetch + campaign |
|---|---|---|---|
| proof generations | 16 | 12 | 12 (3 on the retry pass) + 0 in campaign |
| proving / prefetch wall | 501.8 s | 402.5 s | **290.1 s** (564.0 s of proof time at ×1.94) |
| campaign wall | 502.1 s | 403.0 s | **2.3 s** (16 hits, 2.2 s re-verification) |
| **total** | **502.1 s** | **403.0 s** | **292.4 s** |

- **41.8% faster than the uncached baseline; 27.5% faster than serial
  cold-cache** — measured in-run against the same workload on the same
  machine.
- Effective concurrency **×1.94** including the serial retries (×2.39
  when memory allowed all 4 workers).
- Campaign evidence **asserted identical** to a no-verification
  baseline of the same points: 15/11 observations/unique, 17
  occurrences (15 SUCCEEDED / 1 FAILED / 1 REJECTED) — unchanged from
  every Stage 8 arm.
- The deliberately bad specification failed in prefetch (`execution
  halted (exit 2)`) and again inline — refused twice, warranted never.

## Epistemic status

**MEASURED**: every number above; the OOM kills and their retry
recovery; `prove` × 2 / `verify` × 5 host-call counts in the
instrumented end-to-end test; evidence invariance.

**STRUCTURALLY GUARANTEED**: prefetch cannot touch evidence or
occurrences (no access); nothing consumes a prefetched artifact except
through the Stage 8 mandatory hit re-verification; the plan is a pure
function of (policy, specs, lanes); worker completion order is
invisible downstream (content-addressed artifacts, identity-driven
decisions).

**CALLER-DECLARED**: `max_workers` (default: cpu count, measured best
here); which specs to prefetch.

**EXTERNALLY UNVERIFIABLE**: unchanged from Stage 8 — physical
measurement claims (none made), zkVM soundness, filesystem integrity
between verifications (why every hit re-verifies).

## Remaining bottleneck (measured, for the next stage to consume)

With reuse and parallel manufacture in place, campaign cost is now
**the irreducible first proof of each genuinely new statement**, bounded
below by prover memory (~8.5 GB/worker limits this machine to ~2 safe
concurrent Nexus provers) and by the per-statement proving times of the
ladder itself (Nexus ~20–50 s, RISC Zero ~65 s, SP1 ~300 s). Reducing
it further means either more memory, cheaper provers, or proving fewer
new statements — a policy/scientific choice, not an orchestration one.
