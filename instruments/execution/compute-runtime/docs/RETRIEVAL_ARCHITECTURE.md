# Retrieval Architecture — Phase 15

This document is Phase 15's required deliverable: the retrieval/context
boundary between SCOUT's evidence pool (`docs/SCOUT_ARCHITECTURE.md`)
and a future computational layer (`InquiryState`, still unimplemented).
It documents `retrieval/` — a new, deterministic, read-only package —
and nothing else changed: `core/`, `morpho/`, `adapters/`, `backends/`,
`runtime/`, and `evidence/`'s existing behavior are all untouched (the
one addition to `evidence/` is a new, pure `EvidencePool.fingerprint()`
method — see §Evidence versioning below).

## 0. The pipeline this phase completes

```
Evidence (evidence/, Phase "SCOUT")
     |
Trust Graph (evidence.trust_graph -- derived view, unchanged)
     |
RetrievalQuery (retrieval/query.py)              <-- NEW
     |
RetrievalEngine (retrieval/engine.py)             <-- NEW
     |
RetrievalResult (retrieval/result.py)              <-- NEW
     |
ContextPackage (retrieval/context.py)               <-- NEW
     |
InquirySeam (retrieval/seam.py)                       <-- NEW, deliberately minimal
     |
[future InquiryState -- NOT implemented this phase]
```

This is the layer `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` and
`docs/COMPUTATIONAL_COMMONS.md` both discussed only conceptually
("retrieval," "reusable context," "InquiryState") — Phase 15 is its
first real implementation, for the deterministic case only. No model,
no vector search, no external database, per this phase's explicit
constraints (§13 below).

## 1. What retrieval consumes — the exact existing objects

Investigated first, per this phase's own instruction not to invent a
parallel evidence model. Retrieval consumes exactly:

- `evidence.pool.EvidencePool` — read-only; every lookup already
  exposed (`get_referent`, `get_observation`, `get_record`,
  `get_document`, `get_source`, `all_referents`,
  `all_claimed_relationships`, `all_observations`,
  `relationships_touching`) is used as-is. The only new pool method,
  `fingerprint()`, is additive and itself read-only (§Evidence
  versioning).
- `evidence.trust_graph.build_trust_graph(pool)` — the existing derived
  graph view, used unmodified as the traversal substrate.
- `evidence.types.{Source, Document, Record, Observation, Referent,
  ClaimedRelationship}` — read, never constructed or mutated by
  `retrieval/`.

Nothing in `retrieval/` defines a competing `Entity`/`Relationship`/
`Observation` type. `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`'s own
naming-collision warning (avoid a second `Entity`, avoid a second
`Relationship`) is honored a second time here by simply not introducing
new object types for the same concepts at all.

## 2. Authoritative vs. derived vs. temporary objects

| Object | Kind | Mutable? | Authority |
|---|---|---|---|
| `CanonicalState`/`Version` | Authoritative | No (immutable, versioned) | Sole source of truth (unchanged, untouched by this phase) |
| `evidence.pool.EvidencePool` contents (`Source`/`Document`/.../`ClaimedRelationship`) | Authoritative (for evidence, not truth) | No (append-only) | The evidence record — uncertain, conflicting, never authoritative over `CanonicalState` |
| `evidence.trust_graph.TrustGraph` | Derived | N/A (recomputed, never stored) | A view, not a store — `docs/SCOUT_ARCHITECTURE.md` §4 |
| `retrieval.query.RetrievalQuery` | Derived (content-addressed from its own fields) | No | Not authoritative over anything — a request |
| `retrieval.result.RetrievalResult` | Derived (references into the pool only) | No | Not authoritative — deterministically identifiable against one query and one evidence fingerprint (§7 distinguishes this from historical reconstruction) |
| `retrieval.context.ContextPackage` | Derived (composed from one or more results) | No | Not authoritative — deterministically identifiable *selection*, never a copy (§7) |
| `retrieval.seam.InquirySeam` | Temporary marker | No (itself immutable — but represents the *opening* of a temporary computation) | Not authoritative — a seam, not a store |
| future `InquiryState` | Temporary, disposable | Yes (explicitly, per design) | Never authoritative — the eventual, still-unimplemented computational workspace |

