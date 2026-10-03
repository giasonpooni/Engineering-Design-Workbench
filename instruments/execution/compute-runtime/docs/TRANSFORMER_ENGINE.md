# Hardmax-attention workload in Scientific Computation Runtime

This document records the implementation and measured phases of the attention
workload. The runtime also executes non-neural scientific workloads. Existing
`ste.transformer.*` and `scout.native.attention-kernel.v1` identifiers are retained;
see [documentation compatibility](README.md#compatibility-and-historical-records).

The workload's first slice: molecular scientific state,
projected to typed tokens, transformed by an integer single-head
**hardmax attention** model computation running through the *unchanged*
STE execution boundary, yielding a Prediction that is — structurally —
not evidence.

## Inspection results (before any code)

No Transformer functionality, tensor representation, or SCL C++/CUDA
package existed. `backends/neural/interface.py` is the earlier
projection-layer estimator protocol (belief-state interface), not a
model-computation path — inspected and left alone. The computational
substrate is the Rust native engine (plus the external MD engine
boundary); execution identity, tracing, proving, warrants, and
retention machinery all already exist and are consumed, not duplicated.

## The path (all contracts recorded in `architecture/transformer_contract.yaml`)

    Molecule (canonical, structures/)                     -- not owned here
      -> TransformerRepresentation                        ste.transformer.representation.v1
         typed tokens (mass_amu, x_pm, y_pm, z_pm); the mass feature SEES
         the element (unlike the element-blind pairwise lowering)
      -> tensor projection (the token matrix; a projection, not a schema)
      -> AttentionModel                                   ste.transformer.model.v1
         three d*d integer matrices; content-addressed
      -> ExecutionSpecification                           STE, unchanged
         payload = [X | Wq | Wk | Wv]: spec identity covers model+data
         jointly (a different model IS a different computation); the
         model identity exists beside it at this layer
      -> scout.native.attention-kernel.v1                 registry 4 -> 5
         integer hardmax attention (argmax, ties to lowest index --
         exact in integers; no softmax rounding hidden in semantics)
      -> ExecutionResult -> Prediction
         explicit uncertainty_kind; no conversion to Observation exists

## Measured (baseline, 200 forwards, d=4)

| phase | measured |
|---|---|
| reference agreement (independent Python implementation) | **200/200 exact** |
| representation construction | 3.0 µs/forward |
| spec encoding (tensor + lowering) | 11.4 µs/forward |
| forward through the STE engine | **2.11 ms/forward** (474 forwards/s) |
| engine child peak RSS | 18.2 MB |
| repeatability | identical predictions on repeat (locked) |

**The measured bottleneck**: the one-process-per-execution engine
boundary (~2 ms of process spawn + IPC per forward) dominates the
microseconds of attention arithmetic by ~150×. That boundary is a
deliberate STE isolation property (state cannot leak between
executions); amortizing it (batching multiple forwards into one
request, or a session mode) would be an *execution-contract* extension
to take up only if a real workload needs thousands of forwards —
recorded, not built.

## Locks (all executed)

Representation→tensor correctness and identity sensitivity (coordinate,
element); native/reference exact agreement on water and methane;
repeat-computation identity; model ≠ representation ≠ specification
identity with weight- and input-tamper sensitivity; failure semantics
(malformed → exit 2, value bound → exit 4, dimension mismatches refused
in Python before the engine — refusals, never predictions); prediction
is not evidence (pool refuses the type; no pool write exists in
`transformer/`; the architecture-sync minting-seam ratchet scans the
package); `uncertainty_kind` explicit or the Prediction cannot exist;
proving refused attributably (no guest registered — the stage-5 gate).
Rust: 3 new kernel unit tests (one of which caught my own wrong
expected value — the kernel was right, the test arithmetic was wrong,
fixed as a test correction, semantics untouched); clippy + fmt clean.

## Boundary states

- **STE**: the only execution path; no parallel Transformer
  execution/proof/warrant/evidence systems exist.
- **SCL**: no C++/CUDA package exists in this repository; recorded in
  the contract. An accelerator path is a future backend extension
  behind the same boundary.
- **Evidence**: prediction → validation → admissibility → acquisition
  is the only re-entry; `prediction_carries_uncertainty` continues to
  gate canonical assertion.
- **FEP**: nothing required by this workload; nothing built.
- **Proving**: attention guests are buildable through the established
  Stage 5 machinery when a workload justifies them; until then the
  refusal is attributable.

## Claim classification

**MEASURED**: every number above; the 200/200 agreement; the caught
test defect. **STRUCTURALLY GUARANTEED**: identity separations
(distinct commitment tags), prediction-not-evidence (no conversion, no
write path, ratcheted), explicit uncertainty, kernel fault refusals.
**CALLER-DECLARED**: the model weights and the token feature
convention. **EXTERNALLY UNVERIFIABLE**: nothing new — the kernel is
native and deterministic; hosted-model claims remain governed by
`model_binding.yaml`.

## Phase 2 — The Batched Forward Execution Contract (measured)

The 2.11 ms boundary cost is amortized by the smallest possible seam:
the engine's wire format became a SEQUENCE of the existing request
(`[program][configuration][input]` repeated B ≥ 1 times) answered by B
complete result blocks in request order — the same protocol, not a
second one. The whole stream is parsed before anything executes
(truncated stream → exit 2, nothing runs); requests share ONE
process-local trace, so occurrence numbers record execution order;
every constituent keeps its own engine-minted specification, program,
input, output, and computation identity — a batch has no identity of
its own beyond the process that ran it, and nothing collapsed.
`run_specifications` checks every block with the identical recompute-
and-compare logic (`_check_result`, shared with the single path, which
is now literally a batch of one and byte-identical on the wire).
`AttentionModel.forward_batch` gives the Transformer the same contract:
per-item halts are attributable at the execution layer and refuse by
index at the model layer — a fault is never a prediction.

| B | ms/forward | forwards/s |
|---|---|---|
| 1 | 1.895 | 528 |
| 2 | 1.039 | 963 |
| 4 | 0.565 | 1,769 |
| 8 | 0.356 | 2,811 |
| 16 | 0.214 | 4,665 |
| 64 | 0.104 | 9,601 |
| 256 | **0.088** | **11,335** |

**Outcome A — strong amortization**: ×8.8 at B=16, **×21.5 at B=256**.
The measured boundary cost (1.807 ms, 95% of a single forward)
amortizes away; batched[i] == single(input[i]) exactly at every tested
size, and duplicates inside one batch share a computation identity
while keeping distinct occurrences — content collapses, operations
never do. Verification/proof boundary: unchanged and untouched — the
attention program has no registered guest, and each constituent
computation is exactly the shape the existing proof machinery already
addresses per-statement; nothing batch-proof-shaped was built.

**The next measured constraint**: the per-item marginal cost of
**0.088 ms** — dominated by per-item Python-side work (result-block
parsing, hex decoding, and the four SHA-256 identity recomputations per
item that make the engine checked-not-trusted), now ~1000× the kernel
arithmetic. Amortizing *that* honestly (without weakening the
recompute-and-compare discipline) is the next frontier if a workload
ever needs more than ~11 k forwards/s.

## Phase 3 — Per-Item Checker Cost (profiled, optimized, stopped)

The profile OVERTURNED the predicted attribution, and the measurement
governs: at B=256 the engine subprocess side costs **~35–37 µs/item**
(execution + result formatting + the batch process's amortized share),
while Python-side checking costs only **16.8 µs/item** — parsing
~3.6 µs, the five digest computations ~12.5 µs. The "0.088 ms of
Python checking" prediction was wrong by attribution; checking was a
third of the marginal cost, not most of it.

The one provably-safe reduction: batch members share byte-identical
program bytes (and duplicate specs share everything), yet identities
were recomputed per item. `run_specifications` now reuses digests per
batch, keyed by the exact input bytes — dict key equality IS the
byte-for-byte identity proof, and the digests come from the very same
identity functions. `_check_result` with no precomputed identities
remains the untouched semantic reference; a corpus lock requires exact
verdict agreement between reference and optimized paths on valid
blocks and on every tampered identity class (spec, program, input,
output_id, computation, flipped output bytes) — one lock construction
defect was caught by running: two nearby heat inputs CONVERGE to
identical outputs under integer truncation, so an output "swap" was no
tamper; replaced with a byte flip. Duplicates still never collapse
operations ([A,A,A,B] → one content identity, occurrences 0..3).

Measured result: Python checking 16.8 → **13.5 µs/item**; end-to-end
0.088 → **0.083 ms/forward (12,062 forwards/s, ×22.9)**. About 6% of
the marginal cost was removable without weakening verification; the
rest of the checker cost is SHA-256 over per-item-unique bytes — the
price of checked-not-trusted, and it stays.

**Stop condition applied**: no current workload is constrained at
12 k forwards/s, and the remaining marginal dominator is the
engine-side per-request work — a Rust/STE frontier (result hex
formatting, per-request bookkeeping) to take up only if a real
workload demands it. Recorded, not built.

## Phase 4 — Rust Engine Per-Request Cost: PROFILED, then DEFERRED

INSPECTED 2026-08-25: the only consumers of the batched forward path
are the benchmark/profile scripts and `AttentionModel.forward_batch`
itself; the real scientific campaigns in this repository execute tens
of points per run. **No actual workload demonstrates that 12,062
forwards/s is insufficient**, so per the phase gate no implementation
change was made and no speculative profiling harness was built.

The frontier was nonetheless **profiled before deferring**, because
deferring on a hypothesis is what step 4 of the directive warns
against. Profiling is measurement, not optimization: it required no
instrumentation and no engine change — the attribution comes from
differential experiments that vary what a request makes the engine do
(`scripts/engine_request_profile.py`).

**Design.** Three request shapes isolate the terms: `heat steps=0 n=3`
(32 B in, 24 B out — a zero-iteration loop, so essentially no
arithmetic) fixes the constant; `attention n=1 d=64` (49,416 B in,
512 B out) is large-input/small-output; `heat steps=0 n=4096`
(32,776 B in, 32,768 B out) is large in *and* out. A sweep over batch
size on the constant point then separates one-time process spawn from
the true marginal per-request cost by linear fit.

**Measured components** (engine side, this machine):

| component | measured |
|---|---|
| process spawn + startup | **2.15 ms per process** (one-time; the term batching already amortizes) |
| true marginal per-request (tiny payload) | **11.43 µs** — parse, reconstruct, execution bookkeeping, result construction |
| input-side (parse + reconstruct) | **12.7 µs/KB** |
| output-side (hex + block formatting) | **58.2 µs/KB** — 4.6× the input side per byte |

**Attribution for the real transformer request** (280 B in, 160 B out),
at B=256: amortized spawn ≈ 8.4 µs (26%), fixed per-request
bookkeeping 11.4 µs (35%), output hex + formatting 9.3 µs (28%), input
parsing 3.6 µs (11%) — summing to ≈ 32.7 µs against the 35–37 µs
measured independently in the previous phase, which is the check that
the model is sound.

**The hex hypothesis was half right, and that is why it was measured.**
Output bytes really are 4.6× costlier than input bytes — consistent
with `format!("{b:02x}")` allocating per byte — but at this workload's
160-byte outputs that is only ~28% of engine cost. The single largest
marginal term is the **fixed per-request path (11.4 µs)**, not hex. Had
the frontier been opened on the hypothesis, the wrong component would
have been optimized.

**Gate re-applied against the measurements**: unchanged — no workload
demands more than 12 k forwards/s, so **no implementation change was
made**. If the gate ever opens, the target is the fixed per-request
path first and output formatting second, under the standing invariant:
same protocol, execution, identity, failure, and verification semantics
(parse-all-before-execute, per-item fault attribution, deterministic
ordering, all five constituent identities, caller-side
recompute-and-compare, no trusted engine digests), benchmarked before
and after, stopping if the improvement is not meaningful.
