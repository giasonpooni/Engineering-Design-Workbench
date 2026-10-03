# Scientific Computation Runtime Stage 1 -- The Execution Vertical

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
The first coherent execution vertical of Scientific Computation Runtime:
built, executed, audited, and integrated in one pass. From the STE
diagram, the slice that now runs end to end:

```text
OPERATION TRACE          operations/trace.py            (Phase 124, unchanged)
      |
EXECUTION SPECIFICATION  execution/specification.py     (new: the request)
      |
EXECUTION ENGINE         crates/execution-cli           (new: one Rust process per run)
      |                  execution/gromacs.py           (new: real external workload)
COMPUTATION              checked ExecutionResult        (execution/engine.py)
      |
RESULT STATE             DispatchedMeasurement          (existing seam type)
      |
EVIDENCE ADMISSION       experiment.step.run_experiment_step   (unchanged)
      |
EvidencePool             unchanged, untouched, uncontaminated
```

**Zero changes to EvidencePool, evidence identity, `materials/`,
`experiment/`, `scout/`, or `operations/`.** The vertical enters the
scientific architecture through the `ActionDispatcher` seam Phase 63
built and Phase 125 instrumented, so every existing firewall applies to
computed results automatically.

## What was reused vs. built

| STE box | disposition |
|---|---|
| SCOUT / DAF / EVIDENCE | already exist; untouched |
| OPERATION TRACE | already exists (`operations/`); attached at the seam, unchanged |
| EXECUTION SPECIFICATION | **built** -- `ExecutionSpecification(program, configuration, input_payload)` |
| EXECUTION ENGINE | **built** -- `execution-cli` (Rust) + `run_specification` (Python, checking side) |
| COMPUTATION / SIMULATION | **built** -- native kernel (computation) + GROMACS single-point energy (simulation) |
| RESULT STATE -> ADMISSION | already exists -- `DispatchedMeasurement` -> `run_experiment_step` |
| VERIFICATION LAYER | exists from Phase 129 (`ProofBackend`); no zkVM attached yet |
| SP1 / NEXUS / RISC ZERO | **not built** -- next stage, after the proof interface meets a real workload |

## The specification (and the recorded reversal)

The Phase 128 review rejected an `ExecutionSpecification` for lack of a
consumer. The consumer arrived with the cross-process boundary: a result
coming back from another process must name the request it answers, or it
is the detachable-warrant hazard (Phase 128 probe 1) at the process
seam. The reversal is recorded at the type's docstring and at
`SPECIFICATION_TAG` in `crates/execution-model` -- not made silently.

Identity: `commit("scout.execution.specification.v1", [program,
configuration, input])`. Excluded by construction (the dataclass has
exactly three fields, and a test pins that): occurrence numbers,
timestamps, hostnames, engine versions-as-metadata. Two identical
requests are one request; two RUNS of it are two occurrences.

## Checked, not trusted: the process boundary

`run_specification` recomputes every identity the engine echoes --
specification, program, input, output, computation -- from bytes Python
already holds, and raises `EngineIdentityMismatch` on any disagreement.
Every execution is therefore also a live cross-language agreement check
and a tamper check: the test suite includes a lying engine (one nibble
off in the computation identity) and a misdirected engine (answers for a
different request); both are caught.

What checking CANNOT catch: an engine that runs a different computation
and honestly reports that computation's real output -- the
bytes-vs-behavior gap, declared since Phase 129, closable only by a
proving backend.

Refusal semantics: `unrunnable` (unknown program; configuration bytes
for a program that takes none) means NOTHING RAN -- surfaced as
`ExecutionRefused`, mapped to the ledger's NEVER_STARTED, with no
occurrence resolved. Ignoring configuration silently would let two
different requests converge on "the same" computation; refusal is the
audit position.

## The real workload (Target D, executed)

The GROMACS fork was built from source in-session (double precision,
SIMD off, fftpack) and a genuine workload runs through the vertical:
argon-pair single-point energy, `grompp -> mdrun(nsteps=0) -> energy`.

Dimension mapping: **program** = descriptor (engine version line + full
topology bytes -- two GROMACS versions are two programs, as two backend
versions are two proofs); **configuration** = the `.mdp`;
**input** = the `.gro`. Output bytes are gmx's own text for the
potential (`potential_kj_per_mol -0.914149`), verbatim -- no
re-formatting on our side.

Trust spectrum, stated: the Rust engine is *checked* (identities
recomputed against its echoes); the GROMACS runner is *declared* (gmx
knows nothing of our identities, so this layer computes all of them, and
the descriptor's version line is verified against `gmx --version` only
at build time). Determinism claimed and tested: same binary, same
machine. Cross-machine bit-identity: not claimed.

Audited live: completion with a physically-sane sign (attractive well ->
negative potential), repeat determinism across fresh workdirs, geometry
change separating input/computation identities, version-in-program, and
a broken topology halting at grompp with no output and nothing
fabricated.

## The decisive integration audits (all as tests)

- **Evidence uncontaminated by execution history** (invariant 8): two
  complete loops -- two engine processes, two pools -- admit the SAME
  observation id. Execution happened twice; the evidence is one fact,
  twice reproduced. The execution transcript (specification, occurrence,
  computation identity) rides in the Record's raw content; the
  Observation's semantic content carries none of it.
- **Operation identity stays occurrence-based**: the same rerun that
  collapses evidence ids mints occurrence 1 in the operation trace, with
  `output_ref` pointing at the observation -- the one-directional link
  from Phase 125, unchanged.
- **Failure admits nothing**: a faulting execution (coincident
  particles) raises at the dispatch seam, the pool fingerprint is
  byte-identical before and after, and the operation ledger records
  FAILED.
- **Declaration honesty**: computed results enter with
  `extraction_method="simulation:deterministic_native_execution"` --
  the one prefix asserting no external-world event. A declaration is
  still not a witness; what improved is only that every identity of the
  reported computation was independently recomputed.

## What this stage deliberately did not build

SP1/Nexus/RISC Zero adapters (the proof interface has now met a real
workload; an adapter is the NEXT stage), proof generation, Python
bindings (the process boundary is the bridge; FFI must earn its
existence), persistence, cross-process occurrence identity, any change
to evidence semantics.
