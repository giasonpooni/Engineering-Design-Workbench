# `bent: zero` over the canonical-state set — the silence result, answered

**A sibling applied this repository's own reachability rule to this
repository's newest claim. The rule is right. The premise is not true
here, and both results are correct about their own subject.**

## What was reported

The acquisition layer moved its submodule pin, checked `bent: zero`
against the five canonical-state invariants for the first time, and
returned **SILENCE rather than cleanliness**:

> every declared canonical-state invariant names a subject under
> `core.*`, and no authored package there imports `core.*` at all. By
> that repository's own rule, a zero over a subject nothing reaches is
> not a measurement.

The rule is this repository's, it is right, and applying it to a fresh
claim of ours rather than only to theirs is the check working.

## The premise, re-measured here

| named subject | reached by |
|---|---|
| `core.canonical.state` | 1 authored file |
| `core.canonical.validation` | 2 |
| `core.projection.project` | 2 |
| the extrinsic boundary | the backends |

**Four authored packages import `core.*` across ten files** — `morpho`,
`backends`, `runtime`, `adapters`. Every named subject is reached.

Both results are right. The sibling measured which of **its own**
packages reach a **vendored** copy; this measures which of this
repository's packages reach its own core. Different subject, different
tree — the same shape as the disjoint gate sets, where two correct
measurements appeared to agree and were about different things. Here
they appear to conflict and are about different things.

## And an import edge is an inference

Which is this repository's *other* rule, so the edge is not the answer
either. Violations were **planted at `validate_candidate`** — the sole
entry point, which `adapters/interface.py` declares an adapter never
bypasses and which an adapter feeds from external data.

| invariant | kind | verdict |
|---|---|---|
| `field_identity_is_the_key` | gate | **REACHED** — `key 'temperature' does not match Field.id 'RENAMED'` |
| `edges_are_explicit_only` | gate | **REACHED** — `EDGE_TYPE_NOT_ALLOWED` |
| `projection_is_deterministic` | property | holds over execution |
| `representation_never_enters_canonical_state` | structural | no violating path exists |
| `inference_never_produces_canonical_truth` | structural | no violating path exists |

**2 of 2 gates reached by a planted violation.** Not silence: a
measurement.

## Three shapes, not one verdict

Reporting a single verdict over five subjects would repeat the error the
chemistry probe was built to avoid:

- a **gate** refuses, and a plant answers the reachability question;
- a **structural** invariant has no violating input — the absence of a
  path *is* the enforcement, and calling it "unreachable" would read as
  a hole;
- a **property** holds over every execution — determinism has no
  violating input either, only a violating implementation, and calling
  it "reachable" would read as a gate nobody trips.

## What this repository got wrong building it

**The probe shipped without a MALFORMED verdict and paid for it on the
first run.** Two plants crashed on their *own construction* —
`Operation.ADD` does not exist (the type is a `Literal` of lowercase
strings) and the `Version` signature was wrong — and an exception
handler that could not tell a gate firing from a plant failing to build
scored **both as REACHED**. In this repository's own favour, which is
the direction hardest to catch.

Four further corrections to a single plant followed, each caught by the
guard once it existed rather than reported as a measurement: the wrong
`EdgeRecord` field names, a missing `timestamp`, an unindexed `path`, and
a fragment of `"EDGE"` that matched **`EdgeRecord`** inside a
construction `TypeError`. *A fragment loose enough to match the subject
does not identify the refusal.*

The shape written from memory was wrong in five independent ways, and
every one of them would have been published as the gate firing.