The one property every "derived"/"temporary" row shares: none of them
can ever become authoritative by construction, because none of them
hold anything but ids referencing the authoritative rows above them.
There is no code path anywhere in `retrieval/` that writes a
`RetrievalResult`'s or `ContextPackage`'s referenced ids back into
`evidence/` or `core.canonical` — checked by
`tests/test_retrieval_boundaries.py`.

## 3. The authority boundary, explicitly

```
retrieval/  ---->  evidence/  (read-only: get_*, all_*, fingerprint())
retrieval/  ---->  core.canonical.*  NEVER (no import at all)
```

Enforced by `tests/test_retrieval_boundaries.py`:
- no import of `backends/`, `renderer/`, or `runtime/`;
- no import of `core.canonical.validation`, and no import of
  `validate_candidate`/`make_version`/`create_genesis_version` by name;
- no AST `Call` node anywhere in `retrieval/` whose called name is
  `validate_candidate`;
- no AST `Call` node anywhere in `retrieval/` whose method name is any
  of the pool's `put_*` mutators — retrieval cannot write to the
  evidence pool either, not just to `core.canonical`;
- no import of `Version`/`CanonicalState` by name;
- and, symmetrically, `core/` never imports `retrieval/`.

## 4. RetrievalQuery — minimum representation

```python
RetrievalQuery(
    id,                      # content_hash of everything below
    entity_natural_keys,      # exact entity lookup / traversal seeds
    relationship_types,        # restrict traversed/returned edges; () = no restriction
    source_kinds,                # restrict returned Observations by Source.kind
    epistemic_statuses,            # restrict by retrieval.epistemic classification
    text_terms,                      # substring match over Observation.content values
    traversal_depth,                   # bounded BFS depth from the seeds
    limit,                                # cap on returned Referent count (None = unbounded)
)
```

Every field considered by the prompt's own sketch (`query_id`, entities,
relationship types, source filters, epistemic-status filters, metadata
filters, traversal depth, text terms, result limit) is present except a
generic "metadata filters" catch-all — investigated and rejected as
premature: nothing in `evidence.types` currently exposes free-form
metadata beyond what `source_kinds`/`epistemic_statuses`/`text_terms`
already cover, and adding an open-ended filter with no concrete
consumer would be exactly the "speculative infrastructure" this phase
was told not to introduce. `id` is always derived
(`retrieval.query.make_retrieval_query`), never caller-supplied — same
discipline as `make_version`/every `evidence.types.make_*` factory —
and every list field is deduplicated and sorted before hashing, so two
queries expressing the same request in a different order or with
accidental repeats get the identical `id`
(`tests/test_retrieval_query.py::test_query_identity_ignores_input_order_and_duplicates`).

## 5. RetrievalResult — what it answers

| Question | Answered by |
|---|---|
| What was queried? | `query_id` (dereference the `RetrievalQuery` if the caller still has it) |
| What was returned? | `referent_ids`/`relationship_ids`/`observation_ids`/`source_ids` |
| Why was it returned? | `filters_applied` (human-readable) + `traversal_depth` |
| Which source versions were used? | `evidence_version_id` (`EvidencePool.fingerprint()` at query time) |
| Which graph entities were involved? | `referent_ids` |
| Which relationships were traversed? | `relationship_ids` |
| What retrieval configuration was used? | `retrieval_method` + `filters_applied` + `traversal_depth` |
| Is the result deterministically identifiable? | Yes — `result.id` is a content hash of every field above; recomputing the identical query against the identical evidence snapshot always yields the identical `id`. This is a narrower claim than "reproducible": it means the *identity* is stable, not that the evidence *contents* behind an older `evidence_version_id` can still be recovered once the pool has since changed — see §7. |

