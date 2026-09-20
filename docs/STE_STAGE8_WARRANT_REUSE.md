# Scientific Computation Runtime Stage 8 — Warrant Reuse / Proof Artifact Cache

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
Stage 7 measured its own next bottleneck: routine Nexus proving was
301.8 s of the campaign's 366.8 s total proving time, and 5 of its 15
routine proofs re-proved a statement **identical** to one already
proven. A proof is a portable artifact; an identical statement can
reuse it. Stage 8 builds that reuse — under one non-negotiable rule:

> **A cached proof is NOT trusted because it is cached.**
> cache hit → retrieve bytes → backend verifier → `VerifiedExecution`.
> The cache contains **bytes, not trust**.

## What was built (the smallest superset)

| Piece | Where | Responsibility |
|---|---|---|
| `statement_key` | `campaign/warrant_cache.py` | identity of the *statement* a proof answers |
| `WarrantCache` | `campaign/warrant_cache.py` | store / lookup / explicit invalidate of proof **bytes** |
| `verify_existing_proof` | `execution/proving.py` | the verify-only gate every hit must pass — no proving anywhere in this path |
| cache-aware dispatch | `campaign/policy.py::policy_runner` | hit → mandatory re-verify; miss → prove + store; hit-invalid → recorded failure, regeneration only as an explicit decision |

Nothing else changed. `EvidencePool`, `Observation`/`ExperimentalResult`
identity, `ExecutionSpecification`, `OperationTrace`, the `ProofBackend`
contract, and `VerifiedExecution` semantics are untouched; the `crates/`
workspace gained no dependency.

## The statement key

```
commit( scout.campaign.warrant-statement.v1,
        [ backend name, sha256(guest artifact), specification identity ] )
```

- **Specification identity** covers program descriptor, configuration,
  and input — change any of them and the key changes (identity-based
  invalidation; there is no other kind except the one explicit
  `invalidate`).
- **Guest artifact hash** ties the warrant to the Stage 5 reproducible
  build actually verified — a rebuilt or different ELF is a different
  statement.
- **Backend name** isolates proof systems structurally: a Nexus proof
  can never be *retrieved* for a RISC Zero request; even if bytes were
  swapped on disk, the RISC Zero verifier would reject them. The key is
  the structural guarantee, the verifier the cryptographic one.

Deliberately **not** in the key: output and exit code (the statement is
rebuilt from the *fresh* native execution on every hit, so a cached
proof committed to a different output fails verification — it cannot
silently pass), and never occurrence numbers, timestamps, filenames,
hostnames, or PIDs. The cache deduplicates **proofs**, not
**operations** — three runs of one spec remain three trace occurrences
and one observation, now backed by one reusable warrant. This is the
Phase 121–123 two-ledger distinction applied to warrants.

Storage is deliberately minimal per the overbuild ban: one immutable
local directory per key holding `proof.bin` + `meta`; the artifact
identity is sha256 of the bytes. No TTLs, no LRU, no eviction policy,
no database, no remote store.

## Separation of concerns (unchanged from Stage 7, extended)

- the **policy** decides WHICH warrant is wanted,
- the **cache** answers WHETHER a proof artifact already exists,
- the **backend verifier** decides WHETHER that artifact verifies,
- the **evidence pool** decides WHAT counts as scientific evidence,
- the **operation trace** records WHAT actually happened, every time.

`WarrantRecord` gained one campaign-metadata field, `cache`, with
values `miss+stored` / `hit` / `hit-invalid` / `invalidated` /
`regenerated+stored` — never part of any evidence identity.

## Failure semantics

A **miss** ("no warrant") and a **hit that fails verification**
("invalid warrant") are different results and are recorded differently.
A hit-invalid is a *failed lane*: it feeds the existing deterministic
escalation and is never silently regenerated. Only
`regenerate_invalid=True` lets the policy discard the bad artifact —
via an explicit `invalidate` that itself lands on the warrant record —
and prove afresh. Corruption is an *event with a record*, never an
automatic repair that hides it.

## Empirical results (tests: `tests/test_execution_stage8_warrant_cache.py`)

All with real Nexus proofs and an **instrumented host** (a logging shim
in front of the real host binary), so "proving was skipped" is an
observed fact about which subcommands ran, not an inference:

1. **Key discrimination** — same (backend, artifact, spec) → same key;
   different backend / ELF / input / configuration / descriptor → all
   different keys.
2. **Reuse skips proving, never verification** — three identical
   campaign points: 3 occurrences, 1 observation, 1 stored artifact;
   shim log shows `prove` × 1, `verify` × 3; warrant records
   `miss+stored, hit, hit`; observation ids identical with and without
   the cache.
3. **Corruption (mandatory experiment)** — one byte flipped in the
   stored artifact: the hit still goes to the verifier, fails
   (`Malformed`), the dispatch **fails**, no `VerifiedExecution`, no
   automatic regeneration, the corrupted entry left in place, `prove`
   count unchanged. With `regenerate_invalid=True`: records
   `hit-invalid → invalidated → regenerated+stored`, and the
   replacement serves clean hits.
4. **Cross-process reuse** — a producer *process* proves and stores; a
   separate consumer *process* sharing only the cache directory hits,
   re-verifies (shim log: `verify` × 1, `prove` × 0), and gets the same
   proof identity.
5. **Backend isolation** — a warrant stored under the Nexus key is
   invisible to a RISC Zero lookup of the same spec and ELF.

## Measured campaign (`scripts/stage8_warrant_campaign.py`)

