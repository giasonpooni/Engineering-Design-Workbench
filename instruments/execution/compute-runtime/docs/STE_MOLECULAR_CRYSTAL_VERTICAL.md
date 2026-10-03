# Scientific Computation Runtime — The Molecular / Crystal Structural Vertical

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
A new scientific INPUT FAMILY entering the existing substrate — not a
new architecture. The five identities stay separate and none was
collapsed:

    STRUCTURE    ste.structure.*         structures/ (new)
    COMPUTATION  ExecutionSpecification  unchanged — structures LOWER into it
    OPERATION    OperationTrace          unchanged — occurrence-distinct
    WARRANT      WarrantCache            unchanged — proof bytes, re-verified
    EVIDENCE     EvidencePool            unchanged — content-collapsing

## Representations

**Molecule** (`structures/molecule.py`): an ordered tuple of atoms,
each a capitalized element symbol plus Cartesian coordinates in
**integer picometers**. Canonical bytes:

    ste-molecule v1
    convention cartesian-pm
    atom <Element> <x> <y> <z>          (declared order)

**CrystalStructure** (`structures/crystal.py`): three integer lattice
row vectors (pm, an explicit 3×3 row-major matrix) plus ordered sites
with fractional coordinates in **integer millionths**:

    ste-crystal v1
    convention fractional-millionths lattice-pm row-major
    lattice <ax> ... <cz>
    site <Element> <fx> <fy> <fz>

Identity = `commit(tag, [canonical bytes])`; the tags differ, so a
crystal identity can never collide with a molecular one (locked by
test). A crystal is semantically periodic, not a molecule with unused
fields — the kernel makes it executable: a single-site crystal's
nearest neighbour is its own image one cell over; a single-atom
molecule has no pairs (both locked by test).

**Canonicalization — exactly what determinism required, probed, no
more**: atom/site order is identity-bearing (the kernels consume atoms
in input order — sorting would equate computations the engine
distinguishes); coordinates are exact integers (the float→pm rounding
burden is paid once, at construction — `structures/library.py` records
where each real structure paid it); element symbols are validated and
never normalized (`"h"` is refused, not equated with `"H"`); nothing
temporal, host-local, or occurrence-shaped can reach an identity.
**Physical equivalence is deliberately NOT computational identity**: a
relabeled or reordered water is "the same molecule" physically and a
different description computationally; no equivalence relation is
established because no workload has needed one yet.

## Real structures (`structures/library.py`)

Water (O–H 95.7 pm, 104.5°), methane (ideal tetrahedron, C–H 108.7 pm),
FCC argon (a = 526 pm, 4 sites), rock salt (a = 564 pm, B1) — textbook
equilibrium DESCRIPTIONS with their rounding recorded, claiming
nothing about any physical sample.

## Kernels (through the existing engine boundary — registry grew 2 → 4)

- `scout.native.radius-of-gyration-kernel.v1` — mass-weighted Rg²,
  integer arithmetic. Exists for a **discovered epistemic reason**: the
  pairwise kernel consumes coordinates only, so a pairwise proof binds
  geometry and *cannot* bind element identity (changing O→S moves the
  structural identity but not the pairwise input commitment — locked by
  test as a fact, not hidden). In the Rg kernel the element's integer
  mass is part of the CONSUMED bytes, so an element change moves the
  input commitment. Methane's Rg² is pinned exactly:
  `(4·3·63²)//16 = 2976 pm²` recomputed independently.
- `scout.native.crystal-lattice-kernel.v1` — `V = |det L|` plus the
  minimum-image nearest-neighbour distance² over the committed
  `{-1,0,1}³` shift set. Exact integer results locked: argon
  `V = 526³ pm³`, `mind2 = 526²/2` (a/√2); NaCl `(a/2)²` (Na–Cl).
  Coincident sites/images fault (code 7) — refused, never zero.