`RetrievalResult` stores only sorted tuples of ids — never a copied
`Referent`/`Observation`. "Ordering is not ranking": `ordering` is
always `"sorted_by_id"` in this phase's implementation, stated
explicitly rather than left implicit, because id-sort is an arbitrary,
stable tiebreaker, not a relevance/quality signal — no ranking model
exists in this codebase (consistent with `evidence.fep_interface`'s own
refusal to fabricate a `priority` without real inputs).

### Evidence versioning

`EvidencePool.fingerprint()` (the one new method added to `evidence/`
this phase) is a content hash of the sorted id sets of every object
category the pool holds. Two pools with identical contents fingerprint
identically regardless of insertion order; any change to the pool —
even one unrelated to a given query's visible result — changes the
fingerprint. This is deliberately coarse: a `RetrievalResult`'s `id`
therefore changes whenever the *pool* changes, even if the specific
referents/relationships/observations that satisfy one narrow query
happen to be identical before and after
(`tests/test_retrieval_engine.py::test_source_version_sensitivity`).
This was a specific, literal requirement (§7 of the phase prompt: "the
system must be able to distinguish the new retrieval from the old one")
and is met by including the whole-pool fingerprint in the result's
identity hash, not just the returned id sets.

**What `fingerprint()` does and does not establish, stated precisely
(post-Phase-15 audit finding, resolved as a design decision in Phase 16
and now implemented — see §7):** `fingerprint()` gives every
`RetrievalResult` and `ContextPackage` a stable, content-addressed
*identity* tied to one moment of evidence state. On its own it gives the
system no memory of that moment once the pool has moved on. **Phase 16
adds exactly one thing to close that gap: `EvidencePool.fingerprint_history()`**
— an append-only record of which fingerprints were actually observed,
described fully in §7. It does not change what `fingerprint()` itself
returns or how it is computed (unchanged from Phase 15, byte-for-byte).

**Phase 17: `fingerprint()` now covers seven categories, not six.**
`evidence/types.py` gained a seventh peer type, `DerivedValue` (a value
synthesized from multiple `Observation`s and/or other `DerivedValue`s,
with a stated method — see `docs/SCOUT_ARCHITECTURE.md` §3). Because
`fingerprint()`'s own contract is "a content hash of exactly which
object ids this pool currently holds," omitting real pool content from
it would be the actual defect — so its payload now includes
`"derived_values"` unconditionally, even when empty. This changes
`fingerprint()`'s *output value* relative to Phase 16 for every pool
(the hashing algorithm and the six existing keys are otherwise
unchanged), which is an intentional, accepted consequence, not a
regression — no committed test in this repository asserts a literal
fingerprint string. **`DerivedValue` is deliberately not retrievable in
Phase 17**: it exists upstream in `evidence/`, participates in
`fingerprint()`/`fingerprint_history()` exactly like every other
category, but `RetrievalQuery`, `RetrievalResult`, and `ContextPackage`
remain completely unaware it exists — no field references it, and
`retrieval/` contains no mention of it anywhere
(`tests/test_derived_value_boundaries.py`). `RetrievalQuery.id` has no
dependency on evidence content at all and is therefore byte-for-byte
unchanged from Phase 15/16; `RetrievalResult.id`/`ContextPackage.id`
shift only because the opaque `evidence_version_id` they already
depended on shifts — their own hash *inputs* (the same ten and six
fields, respectively) are untouched.

## 6. ContextPackage

```python
ContextPackage(
    id,                       # content_hash of everything below
    retrieval_result_ids,      # which RetrievalResults contributed
    referent_ids,                # union, deduplicated, sorted
    relationship_ids,
    observation_ids,
    source_ids,
    evidence_version_ids,          # every DISTINCT evidence_version_id among contributors
)
```

`ContextPackage` is not `CanonicalState` and not a new authoritative
store — `retrieval.context.build_context_package` never copies a
`Referent`/`Observation`/etc., it only unions and sorts id sets from one
or more `RetrievalResult`s. Dereferencing (`retrieval.context.referents`/
`.relationships`/`.observations`/`.sources`) always returns the exact
same object instances already stored in `evidence/`
(`tests/test_context_package.py::test_context_package_holds_references_not_copies`
asserts `is`, not just `==`).

**Composition across different evidence versions is recorded, not
hidden.** If the contributing `RetrievalResult`s were queried against
different pool states, `evidence_version_ids` has more than one entry
— the caller can see that directly, rather than the `ContextPackage`
silently presenting a blend of two snapshots as if it were one coherent
moment (`tests/test_context_package.py::test_composition_across_different_evidence_versions_is_recorded_not_hidden`).

## 7. Deterministic identifiability vs. historical reconstructability

**This section replaces an earlier looser use of "reproducible"
throughout this document (found and flagged by a post-Phase-15
architectural audit).** The word conflated two genuinely different
claims. Both are real; only one is currently guaranteed.

**Deterministically identifiable (guaranteed, tested):** given the same
query and the same evidence *fingerprint*, the same `RetrievalResult.id`
and `ContextPackage.id` are always produced. This is an identity
guarantee — it says two computations of the same thing agree — and it
holds unconditionally, independent of wall-clock time, process, or
`PYTHONHASHSEED`:

```
same evidence version + same RetrievalQuery + same retrieval configuration
    => same RetrievalResult.id
    (tests/test_retrieval_engine.py::test_retrieval_result_is_deterministic_across_calls)

same RetrievalResult(s)
    => same ContextPackage.id
    (tests/test_context_package.py::test_context_package_reproducible_from_same_result)
```

Both are additionally checked across three different `PYTHONHASHSEED`
values in separate subprocesses
(`tests/test_retrieval_engine.py::test_retrieval_result_deterministic_across_hash_seeds`),
the same discipline `tests/test_versioning.py` and
`tests/test_trust_graph.py` already established — an in-process test
cannot exercise `PYTHONHASHSEED` at all, since Python only applies it at
interpreter startup.

**Historically reconstructable evidence *contents* (still NOT
guaranteed — a separate, explicitly deferred capability):** given only
a `ContextPackage` and the `evidence_version_id`/`evidence_version_ids`
it recorded, can the exact evidence *contents* that produced it be
recovered after the `EvidencePool` has since changed? **No, and Phase 16
does not change this answer.** `EvidencePool.fingerprint()` (§5) remains
a snapshot of current content, not a content archive. A `ContextPackage`
built yesterday remains *deterministically identifiable* forever (its
`id` never changes, and recomputing the identical query against a pool
that still happens to match the recorded fingerprint reproduces it
exactly), but if the pool has since grown, there is still no way to ask
"show me the evidence objects that were live when fingerprint `X` was
observed" — only, now, "was fingerprint `X` ever observed at all" (see
below), which is a strictly weaker, membership-only answer.

