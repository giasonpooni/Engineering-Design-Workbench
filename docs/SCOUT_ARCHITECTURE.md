# SCOUT — Network Observation Primitive

This document is deliverable A of the SCOUT phase: SCOUT's role,
interfaces, data contracts, its relationship to the Trust Graph and to
an eventual FEP layer, the deterministic/probabilistic boundary, the
network metrics implemented (and the ones deliberately not), and the
future agent topology. Deliverable B (implementation) is `evidence/` and
`scout/`; deliverable C (tests) is `tests/test_evidence_*.py`,
`tests/test_trust_graph.py`, and `tests/test_scout_*.py`.

## 0. What this document is not

This is not a new architecture. Section 10's own instruction — "do not
create a parallel architecture," "inspect the current architecture first
and derive the contract from its invariants" — is followed literally:
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` had already fully designed the
layer SCOUT needed (§B evidence model, §D provenance chain, §E conflict
model, §J agent boundary, §K model boundary, §O CanonicalState boundary,
§R implementation sequence) as research, with zero code. SCOUT is that
design's first real implementation — specifically, steps 1-2 of §R
("`Document`/`Record` raw storage," "`Observation`/`Claim` extraction,
deterministic sources only") plus the `Referent`/`ClaimedRelationship`
graph layer needed for "entity/relation identification," plus SCOUT-
specific network metrics and an FEP-facing interface that Phase 14 did
not need to specify. Steps 3-5 of §R (`NormalizedRecord`/`Condition`,
`Derived value`, the pool→adapter promotion bridge) are **not**
implemented here — SCOUT stops at evidence attachment, per this phase's
own "stop before autonomous experimentation or intervention" instruction.

## 1. SCOUT's role

SCOUT is an **observer**, not a decision-maker. Concretely: SCOUT reads
external sources, extracts candidate entities/relations/facts, and
attaches them to the evidence pool's Trust Graph, subject to a
structural admission gate. It never touches `core.canonical` — no
`CandidateDelta`, no `validate_candidate` call, no `CanonicalState`
mutation, directly or indirectly (enforced by
`tests/test_scout_boundaries.py`).

```
External information
     |
Source acquisition            (scout.interface.SourceAdapter)
     |
Document / Record             (evidence.types, content-addressed)
     |
Observation extraction        (scout.interface.Extractor)
     |
Entity / relation identification  (Referent / ClaimedRelationship)
     |
Admission gate                (evidence.admission -- structural checks)
     |
Trust Graph attachment        (evidence.trust_graph -- derived view)
     |
Network-state metrics         (evidence.metrics)
     |
FEP-facing signal             (evidence.fep_interface -- INTERFACE ONLY)
     |
