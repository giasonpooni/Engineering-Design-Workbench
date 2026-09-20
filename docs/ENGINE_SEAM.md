# The engine seam: what two engines must share, and what they must not

Scientific Computation Runtime's `SpecificationDispatcher` accepts engines
through a `runner` boundary — the native backend, Scientific Compute Layer
(SCL), and GROMACS. The historical `STE` label below identifies this runtime's
existing implementation; its execution identifiers are unchanged. This records
what interchangeability requires while preserving each engine's numerical method.

## The test that was proposed and could not be built

The obvious cross-engine check is *run one configuration through both
and require the answers to agree*. It cannot exist here:

| | STE `execution-kernel` | SCL `lj_pairwise` |
|---|---|---|
| computes | Σ `2⁸⁰/r⁴ − 2⁴⁰/r²` | `4ε((σ/r)¹² − (σ/r)⁶)` and forces |
| arithmetic | `i128`, truncating division | IEEE-754 doubles |
| bounds | coordinates \|c\| ≤ 2²⁰, faults on coincident | cutoff radius |
| runs in | a zkVM (RISC-V, `no_std`) | CPU and CUDA |

These are **different functions**, not two implementations of one.
Measured at the same separations:

| r | STE | SCL |
|---|---|---|
| 2 | +7.56e22 | −6.15e−02 |
| 4 | +4.72e21 | −9.76e−04 |
| 8 | +2.95e20 | −1.53e−05 |

Opposite in sign, ratio moving by a factor of 20 across r = 2…8, minima
at r ≈ 1.48×10⁶ and r ≈ 1.12. No scaling turns one into the other, so
**no configuration exists on which they should agree** — and a test
asserting agreement could only be made to pass by inventing a tolerance
wide enough to mean nothing.

The exponents are not a matter of taste. STE's kernel must be provable
inside a zkVM, where floating point is not reproducible and therefore
not provable, so it is integer arithmetic end to end. SCL's must reach
CUDA. Neither constraint admits the other's implementation.

## What is required instead

Engines are interchangeable not because they compute the same thing —
they must not — but because they observe the same contract:

1. **Identities are the specification's, not the engine's.** A caller
   recomputes `specification_identity`, `program_identity` and
   `input_identity` from the request alone. An engine that minted its
   own would make results incomparable and unverifiable later.
2. **Determinism.** The same specification twice yields the same
   identities and the same output bytes.
3. **The input is read.** Different input ⇒ different input identity,
   different specification identity, different output.
4. **Refusal is fail-closed.** An undefined computation returns no
   output and *no computation identity* — never a fabricated zero — while
   the request stays nameable.

## The hazard that exists only because there are two

Two engines behind one seam create a risk a single engine cannot have:
**if their identities could collide, a warrant, proof or stored result
about one would be indistinguishable from one about the other.**
Everything downstream is built to trust identity, so a collision is the
worst defect available here.

Three cases are driven directly, and the sharpest needs no second engine
installed:

- two engines, distinct program and specification identities
- **the same input bytes under a different program** — two engines can
  legitimately be handed the same coordinates, and the requests must
  still be distinct
- the same program under a different configuration — so ε = 1.0 and
  ε = 5.0 never answer to one name

The second of those was added because a mutant that dropped `program`
from the specification identity **survived** the two-engine test: those
two engines also differ in their input, so the test could not isolate
the program. The mutant was a real defect the battery caught and the
original test could not.

## Availability

SCL's engine needs its native binary. Absent, the engine-specific
checks run against STE alone and the cross-engine checks skip with a
stated reason — an environment gap, not a failure. Both directions are
verified: **12 passed / 1 skipped** with SCL built, **7 passed /
2 skipped** without.

## Locks

`tests/test_engine_seam_conformance.py` — the contract, parameterised
over every engine present, with a guard against the battery running on
an empty list. `scripts/mutate_seam_conformance_checks.py` — 6/6 mutants
killed.

One mutant is deliberately **not** in that list: neutering the collision
assertion itself. It is ill-posed rather than surviving — it makes a
test vacuous and then asks that same test to notice, which no test can
do. Killing it would require a meta-test asserting the check operates on
more than one element, which is a regress with no natural stopping
point. What protects the check is structural: it is skipped below two
engines, and it compares a set's size to a list's, which says nothing
unless there are at least two entries.