**Fingerprint history (Phase 16 — implemented):** `EvidencePool` now
maintains a minimal, append-only history of observed fingerprints,
exposed as `EvidencePool.fingerprint_history() -> Tuple[str, ...]`. Each
of the six `put_*` methods (`put_source`, `put_document`, `put_record`,
`put_observation`, `put_referent`, `put_claimed_relationship`) is the
observation boundary: immediately after an object is stored, the pool
compares its own current `fingerprint()` against the last recorded
history entry and appends only if they differ
(`evidence/pool.py::_observe_fingerprint`, called from all six `put_*`
methods, called by none of the read accessors). This is why a query
executed many times, or `fingerprint()`/`fingerprint_history()` read
many times, never grows the history — only a `put_*` call whose result
actually changes the pool's fingerprint does
(`tests/test_evidence_pool.py::test_fingerprint_history_unaffected_by_repeated_duplicate_put`,
`::test_fingerprint_history_accessor_has_no_side_effects`). `fingerprint()`
itself is byte-for-byte unchanged from Phase 15 — it neither calls nor
is called by the history mechanism from its own body.

This establishes exactly one new fact per entry: **"evidence state `F`
existed and was observed by the system."** It deliberately does **not**
establish "the complete evidence contents that produced `F` can still be
reconstructed" — those are different claims, and the fingerprint history
only ever supports the first one
(`tests/test_evidence_pool.py::test_fingerprint_history_introduces_no_reconstruction_mechanism`
asserts no method on `EvidencePool` maps a fingerprint back to object
ids or contents). Recovering actual historical evidence *contents*
would require a separate, still-undecided mechanism (e.g. retaining old
pool snapshots, or content-addressed archival storage) that this
implementation does not adopt, commit to, or design.

