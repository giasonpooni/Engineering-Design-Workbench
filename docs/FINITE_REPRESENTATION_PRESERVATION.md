# Finite representation preservation V1

Research increment, stacked on representation-aware Needle PR #96. It adds
executable checks to the **State + Representation + Morphism + Invariant**
synthesis. It is not a new execution engine or a replacement for the scientific
instruments, System Board, SemanticRegistry, Session or existing Needle gate.

## 1. Board-to-morphism binding

`ciw.board-morphism-binding.v1` binds every and only Board OPERATION node to one
scientific morphism in the exact registry. It retains the exact Board digest,
registry digest, domain/codomain representation digests, morphism digest and
parameter values. A changed Board or registry requires a new binding.

The binding checks semantic capability identity and that every supplied Board
parameter is declared by the scientific morphism. Omitted optional parameters
continue to use the existing semantic/provider defaults. V1 supports one output
socket and at most one input socket per bound operation.

A DATAFLOW edge must preserve exact source codomain / target domain identity.
A DEPENDENCY edge does not assert scientific representation equivalence. There
is no implicit unit, frame or scale conversion.

```text
Board + exact scientific registry + explicit node assignments
    -> content-bound scientific signatures
    -> existing Board compiler
    -> existing semantic compiler
    -> ordinary experiment
```

`ciw.board-morphism-compilation.v1` retains the ordinary compilation unchanged.
Both validators recompute derived content, rather than trusting a valid hash
alone. The real oscillator qualification executes the bound and ordinary
periodograms separately, comparing data, runtime identity and source evidence.

This binds declared scientific signatures. It does NOT validate the scientific
meaning of a runtime payload or discharge textual preconditions, invariants,
verification requirements or authority requirements. Those remain retained in
the bound registry and require their existing separate checks.

```sh
net board bind-morphisms board.json registry.json binding-spec.json --output binding.json
net board compile-bound board.json registry.json binding.json --output bound-compilation.json
```

The binding specification is:

```json
{
  "binding_id": "spectrum-signature",
  "node_morphisms": {"spectrum": "signal.periodogram.transform.v1"}
}
```

Every operation in the actual supplied Board must be covered. The qualified
single-operation example uses the existing periodogram morphism and provider.
The experiment remains at
`bound_compilation.board_compilation.semantic_compilation.experiment`.

## 2. Finite measure-aware preservation witness

`ciw.finite-preservation.v1` evaluates caller-supplied complete tables for:

- finite state spaces X and Y;
- a projection P: X -> Y;
- declared probability p(x), nonnegative and summing exactly to one;
- a scalar observable f(x), its query name and unit;
- a fine intervention N: X -> X and a proposed coarse intervention B: Y -> Y.

Both endpoints must explicitly declare `ciw.finite-state-label.v1`. This refuses
to relabel an arbitrary table as a witness about continuous signals or a real
periodogram. Each space contains 1..64 distinct labels. Inputs use integers or
rational strings, not floats. Rational numerators and denominators are bounded
by 10^9; maps must be total and remain inside their declared spaces.

Exact Fraction arithmetic evaluates the pushforward:

    p_Y(y) = sum_{P(x)=y} p(x)

and, for positive-mass fibres, the conditional expectation:

    E[f | P=y] = sum_{P(x)=y} p(x) f(x) / p_Y(y).

The witness retains every fibre, its conditional probabilities, conditional
mean and conditional variance. It checks the integrated conditional mean
against the original expectation and reports expected within-fibre variance.
That variance has squared query units; it is not a universal information score
or a measurement of physical calibration error.

For a zero-mass fibre, the compatible state labels remain visible, but the
conditional probabilities, mean and variance are null with
`ZERO_MASS_UNDEFINED`. No unique fine state or conditional law is invented.
These are fibres of the retained declared finite model, not newly acquired or
recovered empirical states.

## 3. Intervention preservation is stronger than matching distributions

The state-level square is evaluated exhaustively over the declared finite set:

    P(N(x)) == B(P(x))  for every x in X.

All labels are checked, including labels assigned zero probability. The record
retains each failed state and both outputs. It separately checks whether any
deterministic coarse intervention can exist on the image of P: if two members
of one fibre have different projected post-intervention states, that proposed
fine intervention cannot descend to a deterministic coarse map there.

