# Experiment Architecture — Phase 63

This document is Phase 63's required deliverable: a formal specification
of the boundary a future `experiment/` package occupies, and nothing
else — no code changes accompany this document. It is written in the
same spirit as `docs/SCOUT_ARCHITECTURE.md` and
`docs/RETRIEVAL_ARCHITECTURE.md`: derive the contract from the
architecture that already exists (Phase 62's audit), rather than
inventing a parallel one.

## 0. Why this document exists

Phase 62 audited the completed `materials/` algebra (Phases 27-61) and
found it mathematically closed but structurally disconnected: nothing in
the repository imports `materials/`, and no orchestrator sequences its
primitives into the closed loop

```
S_t -> P_t = G(S_t, x) -> physical experiment -> O_t -> A_t -> S_(t+1) = F(S_t, O_t)
```

end to end. That is not a defect in the algebra — every phase since 27
deliberately kept `materials/` a library of pure, composable functions,
never a hidden pipeline. But it does mean the algebra has no *caller*.
`scout/pipeline.py` is this repository's own precedent for what a
caller looks like: a small orchestration package, one level above the
layer it sequences, that composes already-existing primitives without
adding new mathematics to them. This document specifies the equivalent
package for `materials/` — call it `experiment/` — precisely enough
that implementing it requires no further architectural judgment calls,
only code.

## 1. The pipeline this phase specifies

```
EvidencePool (evidence/, unchanged)
     |
RetrievalEngine (retrieval/, unchanged)
     |
MaterialsIteration / ModelState / ActionCandidate (materials/, unchanged)
     |
ExperimentSession (experiment/session.py)                     <-- NEW
     |
ActionDispatcher seam (experiment/interface.py)                <-- NEW, deliberately minimal
     |
run_experiment_step (experiment/step.py)                        <-- NEW
     |
[future: a real scheduler / multi-step runner -- NOT specified here]
```

`experiment/` is a **producer that depends on `materials/`**, exactly
the same relationship `scout/` already has to `evidence/`
(`docs/SCOUT_ARCHITECTURE.md` §2: *"`scout/` is a producer that depends
on `evidence/`"*). It sits as a new top-level package, a sibling of
`scout/`, `materials/`, `core/`, `morpho/`, `backends/`, `adapters/`,
`runtime/` — never nested inside any of them, for the same reason
`evidence/`/`scout/` were given top-level treatment rather than nesting.

## 2. Ownership table

This is the actual deliverable of Phase 63: a line drawn precisely
enough that no future phase needs to re-litigate which package a given
concern belongs to.

| Package | Owns | Does NOT own |
|---|---|---|
| `evidence/` | `Observation`, `Referent`, `ClaimedRelationship`, `Source`/`Document`/`Record`, provenance, content identity, append-only storage, the admission gate | Retrieval, prediction, decision-making of any kind |
| `scout/` | Acquisition/extraction — turning external sources into admitted evidence | Anything downstream of evidence attachment (unchanged, per `docs/SCOUT_ARCHITECTURE.md` §0's own "stop before autonomous experimentation" boundary) |
| `retrieval/` | Deterministic, read-only querying of `EvidencePool` | Writing anything; deciding anything |
| `materials/` | `ModelState`, `Prediction`, transition (`F`, actual and counterfactual), `PredictionAssessment`, `ModelStateTrajectory`, `StateTransitionDiagnostic`, `CounterfactualOutcome`/`CounterfactualSet`, the `InformationValueModel` seam, `CandidateUtility`, `CandidateRanking`, `CandidateOptimization` — the full descriptive+dynamic algebra (Phases 27-61) | Sequencing across steps; deciding *when* to act; talking to anything outside `evidence/`/`retrieval/` (enforced today by `tests/test_materials_boundaries.py`) |
| `experiment/` (this spec) | Sequencing, workflow, policy selection, *calling* `materials/`'s primitives in the documented order, external action dispatch (via a seam, never a live integration itself), receiving results, maintaining the active state reference | Any new mathematics — no prediction, transition, information, utility, ranking, or optimization logic of its own; it calls `materials/`, it does not reimplement it |
| `core/`, `morpho/`, `backends/`, `adapters/`, `renderer/`, `runtime/` | Canonical structural/scene state, morphogenesis, rendering/simulation representations | Unchanged, untouched, unrelated (Phase 62 §6: independent state spaces by design, not a projection of anything in the evidence/materials stack) |

The rule that makes this enforceable, not aspirational (mirroring
`materials.results.admit_experimental_result`'s own role as the *sole*
write boundary into `EvidencePool`): **`experiment/` never calls
`pool.put_*`/`evidence.admission.admit_*` directly.** Every write
`experiment/` ever causes goes through `materials.results.
admit_experimental_result`, exactly the same door every other write in
this codebase already goes through. `experiment/` gains no special
access `materials/` itself doesn't already have.

## 3. What `experiment/` adds, precisely

Four new concerns, no more:

### 3.1 The active state reference (`experiment/session.py`)

`ExperimentSession` is an immutable snapshot — `EvidencePool` reference,
`RetrievalEngine`, the current `MaterialsIteration`, the current
`ModelState`, and the `ModelStateTrajectory` accumulated so far. It
follows the exact discipline every `materials/` object already
follows: **"maintaining the active state reference" means the caller
holds the latest `ExperimentSession` returned; nothing is ever mutated
in place.** Advancing one step produces a NEW `ExperimentSession`, the
same way `materials.model_state.update` produces a new `ModelState`
rather than mutating the old one. There is no `ExperimentSession.
advance()` method that mutates `self` — only a pure function that
returns a new session. This is a deliberate, load-bearing choice, not
an oversight: introducing the first mutable object in this entire
codebase, at the exact layer meant to *drive* the immutable algebra
underneath it, would undermine every determinism guarantee Phases
52-61 spent their own effort proving.

### 3.2 Policy selection (`experiment/policy.py`)

`ExperimentPolicy` names which already-existing `materials/` policy
objects to use at each step (an `OptimizationPolicy`, and a caller-
supplied per-candidate utility-input source) — it is a bundle of
references to existing policy types, not a new decision algorithm.
Exactly as `materials.optimization`'s own docstring insists the
optimizer is "optimal only with respect to the caller-supplied utility
values and `OptimizationPolicy`," `ExperimentPolicy` makes no claim to
be smarter than the policies it names.

### 3.3 The external action-dispatch seam (`experiment/interface.py`)

A `Protocol`, mirroring `scout.interface.SourceAdapter`/`Extractor` and
`materials.information.InformationValueModel` — the exact seam pattern
this codebase has now used three times for "a real external capability
does not exist yet, but the interface it will plug into does."
`ActionDispatcher.dispatch(candidate) -> DispatchedMeasurement` is the
one and only place a physical experiment would actually be performed.
No implementation in this codebase, present or future, is asked to be
a real lab-automation integration — the only implementations that will
ever ship here are deterministic and fixture-based, exactly as
`scout/adapters.py`'s `FixtureSourceAdapter` is the only `SourceAdapter`
this codebase ships.

### 3.4 Sequencing (`experiment/step.py`)

`run_experiment_step(session, candidates, dispatcher, policy)` is the
one new function that actually calls things in order — and every single
thing it calls is an unmodified `materials/` primitive already proven
across Phases 37-61:

```
1. materials.model_state.predict            -- P_t = G(S_t, x), per candidate
2. materials.information.estimate_information_value  -- information value at S_t
3. materials.utility.evaluate_candidate_utility        -- utility, from policy's source
4. materials.optimization.optimize_candidates(max_candidates=1)  -- THE decision (Phase 60)
5. ActionDispatcher.dispatch                            -- perform the chosen action [seam]
6. materials.results.make_experimental_result /
   admit_experimental_result                             -- the sole write boundary
7. materials.model_state.update                           -- S_(t+1) = F(S_t, O_t)
8. materials.assessment.assess                              -- residual, diagnostic only
```

Step 4 is not a new decision primitive — it is Phase 60's own finding,
applied: `optimize_candidates` with `max_candidates=1` already answers
"which candidate does the policy select." `run_experiment_step` does
not reimplement that answer; it calls it.

## 4. What this phase explicitly does NOT specify

- **No multi-step scheduler or autonomous loop.** `run_experiment_step`
  performs exactly one step and returns; whether/how a caller repeats
  it (once, N times, until some caller-defined stopping condition) is
  deliberately left to the caller, not this package — the same
  "stop before autonomous experimentation" boundary
  `docs/SCOUT_ARCHITECTURE.md` §0 already drew for `scout/`.
- **No real `ActionDispatcher` implementation.** Only a deterministic,
  test/demo-oriented one, clearly labeled as such.
- **No ranking in the decision path.** `materials.ranking` remains
  available to a caller who wants a diagnostic ordering, but Phase 60
  already established the decision itself needs only `optimize_candidates`
  — `run_experiment_step` does not call `rank_candidates`.
- **No new identity, provenance, or state mechanism.** `ExperimentSession`
  carries existing objects by reference; it mints no new content-hash
  scheme.
- **No connection to `core/`/`morpho`/`backends`/`renderer`.** Phase 62
  §6 already established these are independent state spaces; this
  phase does not reopen that question.

## 5. Boundary enforcement (to be added alongside the implementation)

Mirroring `tests/test_materials_boundaries.py` exactly:

- `experiment/` may import only `evidence/`, `retrieval/`, `materials/`
  (and the standard library) — never `core/`, `morpho/`, `backends/`,
  `adapters/`, `runtime/`, `scout/`.
- No file under `experiment/` calls `pool.put_*` or references
  `admit_*` directly — every write is reached exclusively through
  `materials.results.admit_experimental_result`.
- The existing pin (`materials/results.py` is the *only* file across
  the whole evidence-writing stack that mutates `EvidencePool`) is
  extended, not replaced: the mutator set stays exactly
  `{"materials/results.py"}` even once `experiment/` exists.

## 6. Migration implications

None to `materials/`, `evidence/`, `retrieval/`, `scout/`, or any
existing test. Everything specified here is new, additive
infrastructure **above** `materials/` — the same non-invasive posture
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §O and
`docs/COMPUTATIONAL_COMMONS.md` §O both required of their own proposed
extensions, and the one this repository has followed at every layer
since.

## 7. Addendum — refinement discovered during implementation

§5's original rule ("every write is reached exclusively through
`materials.results.admit_experimental_result`") was one call too
strong, and implementation surfaced the precise correction rather than
silently deviating from this document. `admit_experimental_result` has
always required an ALREADY-ADMITTED `record_id` as input (Phase 44's
own docstring: "the caller is responsible for having already admitted
the Source/Document/Record chain") — Record admission was therefore
never part of the write boundary `materials.results`, or its own
boundary test, protects; it is raw structural bookkeeping (a locator +
raw content), not a scientific claim, the same distinction
`docs/SCOUT_ARCHITECTURE.md`'s own data-contract table already draws
between `Record` and `Observation`.

`ExperimentSession` therefore carries an already-admitted `document_id`
(the caller is responsible for it, exactly the same discipline Phase 44
already established for `record_id`), and `experiment.step.
run_experiment_step` calls `evidence.admission.admit_record`/
`pool.put_record` directly — the ONE admission surface `experiment/` is
permitted to touch outside `materials.results.admit_experimental_result`
itself. The SEMANTIC facts (`Observation`, `ClaimedRelationship`) still
only ever enter `EvidencePool` through `materials.results.
admit_experimental_result` — unchanged from §5's intent, just stated at
the correct granularity. `tests/test_experiment_boundaries.py` enforces
this exact, narrower rule.