*Why a fingerprint history rather than a `VersionStore` (design
rationale, recorded for continuity):* `core.canonical.version.py::InMemoryVersionStore`
was considered and rejected as the model to reuse here, for reasons
worth recording rather than re-litigating later:
- **Minimal and additive** — a flat, append-only tuple of already-computed
  strings, not a new object graph.
- **Deterministic** — each entry is exactly `EvidencePool.fingerprint()`'s
  existing, already-tested output; nothing new is computed.
- **Preserves historical identity without preserving historical content**
  — it answers "did the system ever see this state" without pretending
  to answer "what was in it," which is the honest boundary of what a
  bare list of hashes can support.
- **Does not prematurely commit to persistent evidence snapshots** — a
  `VersionStore`-shaped mechanism would imply (or at least invite) parent
  chains, snapshot persistence, and eventually reconstruction machinery
  that Phase 14's own evidence model never asked for and this decision
  does not want to back into. `CanonicalState` needed a `VersionStore`
  because *reconstructing prior state* is its whole purpose (§18/§19 of
  `docs/ARCHITECTURE_SPEC.md`); the evidence pool has no equivalent
  requirement yet — only the narrower one of proving a fingerprint was
  once real.
- **Leaves full evidence reconstruction as a genuinely open, future
  architectural decision** — this document takes no position on whether
  it will ever be needed, only records that it is not decided and not
  built.

**What was actually implemented, and what deliberately did not change:**
one new private field (`EvidencePool._fingerprint_history`), one new
private method (`_observe_fingerprint`, called from the six `put_*`
methods only), and one new public accessor
(`fingerprint_history() -> Tuple[str, ...]`, returning a fresh tuple
copy each call — never a reference to the internal list). Nothing else
in `evidence/pool.py` changed. `retrieval/` was not touched at all — no
file under `retrieval/` appears in this change. `RetrievalResult.id` and
`ContextPackage.id` were verified, not merely assumed, to be unaffected:
the exact same fixture query against the exact same fixture evidence
produces byte-identical `fingerprint()`, `RetrievalResult.id`, and
`ContextPackage.id` values before and after this feature exists
(confirmed against recorded values from the Phase 15 verification pass —
see `tests/test_retrieval_engine.py::test_retrieval_result_id_unaffected_by_fingerprint_history_mechanism`
for the regression form of this check). Retrieval remains strictly
read-only with respect to `EvidencePool`: no file under `retrieval/`
calls any `put_*` method or `_observe_fingerprint` directly, and the six
`tests/test_retrieval_boundaries.py` checks (import boundaries, no
`validate_candidate` calls, no pool-mutation calls) all still pass
unmodified.

## 8. Minimum retrieval capabilities — what is and isn't implemented

