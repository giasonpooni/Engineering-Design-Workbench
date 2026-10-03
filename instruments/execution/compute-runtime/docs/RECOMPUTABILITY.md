# Measuring this apparatus's own claim

`architecture/apparatus.yaml` said this repository supplies the second
half of *provenance-bearing computational corpora* because

> a computed result carries what it was computed from **and can be
> recomputed by the party reading it**

That is a claim about the records, so it is measurable — and a claim a
repository makes **about itself** is the one no other party can check
for it.

## The verdict

**True of one path, weaker on the other, and the sentence did not
distinguish them.**

| record | grade | what a reader gets |
|---|---|---|
| `ExecutionSpecification` | **SELF_CONTAINED** | the **program itself** — a reader holding the record holds everything the computation consumed |
| `DerivedValue` | **NAMES_ITS_METHOD** | `method` as a **string** — what was done, not a definition |

The proof-bearing path can be proved *because* it is self-contained: a
proof about a program nobody can exhibit proves nothing a reader can
check. The generic derivation path names its method, which is genuinely
provenance-bearing — the method is part of the record's identity, so two
derivations by different methods are different facts and cannot be
confused downstream — but a reader can only recompute if it **already
possesses** that method.

**Provenance-bearing is not the same as self-sufficient.** Both paths are
the first; only one is the second. The declaration now says only the
first, and the removed clause is pinned by a test so it cannot drift
back.

## What would close it, and why it is not closed

Carrying a **digest of the method's definition**, as the execution path
carries the program — so a reader could at least check that the method it
holds is the method that ran.

Not done. It changes what a `DerivedValue` *is*, which is a core-schema
change under `bend_protocol`, and it is a **decision rather than a
measurement**. Recorded as one, so nobody closes it thinking it a chore.

## The probe attempts the recomputation; it does not describe it

And getting that right took three passes, each of which is the same
lesson from a different angle.

**First it rebuilt the record from the live object's own attributes** and
checked the identity matched. Of course it did. A mutant replacing the
comparison with `True` survived — the step proved only that an object
equals itself.

**Then the negative half was added** — remove the program, and the
identity must change — which is what makes `SELF_CONTAINED` rest on a
field that is *load-bearing* rather than merely present.

**But the rebuild half was still tautological**, and the proof of that is
exact: the `True` mutant was **equivalent**. Handing a constructor the
very attributes it was built from cannot fail under any input. The round
trip now crosses an **encoding boundary** — hex out, bytes back — because
that is what a reader actually crosses when a record reaches it as bytes
in a document.

**And the test could not tell a mechanism from a constant** until the
demonstration was given a *failing* input. Asserting only that it
succeeds is unfalsifiable: three mutants that hardcoded `True` walked
past it. An empty program is the discriminating case — the record still
rebuilds, but removing the program no longer changes the identity, so
nothing in the record carries the computation.

## What this does not claim

That a `SELF_CONTAINED` record is **correct**. It says a reader can run
the computation again, not that the computation was the right one to run.
An identity, not a warrant.
