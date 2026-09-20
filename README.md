# State Estimation Evaluation Testbed

**Early-stage evaluation infrastructure for state reconstruction under degraded observations.**

This repository defines the state-estimation evaluation responsibility within
Notation Systems' computational instrumentation stack. Its scope covers
reconstruction under noise, missing observations, latency, and other measurement
degradation, with the plant and measurement model declared explicitly.

## Status and implemented contents

This checkout contains a declarative invariant corpus, its citation, and the
first executable contract slice. It does not yet contain an estimator,
evaluation runner, numerical solver, simulation, fault-injection runner,
benchmark results, or physical-validation certificate.

The existing corpus declares:

- `plant.declared`: estimation requires a declared plant and measurement model.
- `var.x`: the state coordinate requires `declared-H`.
- `claim_scope: computational-integrity-only`.

These declarations do not establish physical validity, estimator accuracy,
observability, or a stability certificate. Noise, missingness, and latency are
evaluation concerns, not implemented perturbation generators in this checkout.

### Instrument exchange contract

`state_estimation_testbed.contracts` validates the v1 instrument exchange
boundary for observation batches, numerical result artifacts, verification
artifacts, and covariance eligibility. It enforces:

- ordered variables, per-component units, coordinate frame, and tangent-space
  evaluation point;
- finite square covariance matrices, symmetry and numerical positive-semidefinite
  checks under the tolerances described below, with an effective-rank estimate;
- explicit unknown covariance rather than a fabricated zero matrix;
- retained source and calibration references; and
- verification summaries consistent with their checks, with internal and
  independent verification kept distinct.

Numerical eligibility does not establish calibration validity, sensor truth,
model adequacy, physical applicability, estimator accuracy, or stability.
Identity fields are references, not authenticated attestations: validation does
not fetch their subjects, recompute producer-specific content hashes, establish
admission, or independently substantiate a declared external verifier.

Run the executable contract slice with `python -m pytest`.

#### Validator API 0.2 compatibility

The wire schemas remain `notation.instrument.*.v1`; validator API 0.2 tightens
previously ambiguous or unsafe validation behavior:

- `CovarianceValidation.effective_rank` is `None` for `unknown` and
  `not_applicable`. A supplied all-zero matrix has rank `0`; missing covariance
  does not. Consumers must handle the nullable rank explicitly.
- Finite, nonnegative variances are mandatory. A zero variance requires an
  exactly zero row and column. Positive-variance coordinates are normalized to
  dimensionless correlations before symmetry, PSD, and rank checks, so changing
  one variable's physical units does not hide another variable's uncertainty.
- Tolerances are finite numbers in `[0, 1)`, expressed in correlation
  coordinates. Both stored triangles must pass the symmetric-eigenspectrum
  check; the matrix is neither averaged nor repaired. Effective rank is the
  smaller triangle rank if tolerated asymmetry straddles the rank threshold.
  Floating-point decisions close to that threshold remain tolerance-dependent.
- The dependency-free Jacobi eigensolver fails closed on nonconvergence.
  It replaces the scale-sensitive unpivoted LDL check; the rank-one covariance
  `[[1e-14, 1e-7], [1e-7, 1]]`, formerly rejected, now validates with rank `1`.
  Optional NumPy differential tests exercise singular/full-rank matrices,
  permutations, indefinite correlations, and extreme mixed-unit scales;
  NumPy is not required by the validator itself.
- Tangent frames require an ordered basis and a finite evaluation point. The
  point's dimension need not equal state dimension (for example, a 2D tangent
  plane in 3D). These declarations do not establish a valid frame transform.
- Timestamps must include a complete date and time in
  `YYYY-MM-DDTHH:MM:SS[.fraction]Z` form; leap seconds are not supported.
  Observation/receipt ordering is not inferred without a clock mapping.
- Covariance calibration references must also be retained at the artifact
  level. Result, execution, input, verification, and subject references cannot
  reuse the same identity where they denote different artifacts.

## Technical responsibility

The testbed's responsibility is to evaluate state reconstruction against a
declared model and explicitly characterized observations. Estimator
implementations retain their own identities and mathematical assumptions; this
repository is not the authoritative implementation of every estimator.

A reported evaluation must distinguish its source observations, model
declarations, estimator operation and version, execution attempt, computed
result, and verification evidence. Declaring an invariant is separate from
executing an evaluation or verifying its result.

## Relationship to the instrumentation stack

These are component responsibilities, not claims of complete working
integrations in this early-stage repository.

| Component | Responsibility |
| --- | --- |
| **State Estimation Evaluation Testbed** | Evaluation of reconstruction under declared observation degradation. |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Source acquisition, observations, extraction lineage, and explicit missingness. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Evidence retention, versioned state, admission, and release management. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Declared scientific computations and provenance-bearing execution. |
| [Constraint-Based State Reconciliation](https://github.com/giasonpooni/Constraint-Based-State-Reconciliation) | Reconciliation against declared physical or structural constraints. |
| [Geospatial State Visualization](https://github.com/giasonpooni/Geospatial-State-Visualization) | Read-only presentation of geographic and temporal state. |
| [Computational Instrumentation Workbench](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Instrument sessions, adapters, inspection, and replay. |

Evaluation, reconciliation, execution, information governance, and visualization
remain separate responsibilities. A display or evaluation result does not grant
authority to change retained evidence or operational state.

## Repository identity and compatibility

The repository was renamed from `State-Estimation-Testbed` to
`State-Estimation-Evaluation-Testbed`. Use the current repository name and
location for documentation and new references.

This naming change preserves the existing `invariant-corpus-v1` schema,
invariant IDs, state-coordinate ID, declared claim scope, and historical
`cites` value. It does not rewrite operation identities, evidence, execution
records, or historical runtime pins.

## Repository contents

- [Invariant corpus](validation/invariant-corpus-v1.json)
- [Corpus citation and claim boundary](docs/invariant-corpus-cite-v1.md)
- [License](LICENSE)
