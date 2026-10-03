# Chemistry gate reachability — per code, and what the number means

**20 refusal codes. 20 LIVE. 0 REACHABLE. No rejection rate is
reportable.**

## Why per-code

A probe reporting "clean" across a gate set is a handful of measurements
and a larger number of **silences**, presented as one number. The
acquisition layer measured 2 of 15 admission codes REACHABLE — the other
13 are not clean, they are unmeasured, and a zero rate says nothing
about any of them.

The earlier probe here reported "0/3 gates reached" over three gates
picked by hand. This one enumerates every refusal in the vertical.

## Two questions, kept apart

The earlier probe ran one and reported it as though it were the other.

| | asks | why it comes first |
|---|---|---|
| **LIVE** | call the gate directly with a violating payload — does it refuse? | reachability analysis over a gate that does not refuse is analysis of nothing |
| **REACHABLE** | plant the same violation at an **entry path** — does it arrive? | this is the question a rejection rate depends on |

A gate can be LIVE and UNREACHABLE. That is not a contradiction and not
a defect — it is the honest state of a vertical whose gates have no
callers yet. What *would* be a defect is reporting the rate anyway.

## Result

Two measurements, taken before and after the gates were wired to the
acquisition path. Everything below the table is the *first* one and is
kept verbatim: it is what the verdict rested on, and rewriting it would
leave the second number with nothing behind it.

| | before wiring | after wiring |
|---|---|---|
| refusal codes enumerated | **20** | **20** |
| LIVE (gate refuses a violating payload) | **20** | **20** |
| DEAD | 0 | 0 |
| REACHABLE through a real ingest | **0** | **15** |
| not expressible as a single document | — | **5** |
| exercised by real acquisition | **0** | **15** |
| rejection rate over what arrived | *no denominator* | **15/15 = 100%** |

Per invariant, after wiring: `quantity_is_typed` 5,
`no_point_identity_for_distributions` 3, `computed_fully_specified` 3,
`no_context_free_property` 2, `applicability_domain_declared` 2.

**Nothing about the gates changed.** They were correct and tested
before, and they refused every payload put to them directly — that is
what LIVE 20/20 always said. What was missing was **position**:
`structures/ingest.py` supplies them to `scout.pipeline.run_scout` as
content gates, and one document now carries fifteen violations to them.
A gate nothing reaches cannot refuse anything, and a rejection rate over
it reads 0% and is evidence about nothing.

The five that remain are **not expressible as a single document**, and
that is recorded rather than counted as unreached: they are
substance-identity refusals, and a merge conflict needs two identities
while a policy refusal needs a `SubstanceIdentity` constructed. No
document payload expresses either.

Verdict vocabulary is adopted from the acquisition layer's
`admission_reachability.yaml` rather than reinvented, so the two
registers read side by side instead of in two private vocabularies.

## An UNREACHABLE verdict needs a path that terminates

Not an absence of anyone finding one. The acquisition layer's **Phase 27
correction** is the case: a stage claimed unreachable turned out
REACHABLE via two real bindings on a zero-length response body — and the
error ran *in the direction that made the metric look meaningful*.

So the verdict here rests on two things, not one:

1. **The traced stop.** No module under `scout/` imports `structures/`
   at all, so no document `run_scout` admits can reach these gates. The
   path terminates at the import graph, and the graph is **re-measured
   on every run** rather than remembered from the phase that checked it.
   (Only `transformer/` imports `structures/` — not an acquisition path.)

   **This trace is no longer the verdict, and the correction is worth
   more than the result it produced.** The wiring runs the *other*
   direction: the vertical calls acquisition and hands it the gate
   (`structures.ingest.ingest_documents → run_scout(content_gates=…)`).
   The edge the trace looked for still does not exist, and the path now
   does — so the trace was measuring a **direction**, not a path, and it
   would today print `STRUCTURALLY_UNREACHABLE` with full confidence and
   be wrong. It is retained in the probe as a note about direction and
   demoted from evidence. An import edge is one way to be reachable, not
   the definition of it.
2. **The stop, executed.** An import edge is an *inference*. So a
   document carrying a bare scalar — no unit, method, conditions or
   uncertainty posture — and a polymer identified by a structure string
   goes through `run_scout`, entering at the **adapter**, the door a live
   document uses. Result: **1 observation admitted, 0 chemistry
   refusals.** The gates were not consulted. That is the termination
   measured rather than argued.

## Two corrections, both found by running