[STOP -- future work: investigation / validation / promotion]
```

## 2. Package layout and why it lives where it does

```
evidence/            The pool (Phase 14's design, now implemented)
  identity.py           content-addressing (mirrors version.py)
  types.py               Source, Document, Record, Observation,
                          Referent, ClaimedRelationship + make_* factories
  pool.py                  EvidencePool: in-memory, append-only, no delete
  admission.py              the one door into the pool (mirrors validate_candidate's SHAPE, not its authority)
  trust_graph.py             derived graph view over the pool (never a second store)
  metrics.py                   network-state metrics, pure functions
  fep_interface.py              FEP-facing signal -- interface, not an FEP implementation

scout/                The agent (SCOUT itself)
  interface.py            stage Protocols (SourceAdapter, Extractor, ...)
  extraction.py             the only Extractor implementation: deterministic, rule-based
  fixtures.py                two fixture source documents (paper, github_repo)
  adapters.py                  FixtureSourceAdapter
  pipeline.py                    run_scout(): the orchestration
```

`evidence/` and `scout/` are new top-level packages, siblings of `core/`,
`morpho/`, `backends/`, `adapters/`, `runtime/` — not nested inside any
of them. Reasoning: `evidence/` is explicitly **not**
`core.canonical` (it stores uncertain, conflicting, unreviewed data,
which `CanonicalState` structurally cannot — §O below), so nesting it
under `core/` would misstate that relationship; `scout/` is a producer
that depends on `evidence/`, structurally analogous to how
`adapters/` is a producer that depends on `core.canonical`, so it gets
the same top-level treatment `adapters/` already has. Both directions
are enforced, not just described: `evidence/` never imports `scout/`
(one-directional dependency), and `core/` never imports either
(`tests/test_scout_boundaries.py`).

## 3. Data contracts

The prompt's suggested `Observation` shape (`observation_id`,
`source_id`, ..., `network_context`, `suggested_followup`) was
deliberately **not** implemented as one flat dataclass. Investigating
the existing architecture's invariants first (per this phase's own
instruction) surfaced a reason already established twice in this
project: `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §B already worked
through exactly this question ("which information classes are
genuinely distinct") and concluded Source, Document, Record,
Observation, Referent, and ClaimedRelationship are six separate things,
not one. Squashing them into a single `Observation` record would
re-introduce the "one object doing five jobs" anti-pattern this whole
project has repeatedly rejected (Phase 13 §Anti-pattern-check, Phase 14
§B's own naming-collision warning). The actual contract:

| Type | Owns | Identity | Mutable? |
|---|---|---|---|
| `Source` | Origin of documents | `content_hash({kind, name})` | No |
| `Document` | A retrieved artifact | `content_hash({source_id, content_hash, retrieval_method})` | No |
| `Record` | One raw unit within a Document | `content_hash({document_id, locator, raw_content})` | No |
| `Observation` | A semantic, extracted fact | `content_hash({record_ids, extraction_method, content})` — excludes `confidence`/`extracted_at` | No |
| `Referent` | The entity a fact is about | `content_hash({natural_key, kind})` | No |
| `ClaimedRelationship` | An asserted connection between two Referents | `content_hash({from, to, type, observation_id})` | No |
| `DerivedValue` (Phase 17) | A value synthesized from multiple Observations and/or DerivedValues, with a stated method — the first representation not tied to exactly one extraction event | `content_hash({derived_from, method, content})` — excludes `confidence`/`derived_at`, same discipline as `Observation` | No |

Two fields the prompt's sketch suggested that were deliberately
**excluded from these types**: `novelty`/`relevance`/`network_context`/
`suggested_followup` are not stored as attributes of an `Observation` at
all — they are *computed*, evaluated against the Trust Graph at a
specific moment, and change every time the graph changes even though the
`Observation` itself does not. Storing them on the `Observation` would
make an immutable, content-addressed record silently go stale the
instant a new, unrelated finding entered the graph — a real correctness
bug, not just an aesthetic one. They are returned instead as a separate
`ScoutFinding` (see §4) computed alongside, never persisted as if they
were facts about the source. `uncertainty` is the one exception: it is
a pure function of `confidence` (`1 - confidence`), so it is a metric
(`evidence.metrics.observation_uncertainty`), not a stored field either.

## 4. Trust Graph relationship

The Trust Graph is a **derived, read-only view**, never a second store
— `evidence.trust_graph.build_trust_graph(pool)` is a pure function; it
has no mutator. This is exactly `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`
§G's recommendation ("graph = a derived index over structured records,
not the primary store"), which itself directly mirrors
`docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md` §G's conclusion about
Morpho relative to `CanonicalState` — the same discipline, applied a
second time, a layer upstream. Nodes are `Referent`s; edges are
`ClaimedRelationship`s. Because `ClaimedRelationship.id` includes its
source `observation_id`, the graph is a **multigraph**: two sources
claiming different (even contradictory) relationships between the same
two Referents both appear as distinct edges — proven in
`tests/test_trust_graph.py::test_multigraph_preserves_conflicting_claims_as_distinct_edges`.
Nothing in this codebase ever collapses two such edges into "the"
relationship.

## 5. The admission gate — a validation boundary, not *the* validation boundary

`evidence.admission` is structurally shaped like
`core.canonical.validation.validate_candidate` (an errors-list return,
atomic reject-leaves-state-untouched) but is a **different, weaker
gate**: it checks referential integrity and structural well-formedness
(does this Record's `document_id` exist? is `confidence` in range? does
a model-attributed observation actually carry a confidence?), never "is
this true," never "does this conflict with something else" (conflicts
are explicitly allowed to coexist, per §E). `evidence/admission.py`
imports nothing from `core.canonical.validation` and never calls
`validate_candidate` — checked by
`tests/test_scout_boundaries.py::test_evidence_and_scout_never_call_validate_candidate`.

## 6. Deterministic / probabilistic boundary

Every identity-defining hash (`evidence/identity.py`) is computed over
content only — never confidence, never a timestamp, never anything a
model's own uncertainty could vary run to run. Concretely: two runs of
`scout.extraction.DeterministicExtractor` over the same `Record` produce
byte-identical `Observation.id`s (`tests/test_scout_pipeline.py::test_pipeline_is_deterministic_across_independent_runs`),
because the extractor itself is deterministic (regex-based, no model)
and the identity hash excludes the one field (`extracted_at`) that could
legitimately differ between runs. `evidence.types.Observation.confidence`
is a required float — never silently defaulted — and
`scout.pipeline.run_scout` enforces the one rule
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §K makes non-negotiable: a
candidate whose `extraction_method` names a model (`"model:..."`) but
supplies no explicit `confidence` is **rejected**, not silently treated
as `confidence=1.0`
(`tests/test_scout_pipeline.py::test_model_sourced_candidate_without_confidence_is_rejected_not_defaulted`).
A model's output is therefore structurally impossible to mistake for a
verbatim transcription — the same discipline `MorphoRelation`'s
`is_canonical`/`inference_status` split already enforces one layer
downstream, reapplied here.

## 7. Network metrics

Implemented only where the current data model actually supports the
computation (per this phase's explicit instruction not to implement a
metric "because it sounds useful"):

### Connectivity (`evidence.metrics.connectivity`)
- **Definition**: node count, edge count, and average degree of a Trust
  Graph snapshot.
- **Math**: `average_degree = 2 * |E| / |V|` (0 if `|V| = 0`).
- **Required data**: the Trust Graph itself — no additional data.
- **Cost**: O(V + E).
- **Interpretation**: how densely the observed portion of the domain is
  currently linked.
- **Limitations**: says nothing about *which* edges matter; a graph can
  be "dense" via many low-confidence, single-source claims.

### Novelty (`evidence.metrics.novelty`)
- **Definition**: fraction of a finding's referenced Referents/
  ClaimedRelationships that did not already exist in the graph
  immediately before the finding.
- **Math**: `(new_referents + new_relationships) / (total_referenced)`,
  in `[0, 1]`.
- **Required data**: a before-finding graph snapshot and the finding's
  referent/relationship ids — both already produced by `run_scout`.
- **Cost**: O(k) in the number of ids referenced by one finding.
- **Interpretation**: is this finding telling us something the graph
  didn't already contain?
- **Limitations**: purely structural — a "novel" node with a wildly
  implausible claim scores the same as a novel, well-supported one;
  novelty is not a truth or quality signal.

### Redundancy (`evidence.metrics.redundancy`)
- **Definition**: count of distinct Sources that have contributed a
  claim touching a given Referent.
- **Math**: `|{document.source_id : rel in relationships_touching(referent), obs = rel.observation, record in obs.records, document = record.document}|`.
- **Required data**: the pool's own reference chain (Observation ->
  Record -> Document -> Source) — no new index needed.
- **Cost**: O(degree(referent)).
- **Interpretation**: how independently corroborated a Referent is.
- **Limitations**: counts sources, not source *quality* — a confidence/
  source-quality scoring methodology is explicitly unresolved research
  (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §S); this metric does not
  attempt one.

### Source diversity (`evidence.metrics.source_diversity`)
- **Definition**: `redundancy(referent) / relationship_count(referent)`.
- **Math**: a plain ratio in `[0, 1]`.
- **Required data**: same as redundancy.
- **Cost**: O(degree(referent)).
- **Interpretation**: are many claims about this Referent coming from
  few sources (low diversity, possible echo/duplication) or many (high
  diversity, independent corroboration)?
- **Limitations**: same source-quality caveat as redundancy; also
  undefined (returns 0.0) for a Referent with no relationships yet.

### Uncertainty (`evidence.metrics.observation_uncertainty` / `aggregate_uncertainty`)
- **Definition**: `1 - confidence`, per observation or averaged over a
  set.
- **Required data**: `Observation.confidence` — always present.
- **Cost**: O(1) / O(n).
- **Interpretation**: how much epistemic doubt this evidence carries.
- **Limitations**: `confidence` itself has no calibration/scoring model
  (§S, again) — this metric is only as meaningful as the confidence
  values extractors actually supply, which for the one deterministic
  extractor in this codebase is a fixed constant (1.0).

### Evidence density (`evidence.metrics.evidence_density`)
- **Definition**: raw count of ClaimedRelationships touching a Referent.
- **Required data**: pool query, already indexed by referent id.
- **Cost**: O(degree(referent)).
- **Interpretation**: how much relational evidence currently surrounds
  this Referent.
- **Limitations**: **deliberately not normalized** against a graph-wide
  average or domain baseline — no principled baseline exists yet (what
  counts as "typical" density is domain-dependent and unresolved).
  Reported as a raw count rather than a fabricated normalized score.

### Bridge potential (`evidence.metrics.bridge_potential`)
- **Definition**: does a new `ClaimedRelationship` connect two Referents
  that were in different connected components of the graph immediately
  before it was added?
- **Math**: union-find over the pre-edge graph; `component(from) !=
  component(to)`.
- **Required data**: the pre-edge Trust Graph.
- **Cost**: O(V + E) (dominated by building the component partition).
- **Interpretation**: is this finding the first evidence linking two
  previously-separate clusters of knowledge — often the most valuable
  kind of finding for directing future investigation.
- **Limitations**: binary (bridge / not-bridge), says nothing about how
  significant either cluster is.

### Deferred, not implemented: activity / temporal acceleration
The prompt's own candidate list included "activity" and "temporal
acceleration" (rate of new findings about a Referent over time). Not
implemented: computing a rate requires a time-windowed index over
Observation timestamps that nothing in this repository builds yet —
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §S already defers exactly this
class of index. Faking a "one-shot" version (e.g., comparing only the
two most recent observations) would produce a number without the
statistical basis its name implies. Left as a documented future metric,
not a placeholder implementation.

## 8. FEP interface — established vs. proposed vs. hypothesis

`evidence/fep_interface.py` gives a future network-dynamics layer a
stable shape to consume. It is explicitly **not** a Free Energy
Principle implementation. Three confidence levels, kept structurally
distinct in the module's own docstring and never blurred in code:

- **ESTABLISHED**: `FEPSignal.uncertainty` and `.novelty` — pure
  functions of data this repository stores and computes, covered by
  tests.
- **PROPOSED EXTENSION**: `.relevance` and `.investigation_cost` are
  caller-supplied numbers with no scoring model implemented here;
  `.priority` is a documented placeholder combination
  (`uncertainty * novelty * relevance / investigation_cost`) computed
  only when both inputs are supplied — never defaulted into existing.
- **RESEARCH HYPOTHESIS**: `.expected_information_gain` has no estimator
  anywhere in this codebase and is always `None`. Its presence in the
  dataclass is the interface commitment that a future estimator will
  fill it in — not a claim that active inference, expected free energy,
  or any variational objective is implemented here.

## 9. Agent architecture — the LLM is one replaceable stage

```
scout.interface.SourceAdapter    -- acquisition (fixture-based here; live-fetching later)
scout.interface.Extractor        -- <-- the ONLY stage a model plugs into
```

`scout.extraction.DeterministicExtractor` is the only `Extractor`
implementation in this codebase: regex-based, `extraction_method`
never starts with `"model:"`, `confidence` fixed at 1.0. A future
Mistral-based extractor implements the identical `Extractor` Protocol
(`def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]`),
sets `extraction_method="model:<name>"`, and MUST supply an explicit,
non-`None` `confidence` — enforced by `scout.pipeline.run_scout`
regardless of which `Extractor` produced the candidate (§6). Nothing in
`scout.pipeline`, `scout.adapters`, or any of `evidence/` imports or
references Mistral, any other model provider, or any specific model API
— checked implicitly by `tests/test_scout_boundaries.py` (no such import
exists to check for) and directly inspectable in every file in both
packages.

## 10. Initial source adapters

One adapter class (`scout.adapters.FixtureSourceAdapter`), parameterized
by a fixed tuple of `RawDocument`s — not four separate classes for
papers/patents/github/docs, since `source_kind` (a plain string field)
is what actually distinguishes them, not the class. Two fixture
documents exist (`scout/fixtures.py`): one `"paper"`, one
`"github_repo"`, both using an unambiguous `ENTITY:`/`RELATION:`/`FACT:`
line format designed specifically so `DeterministicExtractor` can parse
them without a model. No live network access anywhere in `scout/` — a
real requirement for deterministic tests, per §7 of the prompt.

**A real bug this format caught during implementation**: an earlier
draft of the `RELATION:` line used `<from_label> -<type>-> <to_label>`
(arrow syntax). It mis-parsed the moment a label itself contained a
hyphen — `rheo-sim` — because the hyphen in the label collided with the
hyphen that starts the arrow. Caught by actually running the fixtures
through the extractor (not by inspection), fixed by switching to an
unambiguous `<from_label> | <type> | <to_label>` pipe-delimited format.
Documented here rather than silently fixed, per this project's
established practice of recording real bugs found during
implementation rather than only the final working state.

## 11. The architectural question: `agent -> graph` vs. `agent -> observation -> validation boundary -> canonical state -> graph`

The second shape is correct, with one adjustment the prompt's own sketch
doesn't quite name: **"canonical state" in that chain is not
`core.canonical.CanonicalState`.** It is the Trust Graph / evidence pool
— a separate, less-authoritative structure that Phase 14 already
carefully distinguished from `CanonicalState` (§O: "only a `Derived
value`, reviewed and promoted through the unchanged adapter ->
validate_candidate gate, ever crosses this line"). The actual chain SCOUT
implements:

```
agent (SCOUT)
   |
observation (evidence.types.Observation, via scout.interface.Extractor)
   |
validation boundary (evidence.admission -- NOT core.canonical.validation)
   |
Trust Graph attachment (evidence.trust_graph -- NOT CanonicalState.edges)
   |
[STOP -- CanonicalState is not reached this phase]
```

Why this preserves the existing architecture's invariants, and
`agent -> graph` directly would not: without the admission gate, SCOUT
could put a malformed or dangling-reference object straight into the
pool, and the Trust Graph (a derived view with no validation of its own
— §4) would silently reflect it. With the gate, every object the graph
can ever show already passed a structural check, exactly mirroring why
`CanonicalState` is never mutated except through `validate_candidate`.
The one thing this chain deliberately does **not** do — unlike the
prompt's sketch, which continues on to `CanonicalState` — is cross
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §O's one crossing rule. SCOUT
produces `Observation`/`Referent`/`ClaimedRelationship`, never a
`Derived value`, and nothing in this codebase promotes one into a
`CandidateDelta`. That promotion step (§R steps 3-5: `NormalizedRecord`,
conflict-resolution-as-`Derived-value`, the pool→adapter bridge) remains
deliberately unimplemented — see §0.

## 13. What this phase deliberately does not implement

- `NormalizedRecord`/`Condition` (§R step 3) — SCOUT's `Observation.content`
  stays in extractor-defined form; no property/value/unit normalization
  layer exists yet.
- `Derived value` / conflict resolution (§R step 4) — conflicting
  Observations coexist in the pool (proven by
  `tests/test_scout_pipeline.py::test_temporal_update_second_observation_of_same_referent_does_not_overwrite_first`)
  but nothing resolves them.
- The pool→adapter promotion bridge (§R step 5) — no code path from
  `evidence/` to `adapters/` or `core.canonical` exists.
- Warehouse/graph *indexes* beyond the Trust Graph's own derived view
  (§R step 6) — `pool.observations_about`/`relationships_touching` are
  linear scans, adequate at fixture scale, not a real index.
- Any model (Mistral or otherwise), any live source adapter, any
  database, any message broker or distributed worker, any autonomous
  agent loop, entity-resolution/deduplication, or a real FEP/active-
  inference implementation. All per this phase's explicit instructions
  and `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §S.

## 14. Verification

`python3 -m pytest -q` — 174 passed (109 pre-existing + 65 new: 14
identity, 5 pool, 9 admission, 7 trust graph, 15 metrics, 10 pipeline, 5
boundary). No existing test file was modified; every new file is new
(`git status --short` shows only new, untracked paths). No file under
`core/`, `morpho/`, `adapters/`, `backends/`, or `runtime/` was touched.
