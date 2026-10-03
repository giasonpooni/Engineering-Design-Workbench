# The pairing the projection drops — and the wrong number it offers instead

## What was found, and by whom

The acquisition layer measured it, in its own substrate, and stated the
remedy precisely:

> `ComparisonGroup` carries exactly `(context, values, disagreement)`,
> and `values` is a bare tuple of floats. No observation id, no Record,
> no run identity travels with a value into the group. So the Mn group
> and the Mw group are two independent tuples and **nothing pairs the
> i-th Mn with the i-th Mw** … Recovering rho would mean joining on
> Record outside the grouping — **which is a consumer this repository
> does not have, not a capability it lacks.**

That consumer is here now, because the module it has to sit beside is
here. This is the second time the sibling has named a structural gap on
this side of the boundary and correctly declined to reach across it; the
first was the chemistry gate call site.

## Verified here, not taken on faith

It was read at a pin that is now stale, so it was re-measured at this
commit against these modules. All three findings reproduce:

| | |
|---|---|
| the group's fields | `{context, values, disagreement}` — `values` is `Tuple[float, ...]` |
| pairing available in the projection | **none** |
| pairing recoverable from the pool, joined on Record | **5 of 5** |
| per-run uncertainty differing by 1 g/mol | **5 groups of one**, every `disagreement` `None` |

## What this repository adds, and it is the sharper half

**The unpairing is not an absence. It is a wrong answer that is
available, confident, and stable.**

A group's values arrive in the order `RetrievalResult.observation_ids`
gives them, and that field is `tuple(sorted(set(...)))` with
`ordering: sorted_by_id` — so values come back ordered by
**content-addressed observation id**. Two properties measured on the same
runs have different content, therefore different ids, therefore two
*unrelated permutations of the same runs*.

```
inserted   Mn = 3251, 3402, 3188, 3610, 3305
returned   Mn = 3305, 3251, 3402, 3188, 3610
```

So zipping the two tuples does not fail. It succeeds:

| | |
|---|---|
| rho, joined on Record | **−0.9779** |
| rho, paired by index | **+0.3839** |

Wrong in **sign** — and stably so, the same wrong number every run and
across hash seeds, with nothing in the result to indicate it. The polymer
vertical's stated question is rho's sign.

An absence announces itself. A confident wrong answer does not. That is
why `correlation` takes a join rather than two sequences, and why there
is a characterization lock asserting the trap still exists: the day the
projection starts carrying identity, this module should be reconsidered
rather than kept out of habit, and that day should arrive as a failing
test.

### I explained it with the wrong mechanism first

The module docstring originally said the reordering came from
`_group_by_comparison_context`'s `result.sort(...)`. That call is real
and it does sort — **the list of groups**, not the values inside one. The
explanation named a true fact that was not the cause.

It was caught by a mutation aimed at the line the explanation named,
which deleted that sort and left the reordering exactly as it was. **A
wrong mechanism behind a right finding survives review easily, because
the finding keeps reproducing.** Nothing else in the process would have
questioned it.

## What was built, and what was deliberately not

`materials/replicate_join.py` is a **consumer**. `analyze`,
`ComparisonGroup` and `_comparison_context` are untouched, so no
grouping semantics move and no core version does either.

It refuses rather than guesses:

- A Record carrying **two different values of one property** is either
  two runs merged or a re-read disagreeing with itself. The join has no
  basis to choose, and choosing would invent a run. Refused **whole**,
  never partially — the record's other properties are equally suspect.
- A record **missing** a requested property is `incomplete` and
  **retained**. A join that silently discarded what it could not pair
  would report a clean `n` over an unstated denominator — the same defect
  as a rejection rate over gates nothing reaches.
- `correlation` returns `None` for exactly two cases and no others:
  fewer than two pairs, and zero variance in either series. Those are
  **definitional**, not thresholds. A minimum `n` would be a decision
  about what evidence suffices; the caller gets `join.n`.

### The fragmentation is surfaced, not fixed

`_comparison_context` keeps every content key except `property` and the
value key — `uncertainty` included. An instrument that reports a per-run
uncertainty, which is what a real one does, therefore fragments its own
replicates into singleton groups where no disagreement is computable.

**That rule was not changed.** Its docstring states the intent — absence
is never treated as a match — and differing *values* splitting a group
follows from that same rule rather than being a separate choice. Whether
a per-run uncertainty belongs in a comparison context is a question about
scientific semantics: a **decision, not a measurement**, and changing
grouping semantics is a core-invariant change under `bend_protocol`. So
the consequence is made askable (`is_fragmented`) and the decision is
registered as deferred, with a check that fires when a corpus carrying
per-run uncertainties actually lands.

The join pairs correctly *through* a fragmentation, which is the argument
for keeping them separate: fragmentation destroys comparability inside
the projection and leaves the pairing intact in the pool.

## The acquisition contract this rests on, unenforced anywhere

Both halves are load-bearing and they fail in **opposite** directions:

- **One Record per RUN.** Observation identity is over
  `(record_ids, extraction_method, content)`, so two runs reporting the
  same value from one Record collapse into one observation — correct for
  a re-read, wrong for a replicate, and it biases an estimated spread
  *downward*, the overconfident direction.