| Capability | Implemented? | How |
|---|---|---|
| Exact entity lookup | Yes | `entity_natural_keys` matched against `Referent.natural_key` |
| Exact relationship lookup | Yes | via `relationship_types` filter + traversal at `depth=0`/`1` |
| Source/document lookup | Yes | `source_kinds` filter; `source_ids` in every result |
| Field/property lookup | Yes | `text_terms` substring match over `Observation.content` values |
| Provenance filtering | Yes | `evidence_version_id` per result; full trace via dereferencing (§Provenance below) |
| Epistemic-status filtering | Yes | `epistemic_statuses`, via `retrieval.epistemic.classify_epistemic_status` — reuses `docs/COMPUTATIONAL_COMMONS.md` §K's taxonomy, does not invent a second one |
| Simple metadata filtering | Yes, narrowly | `source_kinds` is the one metadata filter implemented; see §4 on why a generic filter was not added |
| Graph-neighborhood traversal | Yes | bounded BFS over the Trust Graph, `retrieval.engine._bounded_neighborhood` |
| Bounded traversal depth | Yes | `traversal_depth`, enforced (0 = seeds only) |
| Simple text/token matching | Yes | `text_terms`, case-insensitive substring |
| Embeddings | **No** | explicitly out of scope this phase |
| Vector search | **No** | explicitly out of scope this phase |
| Semantic/LLM retrieval | **No** | explicitly out of scope this phase — see §Future seam |

## 9. Provenance preservation

Traced end-to-end and tested
(`tests/test_context_package.py::test_provenance_trace_from_context_to_source`):

```
ContextPackage
     |
Referent (retrieval.context.referents)
     |
ClaimedRelationship (retrieval.context.relationships, touching that Referent)
     |
Observation (relationship.observation_id -> retrieval.context.observations)
     |
Record (observation.record_ids[0] -> pool.get_record)
     |
Document (record.document_id -> pool.get_document)
     |
Source (document.source_id -> pool.get_source)
```

Every hop is a plain id dereference against the same, unmodified
`evidence/` accessors SCOUT already used — `retrieval/` adds no new
provenance mechanism, it exercises the one that already existed.

## 10. Retrieval ≠ reasoning — the hard boundary, as implemented

`retrieval.engine.DeterministicRetrievalEngine.retrieve` performs
exactly: seed lookup, bounded BFS, set intersection/union for filters,
sort. There is no branch anywhere in it that constructs a new
`Observation`, a new `ClaimedRelationship`, or any object not already
present in the pool it was given. It cannot infer a new claim, because
it has no code path that calls any `evidence.types.make_*` factory or
any `evidence.admission.admit_*` function at all — confirmed by
`tests/test_retrieval_boundaries.py::test_retrieval_never_writes_to_the_evidence_pool`
and, structurally, by `retrieval/engine.py` never importing
`evidence.admission` or `evidence.types.make_*` in the first place.

## 11. The InquiryState seam — deliberately not InquiryState

`retrieval.seam.InquirySeam` holds exactly two fields: `context_id` and
`opened_at`. It has no mutable slots, no hypothesis storage, no
computation. It exists only to prove the boundary between
`ContextPackage` (selected persistent reality) and a future
`InquiryState` (a temporary computational world built from that
reality) is already representable in code, without committing to
InquiryState's eventual shape — exactly what §12 of the phase prompt
asked for and no more. What remains **intentionally deferred**:

- Any mutable inquiry workspace (hypotheses, derived quantities,
  constraints, candidate regions, annotations — all of §5's worked
  example in `docs/COMPUTATIONAL_COMMONS.md`).
- Any promotion path from an inquiry's output back toward
  `evidence.types.Referent`/`ClaimedRelationship` or, further
  upstream, a `CandidateDelta`.
- Any persistence for `InquirySeam`/`InquiryState` beyond one Python
  object's lifetime — no store, no versioning, no identifiability
  guarantee for whatever happens *after* the seam is opened (only the
  `ContextPackage` it was opened from is deterministically identifiable
  — see §7 for why that is a narrower claim than "reconstructable").

## 12. Compute amortization — measured, not claimed