Matching the two resulting distributions is reported separately. It is never
substituted for this state-level check.

`require_finite_local_support` refuses unless the current contracts explicitly
declare coarse intervention support AND the finite square passes. It does not
create a Needle plan. The existing Needle gate and its baseline/target binding
remain unchanged. A finite fixture is not automatically evidence that some
unrelated live Needle coordinate supports the intervention.

### Retained example

The synthetic fixture has four equally weighted labels, grouped into cold/warm
pairs, and an observable of 270, 274, 290 and 294 K. This is an arithmetic
example, not a calibrated thermal model.

| Check | Compatible group switch | Incompatible partial switch |
| --- | --- | --- |
| Coarse probability masses | 1/2, 1/2 | 1/2, 1/2 |
| Original / integrated conditional mean | 282 K / 282 K | 282 K / 282 K |
| Conditional group means | 272 K, 292 K | 272 K, 292 K |
| Expected within-group variance | 4 K^2 | 4 K^2 |
| Resulting distributions match | yes | yes |
| State-level square commutes | PASS | FAIL |
| State-level counterexamples | 0 | 2 |
| Conflicting fibres | 0 | 2 |

Thus **preserved averages and equal output distributions do not establish
intervention sufficiency**. A separate fixture assigns zero probability to the
only failing states and still refuses the state-level preservation claim.

The exhaustive four-state test enumerates all 256 fine endomorphisms and all
four coarse endomorphisms: 1,024 pairs, of which exactly 64 commute for the
chosen two-by-two partition. This is exhaustive only for that finite case.

## Run and retain the evidence

```sh
net morphism finite-demo --output-dir finite-demo
net morphism finite-check finite-demo/registry.json finite-demo/compatible-spec.json --output checked.json
net morphism finite-verify finite-demo/registry.json finite-demo/compatible-witness.json
net morphism finite-verify finite-demo/registry.json finite-demo/incompatible-witness.json
```

`finite-check` and `finite-verify` return 0 for supported PASS, 2 for a valid
retained negative result, and 1 for malformed/refused input. Failed witnesses
are retained rather than erased. The demo intentionally includes both cases
and returns 0 when the complete demonstration finishes. Existing output files
or demo directories are never overwritten.

A witness validator reconstructs all derived results from its retained inputs
and exact registry. Re-sealing a fabricated PASS does not make it valid.

## Attribution and status

**Established mathematics.** Pushforward measures, conditional expectations and
composition are existing mathematics. Primary formal references include the
Mathlib documentation for
[measure pushforward and map composition](https://leanprover-community.github.io/mathlib4_docs/Mathlib/MeasureTheory/Measure/Map.html).
The displayed finite conditional-mean identity follows directly by collecting
the weighted sum over the partition fibres. No source implementation is copied.

**Architectural adaptation.** Exact representation identities bind Board
signatures; finite commutative squares test declared intervention preservation.

**Project hypothesis.** Task-sufficient representations may reduce cost while
preserving required distinctions. This increment does not measure a general
productivity improvement, choose the cheapest representation, or prove that
hypothesis across domains.

**Implemented evidence.** Exact finite checks, retained negative witnesses,
recomputed seals/bindings, a real existing periodogram comparison, and targeted
regressions. CI retains the source commit, wheel, JUnit results, demo records and
runtime versions. Read the actual run before claiming a platform is qualified.

**Conceptual inspiration only.** Higher categories, sheaves, indexed/fibred
architectures, moduli spaces and information geometry are not general runtime
capabilities implemented here. Mathlib/Lean is a reference, not a new dependency
or a proof certificate for this Python implementation.

## Boundaries and next dependency

There is no new provider, optimizer, scheduler, automatic schema rewrite,
canonical-state mutation, evidence admission, physical control or causal claim.
Probability is declared; empirical calibration remains unresolved. This
increment does not integrate a finite witness into live Needle execution or
perform coarse-to-rich acquisition/materialization.

The next dependency is an **evidence-bound expansion operation**: resolve a
specific retained richer representation, verify its source identity and
projection relationship, and only then reconsider the existing intervention
gate. Conditional fibres must not be mistaken for recovered physical truth.
