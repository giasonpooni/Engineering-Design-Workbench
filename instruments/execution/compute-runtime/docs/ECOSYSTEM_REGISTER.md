# The ecosystem register — what is an apparatus, and what is merely present

**Notation Systems develops computational instrumentation and operates
provenance-bearing computational corpora.** Scientific Computation Runtime
provides declared scientific execution within that stack.

This document retains the ecosystem register's recorded measurements and
reasoning. Counts, repository labels and bindings refer to the inspected
snapshots; they are not a live census of the renamed stack. The [current
component map](README.md#component-responsibilities) describes responsibilities
without changing those historical measurements.

## The measurement

Twenty-five repositories in reach. Classified on **evidence** — an
authored core declaration, external commit authorship, a third-party
copyright — and never on the GitHub org a repository sits under.

| | |
|---|---|
| repositories in reach | **25** |
| apparatuses (bound to the core) | **3** |
| vendored inputs | **16** |
| **unresolved** | **6** |
| vendored, sitting under **our own org** | **6** |
| vendored, referenced by **nothing** | **8** |
| apparatuses declaring a role | **1 of 3** |

`APPARATUS` here means **bound to the core** — an authored architecture
declaration — and *not* "belongs to the company". Those are different
predicates, and the difference matters below.

The three apparatuses measured in that snapshot are Scientific Computation
Runtime (then Scientific Transformer Engine), the acquisition channel, and
the compute layer. All three bind
`core@1.0.0`, so they already agree on the core.

## Org ownership is not authorship

Twelve of the twenty-two vendored repositories sit under the
`notationsystems/` org **while being other parties' work**, by their own
commit history and copyright:

- `notationsystems/topopy` — Dan Maljovec's, MIT, © 2018
- `notationsystems/RiemannFM` — Yongli Mou's, © 2026
- `notationsystems/SP1-zero-knowledge-virtual-machine` — Succinct's SP1
- `notationsystems/risc0-zero`, `notationsystems/geometrickernels`,
  `notationsystems/physgto`, and six more

A coherence exercise that read the org prefix as a provenance claim
would have declared **25 apparatuses and been wrong about 22 of them** —
and the map would have looked entirely plausible, because every URL
agreed with it.

**This is the mirror rule at repository scale.** The invariant register
already enforces it per file: a mirror is not a source, byte-identity is
what makes it dangerous, and only provenance separates a copy from its
origin. A fork under your own org is the most convincing mirror there
is, precisely because the address supports the claim.

So the classifier never asks "is it under our org?" as a positive
signal. Org membership appears in the output only as a **warning that a
mirror is wearing our name**, and the order of checks is pinned by a
test.

### Three verdicts, not two

`UNRESOLVED` exists so that a repository with no discriminating evidence
can be refused rather than rounded toward ours. Two verdicts would force
a guess, and the guess would run in the flattering direction. Today
nothing lands there — which is a fact about this tree, not a reason to
remove the third verdict.

## The first classifier disowned six repositories on nothing

The acquisition channel recorded `architecture/ecosystem_census.yaml`
independently — against this repository at an **older pin than this
register existed at**, so it is not derived from this artifact. It
enumerates **six repositories carrying the name and seven apparatuses**,
where this register reported three.

Neither count is wrong. They measure different predicates: this one asks
*is it bound to the core*, the census asks *does it carry the name*. But
the census listed `morphohdl` as a company repository, and this register
had it `VENDORED_INPUT` — so one of us was wrong about a specific thing,
which is checkable.

**It was me, and the evidence was garbage.** The copyright extractor had
matched Apache-2.0 *boilerplate*:

> "Licensor" shall mean the copyright **owner** or entity authorized by
> the **copyright owner** that is granting the License.

That is the licence's definitions section, not a grant. The match would
have disowned **every Apache-licensed repository**, on nothing. And the
other weak signal was just as bad: every repository here is a **single
squashed commit**, so its commit author is whoever last touched whatever
was imported — which says nothing about ownership.

Both errors ran in the direction that made the ecosystem look **smaller**
and the classifier look more **decisive**. That is the harder direction
to notice, because a wrong exclusion produces no loud consequence.

### Strong evidence only

Three signals now settle it, each sufficient on its own, and each driven
alone in the tests so none is carried by the others:

- the remote is **outside our org** — the address says whose it is
- the project **declares its own upstream** in `Cargo.toml` /
  `pyproject.toml` / `package.json`. SP1 says `succinctlabs/sp1`; RISC
  Zero says `risc0/risc0`. A self-declaration of origin is the strongest
  evidence available and is the one form of authorship evidence this
  project already trusts everywhere else.
- a **copyright grant carrying a year** — what separates
  `Copyright (c) 2018, Dan Maljovec` from the definitions section

Anything else is `UNRESOLVED`: **not adopted, and not disowned**. Six
repositories moved there. The third verdict stopped being decorative the
moment the rule got honest.

## What this register structurally cannot see

The census records **Notation Physical Commerce** living in `commerce/`
inside the acquisition channel, deliberately, with **no repository of its
own**. A register keyed on repositories would never have a row for it.

Recorded as a limitation rather than closed, because closing it means
keying on something other than what is being enumerated. An instrument
should say what it cannot see.

The census's rows are **pointed at, not copied here**. They are that
party's artifact and its claims are its own to state; a duplicate would
drift, and a reader could not tell which was the source.

## A folder is not an ecosystem

**Eight vendored repositories are referenced by nothing** in any
apparatus — not in code, not in configuration, not in prose. They are
present, and presence is not participation.

They are recorded `UNREFERENCED` rather than omitted, on the same
reasoning that makes an unreached gate a silence rather than a clean
result: a component nothing calls contributes nothing, and quietly
dropping it would make the system look like it has fewer loose parts
than it has.

What actually carries load is small and namable: **GROMACS** (the
molecular dynamics bridge) and the three zkVMs — **SP1**, **RISC Zero**,
**Nexus** — behind the proof machinery. `morphohdl` is
`UNRESOLVED` and, as of the sibling's latest commits, referenced by both
apparatuses — its relation to this repository's own `morpho/` package is
**not determined**, and the census is explicit that it must not be
assumed from the name.

## The instrument counted its own prose

`topopy` and `RiemannFM` first came back **INTEGRATED**, while a plain
grep found no reference to either anywhere in any apparatus.

The only file matching was **the classifier itself**. Its docstring
cites both as examples of the mirror finding, and the citation counted
as evidence of the integration it was written to deny.

That is the same class as the emitted invariant register being re-read
as its own source — 26 rows became 77, every one contested — and as the
three contaminated attempts to locate a derived fact in prose *by its
value*. Stated generally: **an instrument that names the things it
classifies will classify its own prose.** It is the deriving-party
exclusion one level out: a party cannot witness a fact about the act it
is currently performing.

The exclusion is **declared, not pattern-matched**, and locked in both
directions — every excluded path must exist (a too-narrow exclusion lets
the contamination back in) and nothing outside the instrument may be
listed (a too-wide one hides a real dependency, failing in the direction
that makes the system look cleaner).

## No apparatus declared its role — and one still doesn't get to write the others'

All three bind the same core. **None stated what it *is*** within the
company. That is the coherence gap, and it is now a measurement rather
than an impression.

It is closed **per repository, by each party**. This repository declares
its own role in `architecture/apparatus.yaml`; the register reads that
file, reports `NOT_DECLARED` for the two that have none, and **does not
fill them in**. A role written here on another party's behalf would be a
self-declaration this party is not entitled to make — the same
provenance-entitlement rule the invariant register applies to every
other claim, applied to the sentence that says what a repository is for.

A central roster would have been faster and would have been one party
writing every other party's self-description. That is the artifact this
company's whole discipline exists to refuse.

## What this does not claim

Not a licence review, and not an assessment of any vendored input. It
classifies **authorship** and measures **reference**. `INTEGRATED` means
an apparatus names it in a load-bearing file — a fact about this tree,
not a judgement about the input. And a vendored repository being
unreferenced is not a reason to delete it; it is a reason not to count
it as part of the system while it is.

## The namesake question, settled as far as evidence allows

The census recorded that this repository contains a `morpho/` package
naming a Morpho IR, and that whether that IR is `morphohdl`'s or a
namesake **is not determined there and must not be assumed from the
name**. It is this repository's package, so it is settled here.

The finding is two-sided, and both sides are surprising.

**The name is more shared than the census knew.** This package does not
merely say `morpho`. Its modules call themselves **Morpho HDL**, in their
own docstrings — the same two words, not a prefix in common.

**The substance is less shared than the name suggests.** Measured across
both trees: zero shared domain vocabulary (*circuit*, *netlist*,
*verilog*, *cell definition*, *rewiring*, *wasm* appear in neither
direction), zero cross-reference either way, and disjoint subject matter
— a content-addressed language front-end carrying provenance here, an
experimental graph-rewrite system for growing circuits there.

**And there is an artifact that would settle it.** This package
implements **Frozen Specification v1.0.0 §7.A and §7.B**, cited by name
in `morpho/lexer.py`, `morpho/parser.py` and `morpho/ast.py`. Nothing in
`morphohdl` references that specification; its only grammar hit is inside
a vendored syntax highlighter.

**Verdict: shared name, unshared referent as far as this tree shows.**
Not asserted as unrelated — two implementations of one idea in two
languages would look exactly like this, and this machine holds no
document that decides it. What is settled is that nothing here licenses
treating them as one thing. The census's instruction not to assume from
the name stands, now with the evidence behind it.

## The core they bind

All three apparatuses bind `core@1.0.0` **by label**, and that label moves
only under `bend_protocol` — so many core commits carry it. The register
publishes a **content digest** beside the bindings, so a binding is
checkable rather than nominal. See `docs/CORE_IDENTITY.md`; the gap was
observed by the census and could only be closed here.

### The heading was true and the field under it was not

The register published **one** digest under this heading. Measured, no
binding party imports the track it covered: the acquisition channel
reaches into this repository hundreds of times — 291 measured
2026-09-03, 293 on 2026-09-05 — and into that track **zero** on every
measurement. The
register was publishing a fingerprint of code nobody uses, under a
heading claiming the opposite.

`the_core_they_bind` now carries `measured` — a digest **per track**, and
per party the track it binds **with the import counts behind it**. A
`binds` without counts would be a declaration; the counts are what let a
reader check it rather than take it.

The old single field is kept for continuity and is now **named**:
`the_digest_field_is_the_TWIN_track` says what it is and points at
`measured`. An unlabelled leftover under a heading that used to mean
something else is exactly how the original defect read to anyone
downstream — which is the whole reason it survived as long as it did.

## A party cannot witness the act it is performing — the fourth time

The full suite caught the register disagreeing with a fresh derivation by
two fields:

```
- "commit": "fde240641823"      - "commits": 161
+ "commit": "98f35f9f09c1"      + "commits": 162
```

The register records each apparatus's HEAD — including **its own** — and
committing the register advances it. The artifact is permanently one
commit stale about itself and can never equal a fresh derivation
byte-for-byte.

That is the same shape this project has now met four times:

1. the invariant register recorded the commit its sources were read at,
   and committing it advanced that commit
2. the emitted register was re-read as its own source — 26 invariants
   became 77, every row contested
3. this module's own docstring, citing repositories as examples of the
   mirror finding, counted as evidence that those repositories were
   integrated
4. and now the register's own HEAD

The fix is the established one: the fields **stay in the artifact**,
because a reader wants to know which commit a reading was taken at, and
are excluded only from the comparison the artifact makes **with itself**
— the one place they cannot be evidence.

**Narrow by construction.** Only the deriving apparatus's row is touched.
A sibling moving is still a difference the fixed point must see, and a
planted sibling commit is required to break it — an exclusion wide enough
to cover every apparatus would excuse exactly the drift this register
exists to catch.

And the lock for it had to be driven over a **constructed** document.
Right after an emit, the artifact and a fresh derivation carry the same
commit, so removing the exclusion changes nothing observable until the
next commit lands — a mutant survived precisely that window. A check that
only works between commits is not a check.
