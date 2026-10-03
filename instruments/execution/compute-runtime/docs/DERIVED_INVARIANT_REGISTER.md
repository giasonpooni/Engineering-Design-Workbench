# The Derived Invariant Register

Core: **core@1.0.0**, now *declared* in `architecture/core.yaml`.
Register derived from three bound repositories at named commits — and,
as of this phase, at commits verified against their **remotes**.

## 1. The core version is a declaration, not an inference

The previous fix set STE's core version by reading `pyproject.toml` and
added a test asserting the two agreed. The number (1.0.0) was right and
the reasoning was wrong.

**A package version moves on any release; a core-schema version moves
only under `bend_protocol`.** Coupling them means a routine release
renumbers the core with no invariant changing meaning — and every
`Bent: zero` this repository has claimed is then asserted against a
referent that can move without anyone bending anything.

`architecture/core.yaml` now declares it, with the coupling explicitly
denied (`derived_from_packaging: false`, `moves_only_under:
bend_protocol`, `moves_on_release: false`). `conformance.core_version()`
reads the declaration and **refuses** one that admits to being derived
from packaging. `invariants.yaml` no longer restates the version; it
points at the declaration. One referent, one place.

### What decoupling cost, and where it is paid

Found by mutation: setting the declaration to `0.1` left the
declaration test **green**. That test compares the declaration against
itself, and a self-consistent declaration is unfalsifiable on its own.
Nothing external pins the value any more — that is the *point*, and it
is also a real loss that has to be paid somewhere rather than pretended
away.

It is paid by the **closure**. Six architecture artifacts bind
`extends: core@<v>`; the gate requires every one to match. A version
that moves stops the whole repository conforming at once. That is
`bend_protocol`'s teeth: the version cannot move quietly, because moving
it invalidates every declared vertical and probe *by construction*
rather than by anyone remembering to re-run them. Locked by
`test_moving_the_declared_core_version_breaks_every_artifact_that_binds_it`.

---

## 2. Two probes, 51 and 73 lines — and what it says about `Bent: zero`

| key | STE | DAQ |
|---|---|---|
| `observation_properties` | 4 entries | **identical** 4 entries |
| `computation_properties` | **key absent** | `[recursive_computation]` |

The two probes agreed exactly on what an *observation* can be, and
differed on whether a **computation** property was in scope at all.

Every property in STE's probe was a property of an observation. The
probe therefore could not falsify anything about computation — and
DAQ's probe, which has the key, found exactly such a case and returned
its first FAIL.

**The consequence for this repository's own record, stated plainly:**
every `Bent: zero` STE has claimed was measured against a probe
structurally unable to find the case DAQ closed. That does not make the
claim false — the evaluation now added returns no bend — but its
**evidence was narrower than the claim implied**, which is the same
shape as trusting an anchor for the property that made it blind.

STE's probe now carries the key, as a **separate key** rather than a
fifth entry in the observation list: a computation property is not one
any source's observations can have, and appending it would be the
category error DAQ's probe deliberately avoided.

**Verdict: `bend: none`, on structural grounds.** An N-iteration
estimator runs to completion *inside one* `ExecutionSpecification`, so
it is one computation identity and one trace occurrence here; the
iteration count is not visible to any identity STE mints and cannot
inflate one. Recorded beside it, because it qualifies the verdict rather
than supporting it: STE **cannot** evaluate the evidence-lineage half —
whether a chain of derivations is bounded and its depth recorded. That
is `generation_depth_bounded`, owned by DAQ. A repository that owns
execution identity cannot falsify a lineage-depth invariant by
inspecting its own ledgers, because lineage depth is not a quantity its
ledgers carry.

---

## 3. Three parties, one with no invariant source

| party | binding mode | invariants | binds via | commit |
|---|---|---|---|---|
| STE | `invariant_registry` | 26 | 6 artifacts | local |
| DAQ | `invariant_registry` | 43 | 30 artifacts | `708f6d6` |
| SCL | **`extends_only`** | **0** | 5 artifacts | `966b31f` |

SCL holding neither `invariants.yaml` nor a probe is a **binding mode**,
not an absence to route around. A party can bind the core by declaring
`extends: core@<v>` in its own artifacts while declaring no invariants
of its own.

