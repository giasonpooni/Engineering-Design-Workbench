# The data platform's two load-bearing properties, measured

The plan rests on two claims, and every layer above the canonical one is
disposable only if both hold:

- **no serving projection writes canonical truth**
- **serving projections are rebuildable** from canonical state

Where either fails for a projection, that projection carries state
nothing can regenerate, and the canonical layer is not canonical for it.

Both are checkable **now, before any of the infrastructure exists** —
and that is the reason to check them now. A projection that turns out
not to be rebuildable is a cheap finding today and an expensive one
after a lakehouse has been built on the assumption.

## Result

| | |
|---|---|
| projections discovered in the tree | **7** |
| probed | **7** |
| excluded, each with a stated reason | 2 |
| **rebuildable** | **7** |
| writes upstream | 0 |
| not rebuildable | 0 |

Seven of seven is a fact about seven modules. It is not a guarantee
about the eighth, and the artifact says so.

## The three things that make the result worth anything

**Enumerated from the tree, not from memory.** The probe *discovers*
projection modules and **refuses** if one is uncovered — or if it covers
a module no longer present, which is reporting on nothing. A conformance
report over the projections someone remembered is the exact shape this
repository has already measured once: every check passing, over a set
that omitted the failing one.

**The barrier is behavioural, not grepped.** The canonical layer's own
fingerprint is taken before and after; a write moves it however it is
spelled. A source search for `put_` tests *spelling*, and a mutant
reaching the same method through `getattr` and a split string walked past
exactly such a check in this repository the day before.

**The canonical state is non-empty.** A projection over an empty layer
rebuilds identically for the wrong reason — the vacuous-plant shape.

## Two defects found in the probe itself

**Three of seven barriers were asserted, not measured.** The backend
probes passed `barrier_held=True` because a backend takes an IR document
and not a pool. That is a good argument and it was *not a measurement* —
three claims inside a probe whose whole purpose is to replace claims with
measurements. Now both halves are run: the input IR must be unchanged
after compiling (a backend that rewrote its input would corrupt the very
thing a rebuild starts from), and the signature must take no pool.

**The aliasing check could not be told from a constant.** A projection
that *aliased* canonical state could mutate it without ever calling a
write method — the fingerprint barrier would hold and the property would
still be false. The real projection never aliases, so a mutant hardcoding
`False` changed nothing observable and survived. The check is now
extracted and driven both ways.

Both are the same family, and it is the fifth appearance in this
project: **a check whose inputs cannot span its branches tests nothing
about the branch.**

## What this does not claim

That a rebuildable projection is **correct**. It says the projection is a
function of the canonical layer *on this data* — which is what makes it
disposable, not that the function is the right one.

And it does not claim rebuildability **at scale**. These run over a small
canonical state in-process. The plan's own advice applies to its
verification too: add the evidence when the workload demands it.
