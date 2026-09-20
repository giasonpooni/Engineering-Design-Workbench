# STE Stage 4 -- Generalization: Is This Actually a Scientific Execution Substrate?

The question Stage 4 was run to answer, with the answer measured rather
than asserted: three materially different scientific workloads passed
through the unchanged contract.

| workload | computational structure | route | proof status |
|---|---|---|---|
| A1: GROMACS MD trajectory (8-atom argon, 200 steps, dt=2fs) | time integration of equations of motion | external process | unproved -- stated, outside the guest envelope |
| A2: 1-D heat diffusion (explicit finite difference, Jacobi, Dirichlet) | time-stepped nearest-neighbour PDE stencil | native kernel + SP1 guest + Nexus guest | **proven by BOTH backends** |
| A3: GROMACS steepest-descent minimization (perturbed lattice) | iterative optimization | external process | unproved -- stated |

(The stage-1/2/3 pairwise-energy workload -- all-pairs accumulation --
remains the fourth shape.)

## Target B -- contract generality: HELD, with zero substrate changes

`ExecutionSpecification -> engine -> ExecutionResult -> OperationTrace
-> optional ProofBackend -> VerifiedExecution` carried all three
workloads. What adding a workload actually took:

- a kernel workload: one function in `execution-kernel` (no_std), one
  registry entry in `execution-cli`, two ~40-line guests (the adapters,
  hosts, drivers and layout were REUSED unchanged -- the SP1 layout tag
  was renamed `ste.sp1.kernel-io.v1` because it was never
  pairwise-specific, and the adapter types were renamed
  `Sp1KernelBackend`/`NexusKernelBackend` to their true generality);