The distinction this pins: *a party contributing zero records* and *a
party the derivation failed to read* produce the same number. Only one
of them is a fact. So `extends_only` is recorded explicitly, with the
binding files **named** — the register can be read to see that SCL
declares none, rather than leaving a reader to infer it from a count.

And the case it must not absorb: a repository with **neither**
invariants nor `extends` is not "bound with no source" — nothing
establishes it is bound at all, and counting it as a contributor of zero
would be the register asserting a binding on the party's behalf. That
**fails**.

---

## 4. Recording the commits — and the failure that found

The instruction was to record the commits derived from, so a later
derivation can tell current from stale. Doing it exposed that the
previous derivation had recorded the wrong side of the question.

**Measured: both sibling clones were behind their remotes** at the
moment the previous phase recorded their local HEADs as the commits it
had derived from, and reported them current. DAQ `854780d` → remote
`aa1f7eb`; SCL `482c336` → remote `3d73080`. One of them (DAQ) moved
*again* between a fetch and the next derivation minutes later.

A local commit proves authorship. Only the remote head proves the clone
is current. The derivation now asks the remote — the same posture as
DAQ's `verify_pair_landed.py`, for the same reason — and the question is
treated as **directional**, because collapsing it to equality gets one
direction wrong:

- clone does **not contain** the remote head → **stale → derivation fails**
- clone **ahead** of remote → `local_ahead_of_remote`, recorded (the
  normal case for the deriving repository, which emits the register from
  its working tree and commits it alongside the state it describes)

`check_remotes=False` is permitted and is **recorded** in the artifact
(`currency_established_against_remotes: false`). What must not exist is
a register that reads the same whether or not the question was asked.

### The asymmetry is real, not an artifact of the check

A symmetric "are we current" reports drift on the party doing the work
— STE's clone diverges the instant it commits the very thing being
derived. The first fix gave every party the same lenient comparison,
which let STE through **for the wrong reason** and would have excused a
*sibling* sitting in the same position.

The asymmetry is a fact about authority, not a tolerance:

- **A party's own HEAD is authoritative for itself.** It cannot be
  stale against itself. The deriving party is exempt **by
  construction** — it carries `authoritative_for_itself`, a state
  reachable only by *being* the deriving party and never by passing a
  comparison.
- **Stale-ability runs one way**: toward siblings. The real question is
  "am I current with respect to what I *derived from*", and that has
  one answer per sibling.

So currency is recorded per sibling and **never collapsed**. A
derivation is only ever as current as its **worst sibling**, and a
single boolean throws away both halves of that: which party is the
constraint, and how far behind it is. The register names it:
`as_current_as_its_worst_sibling: "DAQ at cf35a20bb585 (in_sync)"`.

Mutation found both halves under-asserted. Routing the deriving party
through the sibling check left every assertion true, because STE
happened to be in sync at that moment. And returning `siblings[0]`
instead of the minimum was indistinguishable in production, because
both siblings were in the same state — it took two planted siblings in
*different* states, with the worse one read second, to make the
selection observable at all.

### Faithfulness and currency are different properties

Enforcing currency *inside the test suite* was a design error of mine,
and the siblings made it visible: DAQ pushed **four times** during this
phase, and each push turned STE's suite red for something nobody here
did wrong. Worse than the noise is the direction of the pressure — the
cheapest way back to green becomes weakening the staleness gate.

So the two are split:

| property | whose | when checked | on failure |
|---|---|---|---|
| **faithfulness** — the register is what derivation produces from the commits it *names* | STE's | offline, deterministic, in the suite | hard failure |
| **currency** — those commits are still the remote heads | the world's | at emission, and on demand (`--currency`) | refuse to emit / report, exit 2 |

The digest still covers the **whole** artifact, currency fields
included; only the *comparison* is narrowed, to exactly two fields
(`currency`, `remote_commit`) named in a module constant rather than
filtered ad hoc at each call site — widening that set would let real
drift hide in the gap. The currency gate's own behaviour is locked
hermetically against a local origin nobody else can push to.

### What the register actually guarantees

**Not "never stale" — "stale is detected".** The
committed register is current as of the commits it names and will read
stale the moment a sibling pushes again. That is the correct shape and
worth stating rather than leaving a reader to assume the stronger claim:
a derived register cannot make a moving sibling hold still, it can only
make the divergence *loud* instead of silent. The previous,
hand-maintained projection had the opposite property — it never failed,
and it was wrong.