- **The run identifier NOT in content.** An acquisition locator in
  content makes every observation its own single-member group, so nothing
  is comparable at all.

Neither is enforced. This consumer cannot repair a corpus that violates
them; it can only refuse to guess.

## Three instruments caught themselves this phase

The mutation battery found three of its own mutants inert, and each was a
different way of testing nothing:

1. **A mutant aimed at the wrong mechanism** — see above.
2. **A mutant that never executes.** The write-barrier mutant injected an
   *uncalled* function. Dead code writes nothing, so the behavioural test
   correctly did not fire and the mutant "survived" having done nothing.
   The malformed-plant problem, in a third instrument.
3. **A mutant whose write is a no-op.** Re-putting an object the pool
   already holds moves neither the fingerprint nor its history — the
   store is content-addressed and idempotent. That makes such a write
   unobservable *by design*, not by a gap in the test. The mutant now
   introduces a referent the pool has never seen.

And the test it was aimed at was itself weak: it asserted the module's
*source* contained no `put_` call, and a mutant reaching the same method
through `getattr` and a split string walked straight past it. **A source
grep tests spelling; the pool's fingerprint tests what happened.**

## One ratchet fired on this document's own toolchain, and was right

`tests/test_architecture_sync.py` greps every non-test file for minting
seams, and flagged the new mutation script — first for a mutation string
that never executes, then again for a *comment quoting the name*. Both
were correct: a grep-based ratchet cannot tell code from prose. The
response was to stop writing the token, **not** to add the script to the
allowlist. Widening the check that guards the write barrier to buy a
green suite is the trade this project exists to refuse.

## The aggregate rows — the same trap, one layer up, in my own new code

The sibling's DAQ-2 landed a day after this consumer's first draft. It
took a **real** replicate report — Impact Analytical R190048, from
regulations.gov — and measured what a faithful transcription does. Its
third question:

> *is the aggregate's lineage to the two injections recoverable:* **NO**.
> The Average Record's locator is `Average/row-2` and nothing connects it
> to rows 1 and 2. The lineage is **positional in the document** … and
> position is exactly what acquisition discards.

With the incidental refusals removed, that table lands **five Records** —
two injections plus Average, Standard Deviation and % RSD — each carrying
Mn and Mw, with *"nothing distinguishing them."*

**I ran my own consumer against that shape before saying anything about
it, and it inherited the defect exactly:**

| | |
|---|---|
| Records in the pool | 5 (2 injections + 3 aggregates) |
| `join.n` | **5** |
| refusals | **0** — it has nothing to refuse them *on* |
| rho reported | **+0.9986** |
| the real replicate set | **n = 2** |

The pairs included a % RSD paired with a % RSD and a standard deviation
paired with a standard deviation, and the +0.9986 is driven almost
entirely by three summary rows spanning 8.4 to 24,969 — a magnitude
effect, not a correlation. **The same class as the index-pairing trap
this document opens with: a plausible recovery returning a confidently
wrong number, one layer up, in the code written to answer it.**

### Two ways to derive it were checked, and both refused

- **The evidence class.** It is a total function of `extraction_method`,
  so every row from one adapter shares one class — correctly, since a
  transcribed average and a transcribed injection are equally *the
  document's claim*. It does not separate them and was never meant to.
- **The Record locator.** It *does* separate them in this corpus
  (`Average/row-2` against `PA191 (S190109)/1`), and matching on it is
  the **literal-enumeration hazard** the sibling has just watched fire on
  real data: a two-element tuple of identity-column names that did not
  contain the word the first real vendor used. A list of aggregate labels
  breaks on the next vendor, and breaks *silently*, by admitting an
  aggregate.

So the fact is not in the pool, cannot be inferred, and is **declared**.

### A join is a fact; "these are runs" is a claim

They are now separate. `join_on_record` still returns five, because five
Records *is* the truth about the pool, and `paired_values` needs no
declaration. What changed is that `correlation` **refuses** until a
caller has said which Records are replicate runs — and it *raises*
rather than returning `None`, because `None` means "undefined on this
data" while this is "you have not said what this data is."

That is the same move the sibling's own later adapter makes for its four
provenance fields, and its own contrast records the verdict: the adapter
**with** the declaration channel is the right one, and the earlier one
was never updated.

## What is not claimed

That any of this measures a material. Every number here is the real code
run against **constructed** replicate observations, which establishes
what the substrate does and nothing about the world. The one real anchor
in reach — a Waters Empower GPC report from EPA ChemView, TSCA
P-22-0051 — is deliberately positioned in the sibling's `instrument/`
layer, where an AST-enforced rule forbids the product from importing it
at all. It is ground truth for a forward model, not evidence for
acquisition, and transcribing it into an ingestible fixture would let a
forward model be validated against its own input.

So the corpus still does not exist, and the reason is a **structural
bound that someone chose**, not an oversight. What changed here is that
when it does exist, the number the polymer vertical asked for will be
recoverable — and the wrong one will not be silently available.
