# Two invariant sets, reconciled

**Verdict: the numbered set names things the YAML doesn't.** Not
superseded, not a subset — containment fails in both directions.

## The question

`architecture/invariants.yaml` was treated as "STE's invariant set" — by
a sibling's request, and by this repository's own answer to it. Both were
wrong the same way.

| set | covers | count |
|---|---|---|
| `architecture/invariants.yaml` (+ `evidence_class`, `transformer_contract`) | the **epistemic** layer: evidence classes, provenance, admission, doctrine, execution | 26 |
| **I1–I10**, in prose | the **canonical-state / projection** core: identity, edges, determinism, the extrinsic boundary | 10 claimed |

They are two objects covering two layers. Citing the first as "STE's
invariants" loses the second entirely.

## What was recoverable, measured from citations in this tree

Re-derived here rather than adopted from the sibling's reconstruction —
which read the same documents by the same method, so agreement between
them is **not** independence. Recorded as agreement, nothing more.

| | recovery | rule recovered | YAML counterpart |
|---|---|---|---|
| **I5** | fully — 8 citations, stated verbatim in `core/canonical/state.py` | a field's identity is its key, never its value | none |
| **I6/I7** | fully for the rule, partially for the split | same (version, compiler, config) ⇒ byte-equivalent projection | none |
| **I4** | partially — 3 citations, all on edges | relationships are stated, never inferred | none |
| **I8** | partially — 3 citations | extrinsic representation state never enters canonical state | none |
| **I3** | partially — 2 citations | inference never produces canonical truth | **the one bridge** |
| **I1, I2** | **unrecoverable** — cited only inside the range `I1–I8`, whose referent is a brief not in this repository at any path | — | — |
| **I9, I10** | **no referent** — cited nowhere: not a document, not a test, not a comment | — | — |

The two numbers are cited together everywhere I6 and I7 appear, so
*which half is which* is not recoverable. The rule is; the split isn't.

**The one bridge:** I3's content — nothing writes back into canonical
state except through validation — is carried by the `control_loop`
return edge in `invariants.yaml`, which names canonical state explicitly
and is enforced and locked. That edge lives in the `control_loop` block,
not the `invariants:` list, so it is not one of the 26. Recorded in both
directions so neither file reads as complete without the other.

## The cardinality: retracted, not replaced

The measurement was re-run here rather than taken on trust, and it went
further than expected: **there is no numbered invariant list anywhere in
this repository** — not a table, not a heading, not an enumeration.

Two candidate lists were checked and rejected:

- the anti-pattern table in the same document that carries the "10"
  sentence has **twelve** rows and is about anti-patterns;
- **no Phase 12 document enumerating invariants exists.**

So "Every one of the 10 invariants re-verified in Phase 12" is one
sentence with nothing behind it. **Retracted as unsupported** — not
corrected to eight, because the range is a single citation to an absent
referent and eight is not established either. Swapping one unsupported
number for another would look like a fix.

What *is* established: six numbered invariants are constrained by
citations here, five of them well enough to state as rules. **That is a
floor, not a total.**

A test re-runs the no-list measurement, so if an enumeration is ever
added the retraction fails rather than going stale.

## Registered — under descriptive ids, with the numbering as provenance

Five entries now live in `architecture/canonical_state_invariants.yaml`.
The brief's numbering is recorded as `numbered_as:` and **not adopted as
the id**: this repository can verify what its own citations constrain,
not what the brief said. A test enforces that no id starts with `I`.

I1, I2, I9 and I10 are **not** registered. A rule that cannot be stated
cannot be declared; they sit under `unrecovered:` so the gap is visible
rather than inferred from absence.

## The defect this surfaced

Of I3 through I8, **only I5 was ever cited by a test.** I3, I6, I7 and I8
appeared in *implementation* docstrings and nowhere else; I4 in prose
only.

Enforcement was real throughout — `test_edge_add_rejected_when_schema_declares_no_edge_types`,
`test_same_version_produces_identical_morpho_ir`,
`test_threejs_backend_cannot_become_source_of_truth` and the rest all do
what the invariants say. What was missing was the machine-checkable link
from a *named test* to the invariant.

That is the sibling's own recorded defect — *an enforcement claim naming
a file that says nothing about it* — arriving here **by the opposite
route**: not a claim without enforcement, but enforcement without a
claim.

The enforcing tests now cite the ids, each added only after reading the
test and confirming it enforces what it is being credited with. The
register's `evidence_cites_id` bar is met by evidence rather than by
lowering it, and all five register `enforced`.

## What this does not settle

The brief. It is not in this repository at any path and is not vendored,
so I1 and I2 stay unrecoverable at any effort. A newer submodule pin on
the sibling's side would surface `architecture/invariants.yaml` and
would recover **none** of the numbered invariants — two different sets,
and moving the pin settles only the visibility question.