---

## 5. Nine contested → zero, and why that is a result rather than a silence

The nine disagreeing rows were three different things in one bucket:

**(a) Four rows STE reported for an invariant DAQ owns**
(`generation_depth_bounded`, `no_circular_training`,
`training_admissibility_declared`, `prediction_carries_uncertainty`).
These were the defect.

The fix is **not a corrected copy** — a corrected copy is the same
artifact one correction later, and in the sibling pair this exact
artifact went *two* corrections stale with every suite green. STE now
records `owner_elsewhere: DAQ` and **no status for the owner at any
version**; the register resolves the owner's live value on every
derivation (`owner_status_resolved`). A pointer that resolves cannot go
stale; a copy always can.

The cost is real and is the property working: **STE can no longer be
derived alone.** Four of its rows have no status here, so a single-party
derivation *fails* rather than quietly producing unresolvable pointers.
That is what the copied status bought, and what giving it up costs.

**(b) Five development-process rows** whose state is genuinely
per-repository — each repository has its own authorship lineage,
doctrine and review history, so two parties holding different statuses
are *both* telling the truth. Declared `scope: this_repository`. Scope
defaults to `project`, so silence never buys the exemption.

**(c) One row where STE was stale about *itself*.**
`no_vendor_in_doctrine` read `status: process` with the note *"no
doctrine files exist in this repository"*. Five generated doctrine files
and a mechanical vendor lint have existed here since the
architecture-sync phase. The register was built to catch a claim about
someone else's state going stale, and the first thing it caught in this
file was a claim about our own. A note is not re-checked when the thing
it describes changes, and nothing was watching it. Corrected to
`enforced` with the real validator.

### The reachability proof zero demands

Zero contested is also exactly what a broken detector reports. So a
genuine same-scope disagreement is **planted** and the derivation is
required to find it, then required to stop finding it once the scope is
declared — showing the exemption is the scope declaration doing work,
not the detector having failed.

That test earned its place immediately: the first `contested`
implementation grouped *by* scope and flagged any group that disagreed,
which is a different rule wearing the same words — two claims both
scoped `this_repository` still contested. The plant found it.

The register also emits `rows_with_a_local_scope_claim`, so a reader can
see how much of the zero was reached by agreement and how much by
scoping, instead of taking the count on faith.

---

## 6. A mirror is not a source — the general rule

The same defect has now arrived **three times in three positions**:

1. the emitted register re-read by its own derivation
2. a top-level owner read as though it were a row's owner
3. a party's self-declaration read out of an artifact it merely *holds*

All three are one rule, and the third made it obvious that patching
positions was the wrong move. **Byte-identity is exactly what makes it
dangerous**: a mirror and its origin are the same bytes by design, so
nothing in the *content* can separate them. Only provenance can.

So provenance is now established **across all parties at once**, before
anything is read, and holders are found **by digest rather than by
path** — a mirror may sit anywhere, and identical bytes are the only
thing that makes two files the same artifact. Two facts decide it:

- do any other bound parties hold these exact bytes?
- does the document name a generator, and does that generator resolve
  *here*?

Generator resolution is load-bearing because it is the only test that
needs **no name resolution**. Asking "is this party the owner named in
the file" is circular here — the acquisition layer calls itself `daf`,
the compute layer addresses it as `daq`, and this derivation labels it
`DAQ`. A path either exists in a repository or it does not.

Each read then gets a different entitlement:

| read | requires |
|---|---|
| canonical invariant source | not emitted, and no other party holds these bytes |
| self-declaration (a name) | provable authorship — `joint` is **not** authorship |
| binding evidence | not authored elsewhere, and not a shared file naming a single author |

**The location conventions are gone.** Both the derivation and the
core-closure lint used to skip the `exchange/` *directory* — a location
standing in for the property. That protected exactly one path, and the
substitution is precisely what re-admitted the circular defect the
moment the rule was generalized: the emitted register did not declare
itself emitted, so 26 invariants became 77 and every row read as
contested. The artifact now says `generated_by`, and **the derivation
is a fixed point** — emitting twice produces identical bytes, which is
the proof rather than the assertion, since an artifact that fed itself
could not reach one.

### The case that separates a joint record from a mirror