**A malformed plant.** The `DISTRIBUTION_FIELDS_MISSING` plant passed an
empty field mapping and tripped a *different* refusal one line earlier —
so it measured the plant, not the gate. The guard has two refusals and
the enumeration had one. `STRUCTURE_STRING_ONLY` was **added**, not the
plant quietly re-aimed: a malformed plant is a finding about the
enumeration.

**A vacuous confirmation.** The executed plant first used `key: value`
lines, which the shipped extractor does not read. It produced **zero
findings, zero refusals**, and the probe reported *"termination
confirmed"* — nothing had traversed the path. That is the same shape as
the Phase 27 error the confirmation exists to avoid. The probe now
refuses to call zero findings a termination.

## The mutation round that mattered

Three of seven mutants survived the first battery, all the same class:
**a check whose inputs are coincidentally uniform tests nothing about
the selection.**

- Every one of the 20 gates is LIVE, so the classifier's `DEAD` arm never
  executes against production inputs — deleting it changed nothing
  observable.
- No plant is malformed, so the `MALFORMED` arms never execute either.
- And the vacuous-pass test **recomputed the rule inside itself** instead
  of calling it, so it passed whatever the code did. A test that
  reimplements its subject tests only its own copy.

Fixed by extracting `classify_liveness` and `termination_verdict` as
pure functions and driving them over *constructed* inputs covering every
branch — the same move as planting two siblings in different currency
states. **9/9 mutants killed by their named test.**

## What this does not claim

That the gates are wrong, or that the vertical is unfinished in some way
it does not admit. The gates are live and correct; they have no caller on
any entry path yet.

The claim is narrower and harder: **no rejection rate measured today is
evidence about anything**, and a probe that reported one would be
manufacturing a measurement out of an absence.

## What would change it — and what it would *not*

Wiring the chemistry gates onto the acquisition path — an extractor that
emits property observations through `assert_property_context` — and then
re-running this probe. Codes that go REACHABLE become measurable; the
rest stay silent and stay labelled. The register is regenerated, never
edited.

**A sibling measured something that looks like the same fact and is
not.** Before acquiring GPC data the acquisition layer asked whether "no
content gate runs at ingest" was the state that data should arrive into,
and answered: not the question that decides anything — five replicates
pass every gate that exists, so wiring them would have changed nothing
either way. Its result is **pointed at, not transcribed**; the derived
register names it and pins it to a commit.

Read quickly, that is this result from the other end: it says wiring the
gates changes nothing, this says nothing reaches them. Two independent
measurements agreeing on a structural claim would be worth more than
either.

### They are not independent, and they are not the same gates

Checked before citing, because the last time convergence was treated as
confirmation without checking, **both halves agreed on the wrong
reason**.

The acquisition layer vendors this repository as a submodule, **pinned
at `3e5bea9`**. That commit is **63 behind this branch's head**, and:

| | at `3e5bea9` | first appears in |
|---|---|---|
| `structures/` — the 20 gates measured here | **absent** | `1637bd8` |
| `architecture/` | **absent** | `1637bd8` |

Its readiness test imports `science.table`, `materials.analysis` and
`evidence.types` — its own table gate, and this repository's admission
path *as it stood 63 commits ago*. **Not one of the twenty codes
measured here existed in the tree it measured.**

So "every gate that exists" is true of the gate set it had, and that set
is **disjoint from** the one measured here. The two results agree in
direction and are about different things. Citing one as corroboration of
the other would be citing a measurement that could not have touched the
gates in question — convergence-is-not-evidence arriving in the
direction that would have been flattering, which is the direction it is
hardest to catch.

**This result therefore stands alone.** `0 of 20 REACHABLE` is
established here, by the trace and the executed plant above, and by
nothing else.

### What the sibling's finding does change

Not the verdict — the sentence a reader would otherwise infer from this
section. Wiring the gates makes the **rate measurable in this
repository**. It is not what unblocks polymer science: the sibling
measured that the pairing is destroyed in the analysis projection, on
its side of the boundary and a separate problem from anything here.
Without that distinction this document could be cited as "the gates are
the blocker" — local scope quietly promoted into a project claim.

---

## The wiring: what was actually built

Three files, and the shape of the change matters more than its size.

**`scout/pipeline.py` gained an extension *point*, not a dependency.**
`run_scout(..., content_gates=(), quarantine=None)` — both defaulting to
the prior behaviour exactly. Importing the chemistry gates into the
generic acquisition path would have made the core depend on one domain;
`core_schema_closed` in spirit if not in letter, since verticals extend
and never widen the core. So the coupling lives at the vertical's call
site, where the vertical owns it.