Neither kernel has zkVM guests yet: proving them is **refused
attributably** by the Stage 5 registry gate ("no built guest is
registered…") — an explicit refusal locked by test, never a silent
skip or a false warrant.

## Lowering — the one insertion point (`structures/lowering.py`)

Pure deterministic functions `Molecule/Crystal → ExecutionSpecification`
over the existing descriptors; unknown elements are refused, never
guessed. **The Morpho decision, recorded**: the question "can a
structure lower into an existing ExecutionSpecification without a
parallel execution architecture?" is answered YES by these ~20-line
total functions directly. The repository's `morpho` compiler pipeline
would insert a language between two byte formats that already agree;
it becomes justified at this boundary when a structural transformation
needs a *program representation* (parameterized generation, symbolic
manipulation) — a need no real workload here has yet exhibited, so no
Morpho stage was inserted and no visualization detour was built.

## GROMACS bridge (`structures/gromacs_bridge.py`)

`molecule_to_gro` renders a Molecule to deterministic `.gro` bytes
(integer pm → exact 3-decimal nm; origin → box centre by integer
shift), consumed by the *unchanged* stage-1/4 external GROMACS
workload. A real argon-trimer Molecule ran through `gmx grompp →
mdrun → energy` to a completed potential (locked by test); moving one
atom moves the specification identity. **Stated plainly: no structural
proof says anything about a GROMACS execution.** They share only the
structure's identity in the structural ledger; the GROMACS run keeps
its documented weaker trust posture (externally executed, identities
computed by our module, engine behavior declared).

## Proofs, warrant reuse, tampering (real artifacts)

Water's pairwise statement proved on **Nexus** through the existing
reproducible pairwise guest (instrumented host: `prove` × 1); the
identical structure re-lowered → the identical statement → cache HIT,
re-verified without proving; a moved atom → different statement →
MISS (the old warrant stays valid for its own statement only);
corrupting the stored proof bytes → the hit still goes to the verifier
and FAILS. The campaign adds **SP1** over the same water statement:
one computation, two independent warrants — never one proof for two
computations.

## Campaign (measured; `scripts/structural_campaign.py`)

Seven real structures — water (×3, the repeated structure), methane, a
moved-atom water (the changed structure), FCC argon, rock salt, a
strained FCC cell, and the argon trimer through GROMACS — ten points,
every layer engaged, all measured in one run:

| measured | value |
|---|---|
| structures processed | 7 (each with its structural identity printed) |
| executions / successes / failures | 10 / 10 / 0 |
| trace occurrences | 10 (all SUCCEEDED; occurrence-distinct as always) |
| unique statements (specs) | 8 |
| observations / unique evidence | 10 / 8 (water's repeats collapsed) |
| proof generations | 4, all in the stage-9 prefetch (Nexus: water, methane, moved water; SP1: water) |
| prefetch wall | 236.0 s for 269.4 s of proof time (SP1 ~231 s dominates) |
| campaign warrants | 8, **all cache hits**, all re-verified |
| water's warrants | (nexus, verified) + (sp1, verified) — one computation, two independent proof systems |
| campaign wall | 220.0 s — of which **219.9 s is hit re-verification** |
| hit re-verification, per backend | **SP1 ≈ 73.4 s/hit** (2.78 MB proof); **Nexus ≈ 0.1 s/hit** (77 KB) |
| evidence fingerprints | 34 |
| evidence invariance | verified campaign == unproved baseline — asserted, CONFIRMED |
| GROMACS point | argon trimer potential completed through the external boundary |

**The campaign's discovered bottleneck** (measured, not guessed):
verification cost is not uniform across the proof ladder. A Nexus
warrant re-verifies in 0.1 s; an SP1 warrant costs **~73 s per hit** —
about a quarter of the ~300 s proof it reuses, paid on *every* hit
because reuse rightly never skips verification. Three water repeats
against a dual-backend policy therefore spent 219.9 s of a 220.0 s
campaign re-verifying SP1 hits. Whatever comes next should start from
this number — plausibly a reusable deterministic verifier artifact
(verification key / backend setup, NOT a cached verdict), but that is
the next stage's question, to be taken up only from these
measurements.

## Claim classification

**MEASURED**: every campaign number above; the exact kernel outputs
(argon 526³, 526²/2; NaCl (a/2)²; methane 2976 pm²); prove/verify host
call counts; the GROMACS potential; evidence invariance.

**STRUCTURALLY GUARANTEED**: structure identities commit to canonical
bytes only; crystal/molecule tag separation; the lowering's totality
and determinism; warrant reuse cannot skip the hit verifier; unproven
kernels cannot acquire warrants (registry gate); the EvidencePool
cannot see warrants or structures' provenance.

**CALLER-DECLARED**: the element→mass table (recorded once in
`lowering.py`); each structure's geometry source and rounding (recorded
in `library.py`); the argon force-field parameters (recorded in
`gromacs_bridge.py`); the GROMACS descriptor's binding of engine
version line to actual binary behavior (the stage-1 posture,
unchanged).

**EXTERNALLY UNVERIFIABLE**: that any structure physically exists,
that any coordinate was measured, that a lab ever held these systems —
a proof here establishes executable identity, program semantics, input
commitment, output commitment, execution; it can never establish "this
molecule physically existed" without an independent physical witness.
The Phase 118–122 boundary stands: COMPUTATION ≠ MEASUREMENT.

## Discovered limitations

1. **Element-blindness of distance kernels** is a real trust boundary:
   proofs bind consumed bytes exactly, so what a kernel does not
   consume, its proof does not bind. Resolved honestly by the Rg
   kernel, not by hashing Python objects.
2. **Structural kernels have no guests yet** — Rg and crystal
   computations execute natively and are attributably unprovable until
   guests are built through the Stage 5 reproducible-build machinery
   (the established, now-routine path).
3. **No physical-equivalence relation** (symmetry, translation,
   rotation invariance) exists yet — deliberately: computational
   identity and physical equivalence stay distinct until a workload
   needs the relation.