Shared bytes that **name a single author** were written by exactly one
holder, and this derivation cannot say which — the author tokens are in
each party's own vocabulary, and resolving them here would be the
deriving party deciding another party's identity. Crediting the holder
would assert a binding the party never declared. So they are excluded
from **both**, and **listed** in the register
(`artifacts_set_aside_authorship_unresolved`): a limitation that costs
a party evidence should be visible to that party rather than silently
applied. Under-crediting the true author is the safe direction — a
party that really binds says so somewhere it authored alone, and all
three do.

## 7. One party, two names — how the third position was found

DAQ and SCL found that DAQ calls itself `daf` in all six of its own
artifacts while SCL addresses all eight requirement rows to `daq` — both
internally consistent, invisible to every check inside either
repository, and visible the first time anything **joined on the token**.

This derivation joins on a **third** name (`STE`/`DAQ`/`SCL`, labels
chosen here). So it records each party's self-declaration beside the
local label and marks the label as a local handle
(`label_is_a_local_handle_not_the_party_s_name`), rather than asserting
the label is the name.

**Found by running:** the first implementation reported DAQ's
`also_known_as` as *SCL's* name. SCL holds a byte-identical **mirror**
of DAQ's requirement response, which carries DAQ's self-declaration —
one party's name attributed to another, by a derivation whose entire
subject is not trusting one repository's account of another.

Mirrors are byte-identical to their origins by design, so content cannot
separate them. The **generator** can: an emitted artifact names the
script that built it, and only the origin repository holds that script.
An artifact naming no generator is hand-authored in place and counts as
origin — absent is not false.

---

## 8. Answering a sibling's standing request

The acquisition layer published a **reconstruction** of STE's invariant
set, marked `RECONSTRUCTION_NOT_DECLARATION`, with three asks and a note
that the request "stands unanswered and is recorded as unanswered
rather than as an agreement." There was a party to answer. Answered in
`architecture/exchange/ste_invariant_declaration.yaml`, authored here —
and its findings **re-measured against this tree** rather than taken on
trust, since it says itself it must never be cited as STE's statement.
Every factual claim it makes reproduced.

1. **Declare the invariant set** — already declared
   (`architecture/invariants.yaml`, 26 entries, id + rule each). But the
   request names a *different* set: `invariants.yaml` is **not** a
   renumbering of I1–I10 and must not be read as one. Mapping them
   would manufacture a correspondence no document supports.
2. **Resolve the cardinality: eight or ten** — **neither.** Measured
   independently here: I3–I8 cited individually, I1/I2 only inside one
   range, **I9 and I10 cited nowhere at all**. The range defers to a
   brief that is not in this repository at any path. So the "10
   invariants re-verified" sentence is **retracted as unsupported** —
   not corrected to eight, because eight is a single citation to an
   absent referent and would replace one unsupported number with
   another.
3. **Re-run the probe against five properties** — done, and it is the
   finding STE owed the record: every `Bent: zero` here before
   2026-08-26 quantified over four properties, all of them properties of
   an *observation*.

## 9. Decisions, not measurements

**A property of this project, not a list of stragglers.** Every
instrument here converts an assumption into a **measurement**, and none
converts a measurement into a **choice**. Probes, mutation batteries,
reachability traces, currency gates and this register all answer *what
is true*; not one of them answers *what should be done about it*.

That explains why five rows have outlived twenty phases of rigour. They
will not resolve by being measured harder — they are waiting on a
person, which is a reasonable place to wait **so long as the register
keeps saying so**. A prose note survives by inertia, which is exactly how
four of them got here. So the flag is now **derived and re-emitted on
every run** (`awaiting_a_decision`), and each flagged row must state
*which* decision or the lock fails — a flag without a question is a note
again.

**Three settled on 2026-08-27, two open.**

| row | the decision |
|---|---|
| `evidence_append_only` | the tombstone bend — **deferred, with a trigger** |
| `multi_writer_write_conflict` | the merge policy for two writers — **deferred, with a trigger** |
| `self_optimization_acceptance_criteria` | capabilities 5–9 — **settled for 6, open for 7–9** |
| `cross_vendor_validation` | **settled: standing.** Vendor-disjointness of the validator is a constraint, not a property the current topology happens to have |
| `builder_check_lineage_recorded` | **settled: the weaker form.** A shared-vendor lineage requires a review *record*; the review need not itself be cross-vendor |