**`structures/ingest.py` is that call site.** It routes on what the
payload *declares* — `property`, `distribution_kind`, `method_block` —
fail-closed over the kinds it recognises, and silent on everything else.
A candidate declaring none of them is not a chemistry claim and passes
untouched: a gate that refused what it did not recognise would make one
vertical a filter on the whole corpus.

**`scout/property_extraction.py` is deliberately permissive.** It parses
a property line and emits it; it does not check that the property
carries a method or the quantity a unit. Those are the *gates'* job, and
they run in the pipeline where a refusal is visible and quarantinable.
An extractor that declined to emit a bad candidate would refuse it
**invisibly** — and an invisible refusal cannot be told from a source
that never made the claim, which is exactly the difference between a
measured rejection rate and no measurement.

### The order was the constraint

Wiring had to come **before** any real dataset. A first measurement over
unreached gates produces twenty silences that read as cleanliness, and a
first number carries an authority a probe result does not. The contrast
is in the probe's own output: the same document that yields fifteen
refusals through `ingest_documents` is admitted **whole** by a bare
`run_scout`. The ungated path has not changed and still never refuses a
chemistry claim. What changed is that a caller can now wire the gate.

## The alias problem, in its fourth position

The five ids the gate refuses under were **not this file's names to
choose**, and three of them were written as new ones anyway:

| written here first | already declared in the acquisition layer |
|---|---|
| `distribution_has_no_point_identity` | `no_point_identity_for_distributions` |
| `computed_method_fully_specified` | `computed_fully_specified` |
| `prediction_within_declared_domain` | `applicability_domain_declared` |

Same rule, second name — shipped one commit after building the register
whose entire purpose is to detect exactly this. It was caught by a lock
requiring every gate id to resolve against a declared invariant, which
failed on all five: **none** of them were in this repository's
`architecture/invariants.yaml` at all. The per-invariant rejection rate
was keyed on strings no registry carried.

