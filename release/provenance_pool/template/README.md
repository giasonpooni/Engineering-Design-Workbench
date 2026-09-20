# provenance-pool

Derived from [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime).
This distribution retains its package name and scoped API; it is not the full
scientific runtime or Computational Instrumentation Workbench.

An append-only evidence pool where every value carries its provenance,
and the admission gate refuses what it cannot ground.

Pure standard library. **Zero runtime dependencies**, on purpose.

```bash
pip install provenance-pool
```

## The problem it solves

Scientific data pipelines lose the difference between *a thing that was
measured* and *a thing that was computed*. Both end up as a float in a
column. Six months later nobody can tell which is which, a model trains
on simulation output labelled as observation, and the error is invisible
because the number was always well-formed.

This library makes that distinction structural instead of documentary.

## Four classes, assigned at ingest, never promoted

Every observation declares an `extraction_method`. Its evidence class is
a **total function of that declaration** — and the method is part of the
observation's content-addressed identity:

| class | what it means |
|---|---|
| `measured` | a physical measurement by a declared instrument method |
| `asserted` | a source's claim, carried by extraction from a document |
| `computed` | the result of a declared computation |
| `derived` | inference over other evidence |

There is **no promotion path, because there is no mutation path.** A
different class means a different `extraction_method`, which means a
different observation with a different identity. Nothing can be quietly
upgraded from `computed` to `measured` — the upgrade would produce a
new object, and the old one would still be there.

An unrecognised method is **refused, never guessed.**

## What it looks like

```python
from evidence.pool import EvidencePool
from evidence.admission import admit_document, admit_record, admit_observation
from evidence.types import make_source, make_document, make_record, make_observation
from evidence.classes import class_of

pool = EvidencePool()
source = make_source(kind="journal", name="J. Mat. Chem.")
pool.put_source(source)

doc = make_document(source_id=source.id, raw_content="Tm = 1811 K",
                    retrieval_method="manual", retrieved_at="2026-01-01T00:00:00Z")
pool.put_document(doc)

rec = make_record(document_id=doc.id, locator="p1", raw_content="Tm = 1811 K")
pool.put_record(rec)

obs = make_observation(
    record_ids=(rec.id,),
    extraction_method="regex:melting_point_v1",
    content={"property": "melting_point", "value": 1811.0, "unit": "K"},
    confidence=1.0, extracted_at="2026-01-01T00:00:00Z")
admit_observation(pool, obs)
```

The same *content*, declared as a measurement it never was, is a
different object:

```python
fake = make_observation(
    record_ids=(rec.id,),
    extraction_method="measurement:dsc",          # <- the only change
    content={"property": "melting_point", "value": 1811.0, "unit": "K"},
    confidence=1.0, extracted_at="2026-01-01T00:00:00Z")

class_of(obs.extraction_method)     # 'asserted'
class_of(fake.extraction_method)    # 'measured'
fake.id == obs.id                   # False
```

Ungrounded evidence does not enter, and the refusal says why:

```python
orphan = make_observation(record_ids=("no-such-record",), ...)
[e.code for e in admit_observation(pool, orphan)]   # ['UNKNOWN_RECORD']

class_of("vibes")
# EvidenceClassError: extraction_method 'vibes' declares no known
# evidence class; refusing to guess
```

## What is in the box

| package | what it does |
|---|---|
| `evidence` | the pool, the admission gate, content-addressed identity, the four classes, quarantine, trust graph |
| `scout` | acquisition pipeline — adapters, extraction, content gates |
| `retrieval` | query and context assembly over the pool |
| `materials` | experiment design and active learning — candidates, utility, ranking, selection, surrogates, counterfactuals, information value |
| `experiment` | session and policy layer driving an acquisition loop |
| `operations` | the second ledger — an append-only trace of what the *process* did |

`materials` is where this stops being a data structure and becomes a
scientific tool: a full candidate-selection and experiment-design suite
in which every value in the loop knows where it came from.

## Three design rules worth knowing before you use it

**Fail-closed never means silent loss.** Rejected candidates go to
`evidence.quarantine` with the ids of the checks they failed — never
dropped. The rejection rate per check is a measurement you can read.
If a gate is rejecting everything, that is visible rather than looking
like a clean run.

**Two ledgers, because one cannot do both jobs.** Evidence identity is
`f(content)`: order-invariant, and a repeat is a no-op. Operation
identity is `f(occasion)`: order *is* content, and a repeat is a second
event. Those rules contradict — no single object satisfies both — so
`operations.trace` is deliberately separate, with its own identity
scheme and no import of `evidence.identity`. It records occurrences; it
does not claim to say when two occurrences are "the same operation",
because that turned out to be underdetermined without knowing what you
are asking for.

**A vacuous pass is a failure.** A gate nothing ever reaches has not
been verified, and the library treats an unreached check as a silence
rather than a success. If you extend it, keep that: a check whose
inputs cannot span its branches tests nothing about the branch.

## What this does *not* claim

It is not a database, a workflow engine, or a lineage tracker bolted
onto one. It is an in-memory, append-only store with a strict door.
Persistence, distribution and scheduling are deliberately yours.

It does not tell you whether your data is *true*. It tells you what
kind of thing each value is, where it came from, and refuses to let you
lose that. That is an identity, not a warrant.

## Requirements

Python 3.10+. Nothing else.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.

Developed at Notation Systems Inc. as part of a larger provenance-bearing
corpus system, and extracted here because the evidence model is useful
on its own.

## Contributing

Issues and pull requests welcome. The test suite is the specification —
if you change behaviour, the test that pinned it should change with it,
and in the same commit.

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```