The identical campaign the Stage 7 experiment ran (9-cell sweep, 3
repeats, near-identical variant, genuine escalation, failure, retry,
rejection — 17 points), same policy identity (`b9dc819b…`), three arms
in one run. Stage 7's own measurement (366.8 s total proving) is kept
only as the recorded historical baseline; **arm A re-measured the
uncached cost in this run**, and all comparisons below are within-run.

| | arm A — no cache | arm B — cold cache | arm C — warm cache¹ |
|---|---|---|---|
| executions | 17 | 17 | 18 |
| successes / failures | 15 / 2 | 15 / 2 | 16 / 2 |
| observations / unique evidence | 15 / 11 | 15 / 11 | 16 / 12 |
| trace occurrences (S/F/R) | 17 (15/1/1) | 17 (15/1/1) | 18 (16/1/1) |
| proof generations | **16** | **12** | **2** |
| proving time | **501.8 s** | **402.5 s** | **46.4 s** |
| cache hits (reused warrants) | — | 4 | 15 |
| hit-verification overhead | — | 0.4 s | 1.8 s |
| cache hit rate | — | 24 % of 17 lookups | 89 % of 18 lookups |
| verification failures | 0 | 0 | 1 (the corrupted artifact) |
| campaign wall time | 502.1 s | 403.0 s | 48.3 s |

¹ arm C reran the whole campaign on arm B's persisted cache, with one
cached artifact deliberately corrupted beforehand and one *new*
specification appended.

**Measured, from the run:**

- **Proof generations avoided: 19** (4 in arm B, 15 in arm C) — each
  one a real proof that did not have to be generated.
- **Same-campaign reduction (A→B): 19.8 % less proving** (501.8 s →
  402.5 s). The within-campaign win is exactly the redundancy Stage 7
  measured: repeats, the retry, and the escalation's second lane all
  restate one statement.
- **Cross-campaign reduction (A→C): 90.8 % less proving** (501.8 s →
  46.4 s). The entire remaining cost is the corrupted-entry
  regeneration plus the genuinely new specification — i.e. arm C paid
  for proofs only where a proof was actually missing or invalid.
- **Verification overhead of reuse: 2.1 s total, ≈0.11 s per reused
  warrant** — mandatory re-verification costs about 0.4 % of the ~30 s
  mean proof generation it replaces.
- **Persisted artifacts: 13 entries, 1,170,206 proof bytes** (74–225 KB
  per proof; Nexus smallest, RISC Zero largest).
- **Corruption recovery, on the record:** `hit-invalid → invalidated →
  regenerated+stored` — the invalid warrant failed verification, the
  discard was an explicit recorded decision, and only then was a fresh
  proof generated.
- **Evidence invariance: CONFIRMED** — observation ids identical across
  arms A, B and C on the common points (asserted, not eyeballed); arm
  C's one new spec was a cache **miss** that proved fresh, because a
  changed statement is a different key.

## Epistemic status of each claim

**MEASURED** (observed in this run, on real artifacts): every number in
the table above; that `prove` was invoked exactly once per fresh
statement and never on a hit (instrumented host log, not timing
inference); that the corrupted artifact failed verification; that the
consumer *process* in the cross-process test verified without proving.

**STRUCTURALLY GUARANTEED** (by construction, enforced by code paths
that have no alternative): a hit cannot skip verification
(`verify_existing_proof` is the only hit path); `VerifiedExecution` is
constructible only from a `Verified` result; backend isolation at the
key (the backend name is inside the commitment); occurrences never
enter the key; the evidence pool has no field a warrant can reach;
regeneration cannot happen without an explicit `invalidate`.

**CALLER-DECLARED** (trusted input, checkable but not checked here):
that the backend name passed to `statement_key` matches the host binary
the lane actually runs — the Stage 5 registry gate catches a wrong
*artifact*, and a mismatched proof system fails verification, but the
label itself is the caller's claim; likewise `regenerate_invalid` is a
policy choice, not a discovered fact.

**EXTERNALLY UNVERIFIABLE** (outside what any proof here can certify):
that the native inputs describe the physical world (COMPUTATION ≠
MEASUREMENT, unchanged since Stage 2); the soundness of the zkVM proof
systems themselves; and the local filesystem's integrity *between*
verifications — which is exactly why every hit is re-verified.

## Conclusion

**Does warrant reuse materially reduce the cost of repeated scientific
computation without changing scientific evidence identity?**

Yes — measured, not estimated: re-running a real 17-point campaign on
persisted warrants cost 46.4 s of proving instead of 501.8 s (90.8 %
reduction; 19 proof generations avoided across both cached arms) while
observation ids, unique-evidence counts, and trace semantics were
asserted identical to the uncached run, and every reused warrant still
passed its backend verifier (≈0.11 s per hit, ~0.4 % of the proving it
replaced).

## Infrastructure note: repository rename

During Stage 8 GitHub renamed the repository upstream to
`Scientific-Transformer-Engine`; the old remote URL transparently
redirects and pushes succeed. No internal renaming was performed: the
`Scout-Retrieval-Agent` strings in `execution/build.py` are the
canonical staging-path components baked into the Stage 5 build-recipe
identities (renaming them would change every registered artifact hash),
so they are part of recorded build identity, not branding. Metadata
only; no action taken.

## What this did NOT change

- Verification never became optional: every `verified` outcome in every
  arm passed a real backend verifier in that arm.
- The proof ladder's meaning is untouched — the cache changes *when a
  proof is generated*, never *what a proof means*.
- COMPUTATION ≠ MEASUREMENT stands: a reused warrant certifies the same
  computation-correctness claim the original proof did, nothing more.