### Why the weaker form, deliberately

The stronger rule makes every enforcement change a two-vendor ceremony —
which is the condition under which someone eventually adds an exception,
leaving a rule that *has* a hole and *still* costs the ceremony. **A rule
that survives beats a stricter one that gets holed.** Recorded as a
deliberate weakening rather than as the strongest form anyone could think
of, because a rule nobody follows is indistinguishable from no rule and
harder to notice. The residual — a shared-vendor review is not
independent review — is recorded, not argued away.

### A premise corrected while settling `cross_vendor_validation`

It looked already satisfied by the binding table: validator on one
vendor, proposing lineage on another. But `role_bindings.status` is
`not_instantiated_in_repository` — that is the **intended** topology, not
a live deployment. Meanwhile `builder_lineage.vendor_relationship` is
recorded as `shared`, and actually is.

Two different lineages: the runtime topology, and who authored the
enforcement code. Satisfying one says nothing about the other, and
reading a table that describes nothing as a satisfied constraint is how
an intended topology becomes a claim. So the row is `partially_enforced`,
the enforced half binds the declaration, and the unenforced half is
stated rather than implied.

### The pattern, generalized

> **A deferred decision is safe only while the condition that made it
> safe still holds, and the condition should be checked rather than
> remembered.**

A note does not close when its condition does — it survives the event in
silence, which is how four of these reached twenty phases. So a row
declaring `deferred_while:` must name a `trigger_enforced_by:`, that file
must exist, and it must actually mention the row. The last clause matters:
a trigger naming a file that says nothing about the invariant is the
enforcement-claim defect again, which this project has now met from both
directions.

The field draws a distinction worth keeping: `awaiting_decision` alone
means **undecided**; `deferred_while` means **safe under a condition**.
Only the second needs a trigger. Capabilities 7–9 are the first kind —
nothing makes them safe and nobody has chosen — and demanding a trigger
there would mean inventing a condition to satisfy a rule, which is how a
mechanism starts generating the evidence it was built to check.

Two triggers exist, and each has its **own reachability proof** — a check
designed never to fire in its shipping state is the archetype of the
shape that rots, so both plant the event and are required to catch it:

| deferral | safe while | fires when |
|---|---|---|
| tombstone bend | `EvidencePool` has no persistence layer | it grows one while the limitation still stands |
| merge policy | exactly one `VersionStore` implementation | a second appears |

### The same lesson, a fourth time

Two mutants survived the first battery on the process checks, for the
reason that has now recurred four times: **a check whose inputs are
coincidentally uniform tests nothing about the selection.** The review
record exists and the vendors *are* disjoint, so weakening either
assertion changed nothing observable. The fix has been identical every
time — extract the predicate, drive it over constructed inputs covering
both outcomes — and never adding cases to the subject and hoping one
fails. **15/15 killed** after.

**Zero contested and five awaiting are both true at once**, and
collapsing either into the other is the error this register exists to
stop. A contest is two parties disagreeing about what *is*. An open
decision is nobody having chosen what *should be*. A test asserts the
two sets stay disjoint.

### Capability 6: the criterion is provenance, not a threshold

"Identifies deficiencies" has **no subject**. Every deficiency this
project has found was surfaced by an *agent operating on the system*,
not by the system — and crediting those to the substrate is the same
category error as citing a reconstruction as a declaration.

So a finding counts only if **a committed check surfaced it without an
agent reading the code**:

| finding | surfaced by | counts |
|---|---|---|
| `nexus-pairwise` ELF divergence | `test_recipe_roundtrip_and_identity_stability` | **yes** |
| both sibling clones stale | the currency gate | **yes** |
| projection re-read as its own source | the fixed-point check | **yes** |
| three under-asserted locks | the mutation batteries | **yes** |
| the vacuous pass | a human, reading output | no |
| enforced-but-never-stated invariants | a human, grepping | no |

Four passes — a real claim, not a deferred one. Capability 5 is
evidenced by the gated optimizations. **7–9 stay unclaimed**: nothing
here optimizes its own architecture.

The partition costs this repository in the direction that matters. The
two most interesting findings of the phase that set this criterion both
fall on the **no** side. A criterion that kept the impressive findings
and excluded the dull ones would be a criterion fitted to the answer.