- an external workload: one runner function and one descriptor header in
  `execution/gromacs.py` (a shared pipeline was factored out; the
  stage-1 single-point runner's bytes are untouched).

**No workload-specific type, field, or branch entered the substrate.**
The one candidate limitation found and deliberately NOT solved: an
`ExecutionResult` carries ONE output byte string, so multi-artifact
outputs must canonicalize into one encoding (the minimization runner
concatenates energy series + minimized structure under labeled
sections). All three workloads fit that; the day a workload genuinely
cannot, THAT is the smallest missing semantic -- speculatively adding a
multi-output map today was rejected.

## Target C -- deterministic identity: every property held

Exercised per workload (heat exhaustively; GROMACS workloads for the
spec/input/config/program dimensions; argon-pair coverage from earlier
stages still standing): same specification twice -> one identity;
occurrences stay distinct; two complete loops admit ONE observation id;
changed input/configuration/program -> changed identities; failed
execution admits nothing semantic. One boundary made newly explicit by
the rejected-output test: on downstream rejection the raw **Record IS
admitted** (the dispatch happened; its transcript is structural
bookkeeping, Phase 44's distinction) while no Observation enters, and
the operation ledger reads SUCCEEDED -> REJECTED.

## Target D -- backend neutrality on a NEW workload

The heat kernel -- which did not exist when either adapter was built --
crossed both backends with **neither adapter modified**: one
specification, one computation identity, two warrants
(`sp1-cpu` / `nexus-stwo`, distinct proof identities). Outside the
envelope, refusal is explicit: a GROMACS specification is refused by the
proving layer (`REGISTERED_GUEST_DESCRIPTORS`), and a heat statement put
to a pairwise-registered backend fails attributably as
`ProgramMismatch`. Different proof backend != different scientific
fact; no backend != pretended verification.

## Target E -- the GROMACS boundary, expanded

The trajectory workload exercises actual simulation state (the
per-frame energy series is non-constant and byte-reproducible across
fresh runs); the minimization workload relaxes a perturbed lattice
(-5.87 -> -18.39 kJ/mol in 41 steps) and returns the minimized
structure. Every demanded dimension is carried and none contaminates
evidence identity: executable identity (the `gmx --version` line) and
topology live in the PROGRAM bytes; the `.mdp` is the CONFIGURATION;
the `.gro` initial state is the INPUT; the output is the canonical
series encoding; the occurrence is per-invocation; verification status
is honestly `unproved`. Execution metadata reaches EvidencePool only
inside the Record's raw transcript -- never the Observation.

## Target F -- Rust/Python boundary audit

Verdict: **not crossing.** Rust holds execution isolation, canonical
encoding, commitments, kernels, verification -- and gained only a kernel
this stage. Python holds orchestration, workload adapters, the
researcher-facing composition -- and gained only runners and registry
entries. Two deliberate, documented asymmetries reviewed and kept:
(1) external-process workloads (GROMACS) are executed and
identity-committed from Python -- adapters are Python's job, and the
commitment function is the cross-checked mirror, with the weaker
declared-trust position stated in `execution/gromacs.py` since stage 1;
(2) the Python guest registry (`REGISTERED_GUEST_DESCRIPTORS`)
duplicates knowledge the `zk/` tree embodies -- accepted as the visible
one-place list, same pattern as the execution-cli registry.

## Target H -- has the system outgrown its name?

From the code: yes. The repository named "Scout-Retrieval-Agent"
currently implements, as tested layers: acquisition/retrieval
(`scout/`, `retrieval/`), evidence identity and admission
(`evidence/`), scientific state and decision (`materials/`,
`experiment/`), operation ledger (`operations/`), execution substrate
(`execution/`, `crates/`), proof backends (`zk/`), and presentation
(`workbench/`, `morpho/`). The proposed stack decomposition is accurate
with two corrections read off the code: the operation trace sits BESIDE
the execution path at the dispatch seam (it is not a stage the data
passes through), and proof/verification re-enters evidence only through
the same admission boundary as everything else (there is no second
arrow into the pool). SCOUT is one subsystem of a scientific
transformer engine, not the frame. No renaming performed, per the
directive.

## Measurements (this environment, 4 CPU cores)

- heat, native: sub-millisecond; through engine process: ~10 ms.
- heat, Nexus stwo proof (500 steps, 8 nodes): 1m13s, ~75 KB class.
- heat, SP1/Nexus proving instances in the suite (50 steps, 6 nodes):
  see the stage-4 test log; SP1 core remains minutes-class, Nexus
  seconds-to-a-minute class.
- GROMACS trajectory (200 steps): ~1 s per full pipeline, byte-identical
  repeat. Minimization: ~1 s, 41 steps to emtol=1.0, byte-identical
  repeat including the minimized structure (title line stripped -- it is
  presentation, not result).

## Failures discovered (the stage's most valuable output)

**A tamper test was falsified by reality and relocated the trust
boundary precisely.** The test assumed a heat proof verified under a
falsely-REGISTERED pairwise binding would fail as `ProgramMismatch`. It
VERIFIED. Correctly so: the registration IS the declared
"this-ELF-implements-that-descriptor" link stated since stage 2, and a
verifier cannot catch a false declaration -- catching it is what the
declaration stands in for. What the tests now pin instead: (1) an
EXPECTATION naming a different program than the registration is
attributably refused; (2) a false registration at the raw CLI seam
verifies -- the caller of that seam is the registrar, and the test
asserts this so it can never be mistaken for a checked property;
(3) the Python driver is not exposed: it registers `spec.program`
itself and cross-checks guest output against the native kernel, so a
wrong ELF for a specification surfaces as a commitment mismatch. The
permanent closure of this boundary is the provable-lowering /
reproducible-guest-build problem -- future work, named, not begun.

Also found and kept as a documented behavior: on downstream rejection
the raw Record IS admitted before the semantic gate refuses (Phase 44's
boundary observed live at the new workload's seam) -- the first draft of
the test wrongly asserted a byte-identical pool.

## Abstractions survived / rejected

Survived unchanged: ExecutionSpecification, ExecutionResult,
OperationTrace, ProofBackend, VerifiedExecution, the dispatcher seam,
every identity. Renamed to their real generality: Sp1KernelBackend,
NexusKernelBackend, `ste.sp1.kernel-io.v1`. Rejected: multi-output
result maps (no workload forced it), a workload base class (three
runner functions and a trait were enough), any Morpho implementation
(not implemented), renaming the
repository (assessment only).