The measurement of the cost is exact. The derived register held **58
rows** before and holds **58 after**: all six STE declarations landed on
*existing* rows (STE's claim count went 33 → 39). Under the renamed ids
it would have been **61** — three more rules that do not exist, reading
as three unimplemented ones over there plus three unrelated ones here.

**A rule gets one id across the project, and the party that implements
it second does not get to rename it by implementing it.** The earlier
declaration keeps the name.

### Not a contest

`scope: this_repository` on the five STE rows. The acquisition layer
declares two as `partially_enforced` ("not wired into any admission
path") and three as `absent` ("no chemistry representation exists in
this repository at all"); this repository declares all five `enforced`.
Those are statements about two repositories, not a disagreement about a
rule, and the register records `contested: 0` across all five.

## Two defects found in the mutation battery itself

Both made it report a confident verdict for work it had not done, and
neither was visible in its output.

**A mutant that does not parse.** It can only ever be "killed" by an
import error — a fact about the edit, not about the named test. The
malformed-plant problem, one level up: in the battery that verifies the
probe rather than in the probe. The guard caught a *second* instance on
its first run.

**A mutant is not identified by `(mtime, size)`.** Two mutations of
`scout/pipeline.py` — "the refusal loses its invariant id" and "the
refusal is filed under the wrong stage" — change the file by **exactly
+8 bytes each**. Written in the same second, they are indistinguishable
to CPython's `.pyc` validity check, so the second run executed the
**first one's bytecode** and printed its PASS under the second one's
label. The battery reported a stable `SURVIVED` across repeated runs for
a mutant that a direct run kills in 0.07 seconds.

Byte-identity is what made it dangerous, again — the same shape as *a
mirror is not a source*, where two files are the same bytes and only
provenance separates them. The fix is both halves: no bytecode written
during a battery run, **and** the cache entry purged before it —
suppressing the write does not invalidate an entry an ordinary test run
already left on disk.

Both guards were then applied to `scripts/mutate_register_checks.py`
**without waiting for them to fire there**. It mutates the same handful
of files repeatedly and is exposed to the identical collision. A defect
found in one instrument is a defect in the other until it is checked —
an absence of anyone finding one is not a verdict, which is the rule
this whole document is built on.

Batteries: **27/27** and **23/23**, each mutant killed by its named test.

## The three-gate probe, and what it hid

`scripts/ingest_reachability_probe.py` predates all of this. It carried
**0 of 3 gates proven reached** for several phases and was right to. Once
the gates were wired it kept reporting UNREACHED — for two reasons that
had nothing to do with reachability, and both ran in the direction that
made the probe look vindicated.

**Its plants could not isolate the gate they named.** They used `FACT:`
lines, read by the flat `DeterministicExtractor`. But
`assert_property_context` requires `conditions` to be a **non-empty
mapping**, which a flat extractor cannot express — so *every* plant was
refused by the context gate first, and no plant could ever reach the
quantity gate behind it. `quantity_is_typed UNREACHED` was a fact about
the plant's format.

**It could not tell "nothing refused it" from "something else refused it
one gate earlier."** A payload stopped one gate early says *nothing* about
the gate being probed. That is a MALFORMED plant, not an unreached gate,
and an UNREACHED verdict has to mean the payload **arrived** and nothing
refused it.

Both survived because the probe **had no test at all**. It has one now,
and the first version of that test was itself wrong in the familiar way:
it asserted what the *gate* did with a misaimed payload and never touched
the classification that reads the result. A mutant deleting the malformed
branch survived it. The classifier was extracted into a named predicate
and driven over all four verdicts with constructed inputs — **the fourth
time in this project that a check has been found testing its ingredients
rather than itself.**

Result: **0/3 → 2/3 reached**, with the third still MALFORMED and still
named (no document payload *can* produce an undeclared extraction
method — the extractor declares its own as a class constant).

## What is still not claimed

A **100% rejection rate is not a statement about real sources.** Every
candidate counted here was planted to violate a gate, so the rate
measures that the plants arrived — not that the world is dirty. The
claim is exactly this wide and no wider: fifteen of twenty refusals are
now reachable through a real ingest, so a rate over real documents would
be *evidence* for those fifteen.

It is not one yet. That needs a dataset, and the ordering constraint this
whole phase was built around is now satisfied: the gates are wired
**before** it lands, so the first real number will be a measurement
rather than twenty silences reading as clean.

---

## The sibling was working the same question, and what that is worth

The acquisition layer landed two artifacts on this exact subject while
this phase ran: `architecture/chemistry_rule_ownership.yaml` and
`architecture/chemistry_gate_wiring.yaml`. Both were read after the
wiring was built. Three separate claims come out of them and they are
**not worth the same**, so they are separated here rather than summed
into a convergence.

**Not independent — its ownership map was derived from this tree.** The
sibling measured "the only callers of these guards outside `structures/`
and `tests/` are the probe itself and its mutation harness" by reading
this repository at pin `5e146d5`. That is a correct reading of my code,
not a second measurement of it. Citing it as corroboration of my own
`0 of 20` would be citing my own tree back to myself — the
convergence-is-not-evidence failure this project has already caught once,
arriving again in the flattering direction.

**Independent, and it settles the alias question.** The sibling declared
all six ids in *its* registry before it had read this tree, and its
ownership map binds each to the implementation here:
`no_point_identity_for_distributions` → `assert_distribution_identity`,
`computed_fully_specified` → `assert_method_block`,
`applicability_domain_declared` → `assert_applicability`,
`identity_policy_declared` → `assert_identity_policy`. Those are exactly
the functions my gate calls. The renames I nearly shipped would have
broken a mapping a second party had already written down. **The earlier
declaration keeping the name is not a stylistic preference; it is what
keeps a cross-repo ownership map resolvable.**

**Independent, and it named the blocking decision before seeing the
answer.** The sibling recorded what wiring would require: *"a decision
about what a chemistry refusal means for a non-chemistry observation —
the four guards assume a chemistry payload shape, and applying them to
every admitted observation would be the `gate applied to content it does
not govern` class this pair has already filed twice."*

That is the hazard, stated precisely, by a party that had not seen the
design. The design answers it: the gate **routes on what the payload
declares** — `property`, `distribution_kind`, `method_block` — and a
candidate declaring none of them is not a chemistry claim and passes
untouched. `test_a_non_chemistry_candidate_passes_untouched` and
`test_an_unrecognised_document_still_ingests_through_the_gated_path` are
that decision made executable. This is the one place the two lines of
work genuinely meet: a named risk from one side, answered structurally
from the other.

### One citation of mine is now stale, and it is mine to correct

The sibling's ownership artifact cites `reachable_from_any_entry: 0`
from this repository's probe, correctly, at the pin it read. **It has
moved to 15.** The sibling was careful to say it *"does not claim STE's
number moved"* — it did not, and the number moved anyway, one commit
later, for a reason the sibling correctly identified as this
repository's to act on: *"adding that call site is inside the
unmodifiable submodule and is STE's, not DAQ's."*

The call site was added. It is `structures/ingest.py`, and it is **not**
inside the guards' module — which is also the sibling's own correction
of an earlier recorded obstacle, reached from the other side: where a
guard *lives* is not where its caller has to live.
