# canonical-state

Derived from [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime).
This distribution retains its package name and scoped API; it is not the full
scientific runtime or Computational Instrumentation Workbench.

One immutable, versioned state is the single source of truth. Every view
of it — a 3D scene, an SVG diagram, a graph report — is a **derived
projection that can never write back**.

Pure standard library. **Zero runtime dependencies**, on purpose.

```bash
pip install canonical-state
```

## The problem it solves

State drifts because there are several places to write it. A value gets
corrected in the dashboard, the export still has the old one, and the
simulation was seeded from a third copy. Nobody can say which is current,
because "current" was never defined — only "most recently touched", per
copy.

This library makes one copy canonical and everything else a projection.
A projection has no write path, so it cannot drift: it is recomputed, or
it is stale and recomputable. The property is structural, not a
convention anyone has to remember.

## Versions are content-addressed, and minted in exactly one place

```python
from core.canonical.schema import StateSchema, FieldSchema, FieldConstraints
from core.canonical.version import create_genesis_version, ProvenanceInfo
from core.canonical.delta import CandidateDelta, CandidateChange
from core.canonical.validation import validate_candidate

schema = StateSchema(
    schema_version="1.0.0",
    fields={"temperature": FieldSchema(
        id="temperature", type="scalar", unit="K", default=300.0,
        constraints=FieldConstraints(min=0.0, max=1000.0))},
)

genesis = create_genesis_version(schema, timestamp="2026-01-01T00:00:00Z")
# genesis.id -> '165750b3281a63bf...'   genesis value -> 300.0

who = ProvenanceInfo(author="operator", transaction_id="t1", source="manual")
accepted = validate_candidate(schema, genesis.state, CandidateDelta(
    version_from=genesis.id, transaction_id="t1",
    timestamp="2026-01-01T00:01:00Z",
    changes=(CandidateChange(path="fields.temperature.value",
                             operation="replace", old_value=300.0,
                             new_value=455.0, provenance=who),)))
# accepted.id -> 'bb4255b4985e6369...'  accepted.parent -> genesis.id
```

A change that violates the schema does not become a version, and the
refusal says which rule:

```python
refused = validate_candidate(schema, accepted.state, CandidateDelta(
    version_from=accepted.id, transaction_id="t2",
    timestamp="2026-01-01T00:02:00Z",
    changes=(CandidateChange(path="fields.temperature.value",
                             operation="replace", old_value=455.0,
                             new_value=5000.0, provenance=who),)))

[(e.code, e.message) for e in refused]
# [('OUT_OF_RANGE', '5000.0 > max 1000.0')]
```

`validate_candidate` returns *either* a `Version` or a list of errors.
There is no third outcome and no partially-applied state.

A version's id is a function of its content, not of the clock:

```python
again = create_genesis_version(schema, timestamp="2099-12-31T00:00:00Z")
again.id == genesis.id          # True  -- same content, same identity
genesis.state.fields["temperature"].value   # 300.0, still; nothing mutates
```

## The rules that make it hold

**One minting point.** `Version.id` is always computed from the state, so
a version's id can never disagree with its own content — the constructor
does not accept one. Every version after the genesis is produced by
`validate_candidate`; nothing else in the library returns a `Version`.

**No write-back path.** Projections and backends receive a frozen
`ProjectedState` or Morpho IR. None of them can reach a `CanonicalState`
or a `Version`. A simulation or an estimator that wants to change
something submits a `CandidateNextState` through
`runtime.feedback_loop`, and it goes through the same door as a typed
human edit.

**Identity is never silently corrected.** If a state's `fields` key
disagrees with the `Field.id` under it, construction raises. It is not
repaired, because a repaired identity is a different object wearing the
old one's name.

**Immutability is enforced, not documented.** `CanonicalState` freezes
its own `fields` mapping and `edges` tuple at construction, so a caller
holding a reference cannot mutate what someone else is reading.

## What is in the box

| package | what it does |
|---|---|
| `core.canonical` | the state, its schema, typed deltas, validation, content-addressed versions, an in-memory version store |
| `core.projection` | the frozen read-only view handed to everything downstream |
| `morpho` | a small declarative language — lexer, parser, AST, IR — with per-node identity and provenance |
| `backends` | deterministic compilers from IR to a Three.js scene, an SVG diagram, and a graph report |
| `runtime` | the candidate → validate → commit-or-reject gate |
| `adapters` | JSON and CSV ingestion at the boundary |
| `renderer` | a browser view of a projected state (see below) |

## Two backends deliberately implement nothing

`backends/simulation` and `backends/neural` are **interface shapes only** —
a `Protocol` and a couple of frozen dataclasses each. They say so in
their own docstrings, and they are shipped as seams so a physics engine
or an estimator has a fixed contract to build against, one that routes
its output through validation like any other candidate.

They are not a physics engine and not a model, and this package does not
claim otherwise.

## This is not a numerical library

It contains no mathematics. The shipped packages import no numeric
module at all — no `math`, no `statistics`, nothing — and the arithmetic
in them is set difference, list concatenation, SVG layout margins and
token indices.

It is infrastructure for state, and it is domain-neutral: the same
property that makes it useful for a scientific pipeline makes it useful
for configuration, engineering models, or anything else where several
views of one truth have to stay honest.

## The renderer

`renderer/index.html` opens a projected state in a browser. three.js is
**vendored** in `renderer/vendor/` rather than fetched, so the page has
no runtime dependency on a CDN — it works offline and the exact bytes
being run are the ones shipped. It is MIT-licensed and carries its own
notices there and in `NOTICE`.

No Python module imports it; it is an asset, not a dependency.

## Requirements

Python 3.10+. Nothing else.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.

Developed at Notation Systems Inc. as one of two independent programs in
a larger repository, and extracted here because the state model is
useful on its own. Its sibling, `provenance-pool`, ships the evidence
model; the two share no code, measured in both directions.

## Contributing

Issues and pull requests welcome. The test suite is the specification —
if you change behaviour, the test that pinned it should change with it,
and in the same commit.

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```