`tests/test_retrieval_amortization.py::test_extraction_runs_once_regardless_of_later_retrieval_count`
wraps `scout.extraction.DeterministicExtractor` in a call-counting
subclass, runs SCOUT once (one `extract()` call per `Record`), then
issues five independent `RetrievalQuery`s and composes their results
into one `ContextPackage` — and asserts the extractor's call count is
unchanged afterward. This is the one thing actually measured in this
phase: **extraction is not re-invoked by retrieval, at all, regardless
of how many queries run against the same pool.** No throughput, latency,
or cost number is claimed anywhere in this document or its tests — per
this phase's explicit instruction not to fabricate performance claims,
only what is actually measurable (a call count) is reported.

The architectural claim this supports: expensive work (source
acquisition, extraction) happens once per `Record`, at SCOUT time;
retrieval and context construction thereafter are pure functions over
already-computed, already-stored data — repeatable at whatever
frequency a future computation layer needs, without paying extraction's
cost again.

## 13. No database yet

Confirmed by inspection, not just by instruction: `retrieval/` imports
nothing beyond `evidence/` and the Python standard library. No
Neo4j/PostgreSQL/DuckDB/Elasticsearch/Qdrant/Milvus/Weaviate/Pinecone/
RDF-store/warehouse dependency exists anywhere in this repository.
Traversal is a linear BFS over `EvidencePool.all_referents()`/
`all_claimed_relationships()` — adequate at fixture scale, explicitly
not a real index, exactly matching
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §R step 6's own sequencing
("indexes are derived and can be rebuilt; getting the underlying record
shapes right first avoids re-deriving a wrong index twice").

## 14. Future semantic/vector retrieval seam

```python
class RetrievalEngine(Protocol):
    def retrieve(self, pool: EvidencePool, query: RetrievalQuery) -> RetrievalResult: ...
```

The entire seam is this one Protocol (`retrieval/engine.py`). A future
`SemanticRetrieval`, `VectorRetrieval`, `GraphRetrieval`, or
`HybridRetrieval` engine implements it and must return the same
`RetrievalResult` shape — proven, not just asserted, by
`tests/test_retrieval_engine.py::test_second_engine_implementation_can_satisfy_the_same_protocol`,
which implements a second, trivial engine (`method_name =
"stub:always_empty_v1"`) and shows it produces a structurally valid
result. No stub classes for the unimplemented engine kinds were added —
per this phase's "do not introduce speculative infrastructure" rule,
the Protocol itself is the extension boundary; five empty subclasses
would add names without adding a capability. A future Mistral or
embedding-based engine improves *which* referents/observations a query
returns; it does not get to redefine what a `RetrievalResult` or
`ContextPackage` means — that contract is fixed by this phase.

## 15. Verification

`python3 -m pytest -q` — 268 passed as of Phase 17 (235 after Phase 16 +
33 new: 31 in `tests/test_evidence_derived_value.py` covering
`DerivedValue` identity/admission/pool/fingerprint semantics, 2 in
`tests/test_derived_value_boundaries.py` proving `evidence/` never
imports `retrieval/` and `retrieval/` never references `DerivedValue`).
`ruff` and `mypy` clean on every file Phase 17 touched or added. Cross-
`PYTHONHASHSEED` determinism reconfirmed for all seven mechanisms that
make such a claim (`Version.id`, `TrustGraph.connected_components`,
`RetrievalResult.id`/`ContextPackage.id`, `fingerprint_history()`, and
now `DerivedValue.id` and `fingerprint()`/`fingerprint_history()` with
`DerivedValue`s present). No file under `core/`, `morpho/`, `adapters/`,
`backends/`, `runtime/`, `scout/`, or `retrieval/` was modified by
Phase 17 — the only implementation files touched are `evidence/types.py`,
`evidence/pool.py`, and `evidence/admission.py`. `RetrievalQuery.id` is
byte-for-byte unchanged from before Phase 17 existed (verified against
the value recorded in the Phase 15 audit); `RetrievalResult.id`/
`ContextPackage.id` shift only through the already-opaque
`evidence_version_id` they depended on before, not through any change to
their own hash inputs.