### The tombstone bend: deferred, with an expiry that fires

Building tombstones with no revocation-compelling source would be a
proposal wearing measurement's clothes — the discipline that stopped the
checker optimization at −6%. But the cost is **not flat**. Today
`EvidencePool` has no persistence layer and legacy records are 0, so the
bend is free. The moment records outlive a process, every stored record
predates the semantics and retrofitting becomes structural.

The window closes at a specific, nameable event — and a carried-forward
note does not close with it; it survives the event silently. **Name the
event, ask what goes red.** `tests/test_tombstone_decision_trigger.py`
fails the moment `EvidencePool` grows a persistence primitive while the
tombstone limitation is still recorded. It does not check that tombstones
exist — that would build the thing the decision deferred. It checks only
that the two facts cannot be true at once.

And because a check that never fires is an untested assertion — and this
one is designed never to fire in the state it ships in, the shape that
rots unnoticed — **the event is planted and the trigger is required to
catch it.**

## 9b. The second gap the sibling named on this side of the boundary

`chemistry_rule_ownership.yaml` said the chemistry gate call site "is
inside the unmodifiable submodule and is STE's, not DAQ's." That was
acted on and the gates are wired.

`polymer_acquisition_readiness.yaml` names the next one in the same
form: the analysis projection drops the pairing between two properties
measured on the same replicate runs, and *"recovering rho would mean
joining on Record outside the grouping — which is a consumer this
repository does not have, not a capability it lacks."*

**Verified here at this commit rather than carried across.** The sibling
read this tree at a pin that has since moved twice, so the three findings
were re-measured against these modules: the group's fields are
`{context, values, disagreement}`; the pairing is recoverable from the
pool by joining on Record; five replicates whose per-run uncertainty
differs by 1 g/mol fragment into five singleton groups.

**And one thing is sharper here than the sibling recorded it.** The
unpairing is not an absence. Values arrive ordered by content-addressed
observation id, so two properties come back as two *unrelated
permutations of the same runs* — index-pairing them succeeds and returns
**rho = +0.38 against a true −0.98**, wrong in sign, stably, with nothing
in the result to indicate it. The polymer vertical's question is rho's
sign.

`materials/replicate_join.py` is the consumer. It is additive:
`ComparisonGroup` and `_comparison_context` are untouched, so no grouping
semantics move and no core version does either. The fragmentation is
**surfaced rather than fixed** — whether a per-run uncertainty belongs in
a comparison context is a decision about scientific semantics, which puts
it in `bend_protocol` territory and on the register's
`awaiting_decision` list rather than in a patch.

Full record: `docs/REPLICATE_PAIRING.md`.

## 10. Carried forward, unresolved

- **DAQ's `no_vendor_in_doctrine`** claims enforced, but the cited test
  does not cite the id — the implementation does. Enforcement is real;
  the machine-checkable link from the *named test* is absent. DAQ's to
  close, reported not patched.
- ~~**Ingest probe: 0/3 gates proven reached**~~ — **closed. Now 2/3
  reached**, with the third still MALFORMED and still named. The gates
  were wired to the acquisition path
  (`structures.ingest.ingest_documents → run_scout(content_gates=…)`),
  and the per-code chemistry probe went **0 → 15 of 20 REACHABLE**
  through a real ingest. `class_assigned_at_ingest` remains a MALFORMED
  plant for the same reason as before — no document payload *can*
  produce an undeclared extraction method, since the extractor declares
  its own as a class constant — so it is reported, never counted as a
  hole.

  Two things had to be fixed in the probe itself to get an honest
  answer, and both were errors running in the flattering direction:

  - Its plants used `FACT:` lines, read into a **flat** mapping.
    `assert_property_context` requires `conditions` to be a *non-empty
    mapping*, which a flat extractor cannot express — so every plant was
    refused by the context gate first and **no plant could ever isolate
    the quantity gate behind it**. `quantity_is_typed` UNREACHED was a
    fact about the plant's format, not the gate's position.
  - The probe could not tell "nothing refused it" from "something else
    refused it one gate earlier". A plant refused under a **different**
    invariant id is now reported MALFORMED, never UNREACHED: an
    unreached verdict has to mean the payload *arrived* and nothing
    refused it.

  The probe still refuses to call this a rate over real documents. Every
  candidate it counts was planted to violate a gate, so 100% measures
  that the plants arrived — not that the world is dirty.
- **The I1–I10 numbered set** is unrecoverable from this repository —
  its referent ("see brief") is not in the tree. Recorded as
  unrecoverable rather than reconstructed; the "10" is retracted.
- **`cohort_identity` / `uncontrolled_conditions`** remain `unknown` in
  STE's probe — recorded, not guessed. DAQ ran the cohort probe in *its*
  substrate mid-phase and reports a representation gap; that result is
  **pointed at, not transcribed**, and STE's verdict is unchanged
  because the sibling measured gates STE does not have. Same boundary as
  §2, from the other side.
- **Tombstone / defeasance semantics** — the one recorded candidate
  bend (`evidence_append_only`), a core increment when addressed.

---

## Verified

Register locks **27/27**, all mutation-verified with per-test
attribution: **22/22 mutants killed by their named test** — tolerated
unreachable repo, citation check always passing, commit not recorded per
claim, contest detection disabled, core version moving without breaking
the closure, core version inferred from packaging, sourceless party
silently dropped, unbound party accepted as sourceless, currency asked
of the local clone only, offline derivation claiming currency, mirror
read as the holder's own name, deferral to a silent party tolerated,
owner status transcribed instead of resolved, committed register gone
stale.

Two mutants **survived** before being retargeted, and the reason is
worth keeping: both mutated `core.yaml`, and both target tests
manipulate that file themselves and restore what they found — so the
test's own save/restore silently reverted the mutant. **A mutation of a
file the test rewrites measures the test's bookkeeping, not its
assertion.** Both now mutate the enforcing code.

`invariant_register.yaml`: 3 parties, 51 invariants, **0 contested**, 4
deferred, emitted through the byte-identical shared serializer adopted
from DAQ, and a **fixed point** under re-derivation. `crates`: `fmt` and
`clippy` clean.

Three mutants survived the first battery and each was a real gap, not a
mutation artifact — the assertions were weaker than the claims they
carried. Deciding provenance per-repository left the mirror test green
because that pair's mirror carries a generator and took a different
branch entirely; the branch the mutation actually broke had nothing
asserting on it. **A rule is not covered because one of its arms is.**

### Suite: five failures, reported here and cleared two commits later

**This section went stale and was found by a measurement run for another
reason** — while counting hand-maintained restatements of derived state
to decide whether the generator was worth building. It said *"Not fixed
here"* and named a suite count of 2065; both were true when written and
neither was true a day later. The five were cleared at `20104e6`, and one
of them was not what it looked like — `nexus-pairwise` had genuinely
diverged. See `docs/STE_STAGE5_REPRODUCIBLE_BUILDS.md`.

That is the argument for the generator standing in its own document: a
hand-maintained projection of derived state goes stale silently, reads as
authoritative, and this one did it inside the record whose entire subject
is that failure mode. The rest of this section is retained as written —
it was accurate at the time and a dated measurement is worth more than a
quiet edit.

Reported rather than absorbed into a green claim.

- `test_execution_stage5_build.py` ×3 — **verified pre-existing.**
  Stashed every change in this phase and ran them at `cbe1185`: the same
  three fail identically with none of this work applied.
- `test_execution_proving{,_nexus}.py::test_a_wrong_program_specification_is_refused_before_proving`
  ×2 — the refusal fires correctly; the test's `pytest.raises(match=...)`
  regex (`"not registered"`) no longer matches the message wording
  (`"no built guest is registered for..."`). A stale assertion, in a
  message this phase does not touch.

**Not fixed here.** They are in the execution vertical, outside this
phase's scope, and quietly repairing unrelated tests in a commit about
cross-repository derivation would make the diff lie about what it did.

**An earlier, larger failure set was mine and was environmental.** A run
showed `host exited -9` (SIGKILL) across the proving and two-backend
suites — the OOM killer, because I had several pytest runs racing for
the ~8.5 GB prover on a 15 GB box. Re-run serially they pass. Worth
recording because the first read of that output was "eleven failures"
and the true count was five: *a measurement taken under contention I
created was not a measurement of the code.*

**Bent: zero** — and, for the first time, measured against a probe that
carries a computation property. The evidence for that claim is wider
than it was; §2 records exactly how narrow it had been.
